"""core/safety/audit_log.py — Append-only audit log for all action attempts.

Every action that passes through the ActionFirewall is recorded here,
regardless of the outcome (approved / denied / pending).
The log is append-only: entries are never deleted or modified.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("core.safety.audit")


@dataclass
class AuditEntry:
    timestamp: float
    action_type: str
    source_module: str
    data_summary: str        # truncated, no secrets
    decision: str            # "approved" | "denied" | "pending"
    risk_score: float
    rule_violated: Optional[str]
    confirm_required: bool
    rule_type: str = "technical"   # "technical" | "ethical"
    friendly_reason: str = ""      # human-readable reason shown in UI


class AuditLog:
    """Append-only JSONL audit log written to base_dir/audit.jsonl."""

    def __init__(self, base_dir: Path) -> None:
        self._path = Path(base_dir) / "audit.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: List[AuditEntry] = []   # in-memory copy of recent entries

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def record(self, entry: AuditEntry) -> None:
        self._cache.append(entry)
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
        except Exception as exc:
            logger.error(f"[AuditLog] Failed to write entry: {exc}")

    # ------------------------------------------------------------------
    # Query (reads from in-memory cache; falls back to disk on cold start)
    # ------------------------------------------------------------------
    def query_recent(self, n: int = 50) -> List[AuditEntry]:
        if not self._cache:
            self._load_from_disk()
        return list(self._cache[-n:])

    def query_violations(self) -> List[AuditEntry]:
        if not self._cache:
            self._load_from_disk()
        return [e for e in self._cache if e.rule_violated]

    def query_by_module(self, module_id: str) -> List[AuditEntry]:
        if not self._cache:
            self._load_from_disk()
        return [e for e in self._cache if e.source_module == module_id]

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        self._cache.append(AuditEntry(**d))
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning(f"[AuditLog] Could not load audit log from disk: {exc}")
