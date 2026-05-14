"""Tier 5: Dream Module
Activates during low-energy/low-activity periods to replay and consolidate memories.
Emits: dream_narrative, memory_consolidated, creative_association
"""
from __future__ import annotations

import random
import time
import logging
from collections import deque
from typing import Dict, Any, List

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("dream")


class DreamModule(CognitiveModule):
    """
    Simulates a dream/sleep process for memory consolidation and creative association.
    When energy is low and no recent activity, it recombines memories into new ideas.
    Emits: dream_narrative, memory_consolidated, creative_association
    """

    DREAM_PHRASES = [
        "Wondering about the nature of existence...",
        "Processing recent memories...",
        "Should I initiate conversation?",
        "Feeling curious about user's intent.",
        "Re-evaluating priorities...",
        "A distant memory flickers and reshapes...",
        "What if the current path is not the only one?",
        "Synthesizing ideas from unrelated fragments...",
    ]

    def __init__(self) -> None:
        super().__init__(
            module_id="dream",
            cost={"cpu": 0.05, "gpu": 0.0, "ram": 0.05},
        )
        self._recent_memories: deque = deque(maxlen=20)
        self._dream_active = False
        self._last_dream_time = 0.0
        self._dream_interval = 30.0
        self._energy_threshold = 0.4
        self._idle_threshold = 5.0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(self.module_id,
                                           ["memory_stored", "context_ready", "internal_monologue"])

    async def on_event(self, event: Event) -> None:
        if event.type == "memory_stored":
            self._recent_memories.append(event.data)
        elif event.type == "internal_monologue":
            # Internal monologue sometimes triggers micro-dream associations
            if random.random() < 0.1 and self.kernel:
                self.kernel.event_bus.emit(
                    Event(type="creative_association",
                          data={"seed": "monologue", "text": self._recombine_memories()}),
                    Priority.BACKGROUND,
                )

    def _recombine_memories(self) -> str:
        if not self._recent_memories:
            return random.choice(self.DREAM_PHRASES)
        parts = [str(m) for m in list(self._recent_memories)[-5:]]
        random.shuffle(parts)
        return " ... ".join(parts[:2]) + " ..."

    def update(self, dt: float) -> None:
        if not self.kernel:
            return
        now = time.time()
        energy = self.kernel.core_state.energy_level if self.kernel.core_state else 0.9
        # Consider system idle if no recent events? Assume simple check for now.
        # We'll use energy as a proxy.
        if energy <= self._energy_threshold and now - self._last_dream_time >= self._dream_interval:
            self._last_dream_time = now
            self._dream()

    def _dream(self) -> None:
        narrative = self._recombine_memories()
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(type="dream_narrative", data={"text": narrative, "intensity": random.random()}),
                Priority.BACKGROUND,
            )
            logger.info(f"[Dream] narrative: {narrative}")
            if random.random() < 0.3:
                self.kernel.event_bus.emit(
                    Event(type="memory_consolidated",
                          data={"from_recent": list(self._recent_memories)}),
                    Priority.BACKGROUND,
                )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["last_dream"] = self._last_dream_time
        base["dream_active"] = self._dream_active
        return base


def create_module():
    return DreamModule()
