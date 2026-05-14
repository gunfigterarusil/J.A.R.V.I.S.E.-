"""core/safety/sandbox.py — Filesystem access control.

Reads are allowed anywhere by default.
Writes are restricted to the jarvis_workspace and jarvis_brain directories
unless the user explicitly adds more paths at runtime.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("core.safety.sandbox")

# Paths where the brain is allowed to write without user confirmation.
_DEFAULT_WRITE_PATHS: List[Path] = [
    Path("~/jarvis_workspace").expanduser().resolve(),
    Path("~/.jarvis_brain").expanduser().resolve(),
]

# Paths that are always forbidden to write, regardless of allowed list.
_FORBIDDEN_WRITE_PATHS: List[Path] = [
    Path("C:/Windows/System32"),
    Path("C:/Windows"),
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
]


class Sandbox:
    """Controls which filesystem paths the brain may read/write/execute."""

    def __init__(self, extra_allowed: List[str] | None = None) -> None:
        self._allowed_write: List[Path] = list(_DEFAULT_WRITE_PATHS)
        for p in (extra_allowed or []):
            self._allowed_write.append(Path(p).expanduser().resolve())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def check_read(self, path: str) -> Tuple[bool, str]:
        """Reads are allowed everywhere except explicitly forbidden zones."""
        resolved = _safe_resolve(path)
        if resolved is None:
            return False, f"Cannot resolve path: {path}"
        if _is_forbidden(resolved):
            return False, f"Read from forbidden path denied: {resolved}"
        return True, ""

    def check_write(self, path: str) -> Tuple[bool, str]:
        """Write is allowed only inside sandbox paths."""
        resolved = _safe_resolve(path)
        if resolved is None:
            return False, f"Cannot resolve path: {path}"
        if _is_forbidden(resolved):
            return False, f"Write to forbidden path denied: {resolved}"
        if _is_core_path(resolved):
            return False, f"Write to core/ directory is forbidden (self-modification): {resolved}"
        for allowed in self._allowed_write:
            try:
                resolved.relative_to(allowed)
                return True, ""
            except ValueError:
                pass
        return False, (
            f"Path '{resolved}' is outside the allowed sandbox. "
            f"Allowed write paths: {[str(p) for p in self._allowed_write]}"
        )

    def check_execute(self, path: str) -> Tuple[bool, str]:
        """Execution is allowed only inside sandbox paths."""
        resolved = _safe_resolve(path)
        if resolved is None:
            return False, f"Cannot resolve path: {path}"
        if _is_forbidden(resolved):
            return False, f"Execute in forbidden path denied: {resolved}"
        for allowed in self._allowed_write:
            try:
                resolved.relative_to(allowed)
                return True, ""
            except ValueError:
                pass
        return False, f"Execution outside sandbox is forbidden: {resolved}"

    def add_allowed_path(self, path: str) -> None:
        """User can expand the sandbox at runtime."""
        p = Path(path).expanduser().resolve()
        if p not in self._allowed_write:
            self._allowed_write.append(p)
            logger.info(f"[Sandbox] Added allowed path: {p}")

    def allowed_write_paths(self) -> List[str]:
        return [str(p) for p in self._allowed_write]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_resolve(path: str) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except Exception:
        return None


def _is_forbidden(resolved: Path) -> bool:
    for fp in _FORBIDDEN_WRITE_PATHS:
        try:
            resolved.relative_to(fp)
            return True
        except ValueError:
            pass
    return False


def _is_core_path(resolved: Path) -> bool:
    """Prevent writing to the core/ runtime itself."""
    try:
        # project root is two levels above this file: core/safety/sandbox.py
        project_root = Path(__file__).resolve().parents[2]
        core_dir = project_root / "core"
        resolved.relative_to(core_dir)
        return True
    except ValueError:
        return False
