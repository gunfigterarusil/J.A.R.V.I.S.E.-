"""Tier 1 Essential: Working Memory Module

Working Memory is ACTIVE cognition memory — not storage, not a database.
It holds what the brain is currently processing: the 7-slot (±2) buffer of
the most important active items.

This is the "current thought space" that feeds:
  - LLM context assembly
  - Goal relevance filtering
  - Monologue generation
  - Attention scoring

Logic extracted from MemoryModule so WM is a first-class cognitive system.

Emits:
  - wm_updated  (COGNITIVE) — snapshot of current working memory
  - wm_overflow (BACKGROUND) — when eviction happened

Listens:
  - thought_generated, sensory_input, user_utterance,
    memory_stored, goal_activated, context_ready
"""
from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("working_memory")

WM_SLOTS = 7
_EMIT_INTERVAL = 1.0  # seconds between wm_updated emissions


class WorkingMemorySlot:
    def __init__(self, item: Any, importance: float, source: str) -> None:
        self.item = item
        self.importance = importance
        self.source = source
        self.timestamp = time.time()
        self.access_count = 0

    def access(self) -> None:
        self.access_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item": self.item,
            "importance": self.importance,
            "source": self.source,
            "age": time.time() - self.timestamp,
            "access_count": self.access_count,
        }


class WorkingMemoryModule(CognitiveModule):
    """7-slot active cognition buffer."""

    MODULE_DESCRIPTION = "Working memory — 7-slot active cognition buffer, current thought space"

    def __init__(self) -> None:
        super().__init__(
            module_id="working_memory",
            cost={"cpu": 0.06, "gpu": 0.0, "ram": 0.05},
        )
        self._slots: List[WorkingMemorySlot] = []
        self._last_emit = 0.0
        self._eviction_count = 0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "thought_generated",
                "sensory_input",
                "user_utterance",
                "memory_stored",
                "goal_activated",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "user_utterance":
            text = event.data.get("text", "")
            self.insert({"type": "utterance", "text": text}, importance=0.8,
                        source="user")
        elif event.type == "thought_generated":
            text = event.data.get("text", "")
            self.insert({"type": "thought", "text": text}, importance=0.6,
                        source="llm")
        elif event.type == "goal_activated":
            self.insert(event.data, importance=0.75, source="goals")
        elif event.type == "sensory_input":
            intensity = event.data.get("intensity", 0.0)
            if intensity > 0.5:
                self.insert(event.data, importance=intensity * 0.6, source="perception")
        elif event.type == "memory_stored":
            # Low-importance passive store — only if WM has room
            if len(self._slots) < WM_SLOTS:
                self.insert(event.data, importance=0.2, source="memory")

    def insert(self, item: Any, importance: float, source: str = "") -> Optional[Dict]:
        """Insert item into WM. Returns evicted item dict or None."""
        evicted = None
        if len(self._slots) >= WM_SLOTS:
            # Evict lowest importance
            self._slots.sort(key=lambda s: s.importance)
            evicted_slot = self._slots.pop(0)
            evicted = evicted_slot.to_dict()
            self._eviction_count += 1

            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="wm_overflow",
                        data={"evicted": evicted, "eviction_count": self._eviction_count},
                        source_module=self.module_id,
                    ),
                    Priority.BACKGROUND,
                )

        self._slots.append(WorkingMemorySlot(item, importance, source))
        return evicted

    def snapshot(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._slots]

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_emit >= _EMIT_INTERVAL:
            self._last_emit = now
            snap = self.snapshot()
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="wm_updated",
                        data={"snapshot": snap, "slot_count": len(self._slots)},
                        source_module=self.module_id,
                    ),
                    Priority.COGNITIVE,
                )
            # Push to CoreState
            if self.kernel:
                self.kernel.core_state.patch({
                    "working_memory_snapshot": snap,
                    "active_thoughts": [
                        s["item"].get("text", str(s["item"]))
                        if isinstance(s["item"], dict) else str(s["item"])
                        for s in snap[:3]
                    ],
                })

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["slots_used"] = len(self._slots)
        base["slots_max"] = WM_SLOTS
        base["eviction_count"] = self._eviction_count
        base["snapshot"] = self.snapshot()
        return base


def create_module() -> WorkingMemoryModule:
    return WorkingMemoryModule()
