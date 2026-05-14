"""core/persistence.py — JSON-based persistence manager.

Stores brain state across restarts at a configurable directory
(default: ~/.jarvis_brain/).

Usage by modules:
    self.kernel.persistence.save("memory_episodic", data_dict)
    data = self.kernel.persistence.load("memory_episodic")   # {} if missing
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import CoreState

logger = logging.getLogger("core.persistence")


class PersistenceManager:
    def __init__(self, base_dir: str = "~/.jarvis_brain") -> None:
        self._base = Path(base_dir).expanduser().resolve()
        self._base.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Persistence] Storage at {self._base}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save(self, namespace: str, data: Any) -> bool:
        path = self._path(namespace)
        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            tmp.replace(path)   # atomic rename
            return True
        except Exception as exc:
            logger.error(f"[Persistence] save({namespace}) failed: {exc}")
            return False

    def load(self, namespace: str) -> Any:
        path = self._path(namespace)
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error(f"[Persistence] load({namespace}) failed: {exc}")
            return {}

    def exists(self, namespace: str) -> bool:
        return self._path(namespace).exists()

    def delete(self, namespace: str) -> bool:
        path = self._path(namespace)
        if path.exists():
            path.unlink()
            return True
        return False

    def checkpoint(self, core_state: "CoreState") -> None:
        """Save identity-critical CoreState fields."""
        snap = {
            "consciousness_level": core_state.consciousness_level,
            "energy_level": core_state.energy_level,
            "attachment_state": core_state.attachment_state,
            "temporal_marker": core_state.temporal_marker,
            "uptime": core_state.uptime,
        }
        self.save("core_state", snap)

    def restore_core_state(self, core_state: "CoreState") -> None:
        """Restore previously saved CoreState fields."""
        snap = self.load("core_state")
        if snap:
            core_state.patch(snap)
            logger.info("[Persistence] CoreState restored from disk")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _path(self, namespace: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)
        return self._base / f"{safe}.json"
