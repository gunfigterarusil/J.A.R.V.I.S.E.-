"""core/safety/risk_engine.py — Danger scoring for action requests.

The RiskEngine assigns a numeric score (0..10) to every proposed action.
Scores at or above CONFIRM_THRESHOLD require explicit user confirmation
before the action can proceed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

logger = logging.getLogger("core.safety.risk")


class RiskCategory(Enum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class RiskAssessment:
    score: float              # 0..10
    category: RiskCategory
    requires_confirmation: bool
    reasons: List[str] = field(default_factory=list)


# Base risk score per action type.  Actions not listed default to 1.0.
_ACTION_BASE_SCORES: Dict[str, float] = {
    # Tier 0 — pure thought / speech
    "think": 0.0,
    "remember": 0.0,
    "speak": 0.5,
    "internal_monologue": 0.0,
    # Tier 1 — screen/input read (no writes)
    "screenshot": 1.0,
    "read_screen": 1.0,
    "ocr": 1.0,
    # Tier 2 — web (read-only)
    "web_search": 1.5,
    "web_fetch": 1.5,
    # Tier 3 — application control
    "open_app": 2.5,
    "open_url": 3.0,
    "switch_window": 2.0,
    "close_app": 3.0,
    "gui_click": 5.2,
    "gui_type_text": 5.5,
    "gui_press": 4.2,
    "gui_hotkey": 5.5,
    "gui_scroll": 3.0,
    "gui_wait": 1.0,
    # Tier 4 — file operations
    "read_file": 1.0,
    "list_files": 1.0,
    "search_files": 1.5,
    "write_file": 4.0,
    "delete_file": 6.0,
    "create_dir": 3.0,
    "move_file": 4.5,
    # Tier 5 — command execution
    "run_command": 7.0,
    "execute_script": 7.5,
    "start_process": 6.5,
    # Tier 6 — autonomous / chained
    "autonomous_chain": 9.0,
    "self_modify": 10.0,
}

# Keywords in the data payload that add extra risk.
_DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "destroy", "wipe", "format", "drop", "truncate",
    "kill", "terminate", "overwrite", "purge",
]
_SYSTEM_PATH_KEYWORDS = [
    "system32", "windows", "program files", "/etc/", "/bin/", "/sbin/",
    "/usr/", "c:\\windows", "c:/windows",
]
_PRIVATE_DATA_KEYWORDS = [
    "password", "passwd", "secret", "token", "api_key", "credential",
    "private_key", "ssh_key", "cookie", "session",
]
_CHAIN_KEYWORDS = [
    "chain", "then", "next_action", "sequence", "pipeline", "loop",
]


class RiskEngine:
    CONFIRM_THRESHOLD = 5.0  # score ≥ this → requires user confirmation

    def assess(self, action_type: str, data: dict) -> RiskAssessment:
        score = _ACTION_BASE_SCORES.get(action_type, 1.0)
        reasons: List[str] = []

        data_str = _flatten(data).lower()

        # Destructive keywords in payload
        for kw in _DESTRUCTIVE_KEYWORDS:
            if kw in data_str:
                score += 3.0
                reasons.append(f"destructive keyword '{kw}' in payload")
                break

        # System path target
        for kw in _SYSTEM_PATH_KEYWORDS:
            if kw in data_str:
                score += 4.0
                reasons.append(f"system path '{kw}' targeted")
                break

        # Private/sensitive data involved
        for kw in _PRIVATE_DATA_KEYWORDS:
            if kw in data_str:
                score += 2.0
                reasons.append(f"private data keyword '{kw}' in payload")
                break

        # Chained / autonomous action
        for kw in _CHAIN_KEYWORDS:
            if kw in data_str:
                score += 2.0
                reasons.append(f"chained action keyword '{kw}' detected")
                break

        # Path outside sandbox adds risk
        path = data.get("path") or data.get("payload", {}).get("path", "")
        if path and not _in_sandbox(str(path)):
            score += 2.0
            reasons.append(f"path '{path}' outside sandbox")

        score = min(10.0, score)
        category = _categorise(score)
        requires_confirmation = score >= self.CONFIRM_THRESHOLD

        return RiskAssessment(
            score=round(score, 2),
            category=category,
            requires_confirmation=requires_confirmation,
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _categorise(score: float) -> RiskCategory:
    if score < 2.0:
        return RiskCategory.SAFE
    if score < 4.0:
        return RiskCategory.LOW
    if score < 6.0:
        return RiskCategory.MEDIUM
    if score < 8.0:
        return RiskCategory.HIGH
    return RiskCategory.CRITICAL


def _flatten(data: dict, _depth: int = 0) -> str:
    if _depth > 5:
        return str(data)
    parts = []
    for v in data.values():
        if isinstance(v, dict):
            parts.append(_flatten(v, _depth + 1))
        elif isinstance(v, (list, tuple)):
            parts.append(" ".join(str(x) for x in v))
        else:
            parts.append(str(v))
    return " ".join(parts)


def _in_sandbox(path: str) -> bool:
    import os
    from pathlib import Path
    try:
        resolved = Path(path).expanduser().resolve()
        bases = [
            Path(os.environ.get("ACTION_WORKSPACE_PATH", "~/jarvis_workspace")).expanduser().resolve(),
            Path(os.environ.get("JARVIS_DATA_DIR", os.environ.get("MEMORY_DIR", os.environ.get("PERSISTENCE_DIR", "~/.jarvis_brain")))).expanduser().resolve(),
        ]
        if os.environ.get("JAV_PORTABLE", "false").lower() == "true":
            bases.append(Path(__file__).resolve().parents[2] / "data")
        for base in bases:
            try:
                resolved.relative_to(base)
                return True
            except ValueError:
                pass
    except Exception:
        pass
    return False
