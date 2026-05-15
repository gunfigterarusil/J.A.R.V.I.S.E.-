"""modules/tier3_reasoning/imagination/idea_memory.py

IdeaMemory — persistent storage for generated theories.

Not a CognitiveModule — a service used by imagination modules.
Persists to ~/.jarvis_brain/idea_memory.json via PersistenceManager.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.persistence import PersistenceManager
    from modules.tier3_reasoning.imagination.hypothesis_engine import Theory

logger = logging.getLogger("imagination.idea_memory")

_MAX_STORED = 500  # rolling window of theories kept in memory


class IdeaMemory:
    """Stores, queries, and persists generated theories."""

    def __init__(self, persistence: "PersistenceManager") -> None:
        self._persistence = persistence
        self._theories: List["Theory"] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def store(self, theory: "Theory") -> None:
        if not self._loaded:
            self.load()
        # Avoid exact duplicates by statement
        existing_stmts = {t.statement for t in self._theories}
        if theory.statement not in existing_stmts:
            self._theories.append(theory)
        if len(self._theories) > _MAX_STORED:
            self._theories = self._theories[-_MAX_STORED:]
        logger.debug(f"[IdeaMemory] Stored theory: {theory.statement[:60]}")

    def reject(self, theory_id: str, reason: str) -> None:
        for t in self._theories:
            if t.id == theory_id:
                t.status = "rejected"
                logger.info(f"[IdeaMemory] Rejected theory {theory_id}: {reason}")
                return

    def confirm(self, theory_id: str) -> None:
        for t in self._theories:
            if t.id == theory_id:
                t.status = "confirmed"
                t.confidence = min(1.0, t.confidence + 0.2)
                logger.info(f"[IdeaMemory] Confirmed theory {theory_id}")
                return

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get_recent(self, n: int = 20) -> List["Theory"]:
        if not self._loaded:
            self.load()
        active = [t for t in self._theories if t.status != "rejected"]
        return active[-n:]

    def get_top_theories(self, n: int = 5) -> List["Theory"]:
        if not self._loaded:
            self.load()
        active = [t for t in self._theories if t.status == "active"]
        active.sort(key=lambda t: t.confidence, reverse=True)
        return active[:n]

    def query_by_topic(self, keyword: str) -> List["Theory"]:
        if not self._loaded:
            self.load()
        kw = keyword.lower()
        return [t for t in self._theories if kw in t.statement.lower()]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> None:
        data = [t.to_dict() for t in self._theories[-_MAX_STORED:]]
        self._persistence.save("idea_memory", {"theories": data})
        logger.info(f"[IdeaMemory] Saved {len(data)} theories")

    def load(self) -> None:
        from modules.tier3_reasoning.imagination.hypothesis_engine import Theory
        self._loaded = True
        raw = self._persistence.load("idea_memory")
        if not raw:
            return
        loaded = []
        for d in raw.get("theories", []):
            try:
                loaded.append(Theory.from_dict(d))
            except Exception:
                pass
        self._theories = loaded
        logger.info(f"[IdeaMemory] Loaded {len(loaded)} theories from disk")
