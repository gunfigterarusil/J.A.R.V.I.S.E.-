"""core/module_manager.py — Dynamic module discovery, loading, and unloading.

Modules expose a top-level factory:
    def create_module() -> CognitiveModule: ...

ModuleManager scans tier directories, imports each module file,
calls create_module(), and hands the instance to the kernel.

V15.5: Failed modules are recorded in _failed_modules instead of crashing the whole
startup. The kernel emits a kernel_degraded event so the UI can show a warning.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.kernel import Kernel
    from core.module_base import CognitiveModule

logger = logging.getLogger("core.module_manager")


class ModuleManager:
    def __init__(self) -> None:
        self._kernel: Optional["Kernel"] = None
        self._failed_modules: List[Dict] = []  # populated during load_all()

    def set_kernel(self, kernel: "Kernel") -> None:
        self._kernel = kernel

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def discover(self, tier_paths: list[str]) -> list[str]:
        """Scan directories for loadable module files.

        Returns list of absolute file paths whose name ends with _module.py
        and that contain a create_module() factory.
        """
        found: list[str] = []
        for tier_path in tier_paths:
            p = Path(tier_path)
            if not p.exists():
                continue
            for pyfile in p.rglob("*_module.py"):
                if self._has_factory(str(pyfile)):
                    found.append(str(pyfile))
        return sorted(found)

    def _has_factory(self, path: str) -> bool:
        try:
            src = Path(path).read_text(encoding="utf-8")
            return "def create_module" in src
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Load / unload
    # ------------------------------------------------------------------
    def load(self, path: str) -> Optional["CognitiveModule"]:
        """Import module from file, call create_module(), register with kernel."""
        if self._kernel is None:
            raise RuntimeError("ModuleManager has no kernel reference")
        try:
            spec = importlib.util.spec_from_file_location("_dyn_module", path)
            if spec is None or spec.loader is None:
                logger.error(f"[ModuleManager] Cannot load spec from {path}")
                return None
            mod_py = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod_py)
            if not hasattr(mod_py, "create_module"):
                logger.error(f"[ModuleManager] No create_module() in {path}")
                return None
            instance = mod_py.create_module()
            self._kernel.register_module(instance)
            logger.info(f"[ModuleManager] Loaded {instance.module_id} from {path}")
            return instance
        except Exception as exc:
            logger.error(f"[ModuleManager] Failed to load {path}: {exc}")
            return None

    def load_all(self, tier_paths: list[str]) -> int:
        """Discover and load all modules in the given tier paths.

        Returns count of successfully loaded modules.
        Failed modules are recorded in _failed_modules (silent fallback).
        """
        self._failed_modules.clear()
        paths = self.discover(tier_paths)
        count = 0
        for path in paths:
            try:
                result = self.load(path)
                if result is not None:
                    count += 1
                else:
                    self._failed_modules.append({
                        "path": str(path),
                        "error": "load() returned None (no create_module or bad spec)",
                        "timestamp": time.time(),
                    })
            except Exception as exc:
                logger.error("[ModuleManager] Failed to load %s: %s", path, exc)
                self._failed_modules.append({
                    "path": str(path),
                    "error": repr(exc),
                    "timestamp": time.time(),
                })
        return count

    def get_failed_modules(self) -> List[Dict]:
        return list(self._failed_modules)

    def degraded_mode(self) -> bool:
        return len(self._failed_modules) > 0

    def unload(self, module_id: str) -> bool:
        """Shutdown and remove a module from the kernel."""
        if self._kernel is None:
            return False
        mod = self._kernel.modules.pop(module_id, None)
        if mod is None:
            return False
        try:
            mod.shutdown()
        except Exception as exc:
            logger.error(f"[ModuleManager] Error shutting down {module_id}: {exc}")
        self._kernel.event_bus.unregister_consumer(module_id)
        logger.info(f"[ModuleManager] Unloaded {module_id}")
        return True

    def reload(self, module_id: str, path: str) -> bool:
        """Unload then re-load a module by file path (dev hot-reload)."""
        self.unload(module_id)
        return self.load(path) is not None
