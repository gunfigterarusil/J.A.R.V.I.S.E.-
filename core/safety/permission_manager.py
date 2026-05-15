"""core/safety/permission_manager.py — Level 0–6 permission gate.

The PermissionManager tracks the current permission level and per-action
overrides.  It persists granted/denied decisions across sessions so the
user does not have to re-approve common safe actions every restart.
"""
from __future__ import annotations

import logging
import time
from enum import IntEnum
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.persistence import PersistenceManager

logger = logging.getLogger("core.safety.permissions")


class PermissionLevel(IntEnum):
    L0_THINK = 0         # think, remember, speak — no external effects
    L1_READ_SCREEN = 1   # read screen / OCR — default at startup
    L2_WEB_SEARCH = 2    # web search (read-only network)
    L3_OPEN_APPS = 3     # open / switch / close applications
    L4_EDIT_FILES = 4    # edit files inside sandbox only
    L5_RUN_COMMANDS = 5  # shell commands (requires explicit per-action confirm)
    L6_AUTONOMOUS = 6    # autonomous chained actions (never the default)


# Maps action_type → minimum PermissionLevel required to attempt the action.
ACTION_LEVEL_MAP: Dict[str, PermissionLevel] = {
    # L0
    "think": PermissionLevel.L0_THINK,
    "remember": PermissionLevel.L0_THINK,
    "speak": PermissionLevel.L0_THINK,
    "internal_monologue": PermissionLevel.L0_THINK,
    # L1
    "screenshot": PermissionLevel.L1_READ_SCREEN,
    "read_screen": PermissionLevel.L1_READ_SCREEN,
    "ocr": PermissionLevel.L1_READ_SCREEN,
    "read_file": PermissionLevel.L1_READ_SCREEN,
    "list_files": PermissionLevel.L1_READ_SCREEN,
    "search_files": PermissionLevel.L1_READ_SCREEN,
    # L2
    "web_search": PermissionLevel.L2_WEB_SEARCH,
    "web_fetch": PermissionLevel.L2_WEB_SEARCH,
    # L3
    "open_app": PermissionLevel.L3_OPEN_APPS,
    "open_url": PermissionLevel.L3_OPEN_APPS,
    "switch_window": PermissionLevel.L3_OPEN_APPS,
    "close_app": PermissionLevel.L3_OPEN_APPS,
    "gui_click": PermissionLevel.L3_OPEN_APPS,
    "gui_press": PermissionLevel.L3_OPEN_APPS,
    "gui_scroll": PermissionLevel.L3_OPEN_APPS,
    "gui_wait": PermissionLevel.L1_READ_SCREEN,
    "gui_type_text": PermissionLevel.L4_EDIT_FILES,
    "gui_hotkey": PermissionLevel.L4_EDIT_FILES,
    # L4
    "write_file": PermissionLevel.L4_EDIT_FILES,
    "create_dir": PermissionLevel.L4_EDIT_FILES,
    "move_file": PermissionLevel.L4_EDIT_FILES,
    "delete_file": PermissionLevel.L4_EDIT_FILES,
    # L5
    "run_command": PermissionLevel.L5_RUN_COMMANDS,
    "execute_script": PermissionLevel.L5_RUN_COMMANDS,
    "start_process": PermissionLevel.L5_RUN_COMMANDS,
    # L6
    "autonomous_chain": PermissionLevel.L6_AUTONOMOUS,
    "self_modify": PermissionLevel.L6_AUTONOMOUS,
}

_DEFAULT_LEVEL = PermissionLevel.L1_READ_SCREEN


class PermissionManager:
    """Tracks current permission level and explicit per-action user overrides."""

    def __init__(self, default_level: PermissionLevel = _DEFAULT_LEVEL) -> None:
        self.current_level: PermissionLevel = default_level
        self._granted_actions: Set[str] = set()   # user said "always allow this"
        self._denied_actions: Set[str] = set()    # user said "never allow this"
        self._history: List[dict] = []

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------
    def check(self, action_type: str) -> Tuple[bool, str]:
        """Returns (allowed, reason).

        Precedence:
          1. Explicit user deny → blocked
          2. Explicit user grant → allowed (even if level is too low)
          3. Required level > current_level → blocked
          4. Otherwise → allowed
        """
        if action_type in self._denied_actions:
            return False, f"Action '{action_type}' was explicitly denied by the user."

        if action_type in self._granted_actions:
            self._log("granted_override", action_type, "allowed")
            return True, ""

        required = ACTION_LEVEL_MAP.get(action_type, PermissionLevel.L5_RUN_COMMANDS)
        if required > self.current_level:
            return False, (
                f"Action '{action_type}' requires level {required.name} "
                f"(L{required}), but current level is {self.current_level.name} "
                f"(L{self.current_level})."
            )

        self._log("level_check", action_type, "allowed")
        return True, ""

    # ------------------------------------------------------------------
    # User overrides
    # ------------------------------------------------------------------
    def grant(self, action_type: str) -> None:
        self._denied_actions.discard(action_type)
        self._granted_actions.add(action_type)
        self._log("user_grant", action_type, "granted")
        logger.info(f"[Permissions] '{action_type}' granted by user")

    def deny(self, action_type: str) -> None:
        self._granted_actions.discard(action_type)
        self._denied_actions.add(action_type)
        self._log("user_deny", action_type, "denied")
        logger.info(f"[Permissions] '{action_type}' denied by user")

    def set_level(self, level: PermissionLevel) -> None:
        old = self.current_level
        self.current_level = level
        logger.info(f"[Permissions] Level changed: {old.name} → {level.name}")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, persistence: "PersistenceManager") -> None:
        persistence.save("permissions", {
            "current_level": int(self.current_level),
            "granted_actions": list(self._granted_actions),
            "denied_actions": list(self._denied_actions),
            "history": self._history[-200:],
        })

    def load(self, persistence: "PersistenceManager") -> None:
        data = persistence.load("permissions")
        if not data:
            return
        try:
            self.current_level = PermissionLevel(data.get("current_level", int(_DEFAULT_LEVEL)))
        except ValueError:
            pass
        self._granted_actions = set(data.get("granted_actions", []))
        self._denied_actions = set(data.get("denied_actions", []))
        self._history = data.get("history", [])
        logger.info(f"[Permissions] Loaded — level={self.current_level.name}, "
                    f"granted={len(self._granted_actions)}, denied={len(self._denied_actions)}")

    def to_dict(self) -> dict:
        return {
            "current_level": int(self.current_level),
            "current_level_name": self.current_level.name,
            "granted_actions": list(self._granted_actions),
            "denied_actions": list(self._denied_actions),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _log(self, event: str, action_type: str, decision: str) -> None:
        self._history.append({
            "timestamp": time.time(),
            "event": event,
            "action_type": action_type,
            "decision": decision,
        })
