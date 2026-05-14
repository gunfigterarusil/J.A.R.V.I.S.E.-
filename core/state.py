"""core/state.py — CoreState and SubjectiveField.

CoreState is the shared read model of the brain's current condition.
Modules write into it via patch(); the kernel and web UI read from it.
It is NOT an event bus — modules should still communicate via events.
CoreState is a live snapshot for introspection and context injection.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SubjectiveField:
    """Slow-moving phenomenal background state."""
    safety: float = 0.7
    social_warmth: float = 0.5
    mental_overload: float = 0.0
    motivation: float = 0.8
    boredom: float = 0.0
    last_update: float = field(default_factory=time.time)

    def update_delta(self, dt: float, changes: dict) -> None:
        import math
        now = time.time()
        elapsed = now - self.last_update
        for key, delta in changes.items():
            if hasattr(self, key):
                current = getattr(self, key)
                factor = 1.0 - math.exp(-elapsed) if elapsed > 0 else 0.0
                new_val = max(0.0, min(1.0, current + delta * factor))
                setattr(self, key, new_val)
        self.last_update = now

    def to_dict(self) -> dict:
        return {
            "safety": self.safety,
            "social_warmth": self.social_warmth,
            "mental_overload": self.mental_overload,
            "motivation": self.motivation,
            "boredom": self.boredom,
        }


@dataclass
class CoreState:
    """Rich live snapshot of the cognitive brain's current state.

    Modules update this each tick via `patch()`.
    The kernel checkpoints it via PersistenceManager.
    """
    # --- consciousness / energy ---
    consciousness_level: float = 0.8
    energy_level: float = 0.9

    # --- attention ---
    active_focus: list = field(default_factory=list)   # strings: what is attended to
    cognitive_load: float = 0.0                         # 0..1

    # --- active cognition ---
    active_modules: list = field(default_factory=list)
    active_goals: list = field(default_factory=list)       # top goal IDs from GoalModule
    active_thoughts: list = field(default_factory=list)    # current thought strings
    working_memory_snapshot: list = field(default_factory=list)  # from WorkingMemoryModule

    # --- affective state ---
    emotional_state: dict = field(default_factory=dict)   # from EmotionModule: {valence, arousal, dominance, label}
    hormone_state: dict = field(default_factory=dict)     # from HormoneModule: {dopamine, cortisol, …}

    # --- metacognitive ---
    uncertainty: float = 0.0     # 0..1 — how uncertain the brain is right now
    attachment_state: float = 0.5  # from SelfModel — relationship with user

    # --- temporal ---
    temporal_marker: float = field(default_factory=time.time)  # from TemporalEngine
    uptime: float = 0.0

    # --- cognition depth ---
    thinking_mode: int = 1                          # current ThinkingMode value (REACTIVE)
    active_theories: list = field(default_factory=list)  # Theory IDs from imagination engine
    imagination_active: bool = False                # True while imagination cycle is running

    # --- safety ---
    safety_level: int = 1                              # current PermissionLevel value (L1_READ_SCREEN)
    pending_confirmations: list = field(default_factory=list)  # action_types awaiting user Y/N
    last_violation: Optional[str] = None               # last constitution rule that fired

    # --- kernel bookkeeping ---
    timestamp: float = field(default_factory=time.time)

    def update(self, timestamp: Optional[float] = None) -> None:
        self.timestamp = timestamp or time.time()

    def patch(self, updates: dict[str, Any]) -> None:
        """Atomically update multiple fields. Ignores unknown keys."""
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict:
        return {
            "consciousness_level": self.consciousness_level,
            "energy_level": self.energy_level,
            "active_focus": list(self.active_focus),
            "cognitive_load": self.cognitive_load,
            "active_modules": list(self.active_modules),
            "active_goals": list(self.active_goals),
            "active_thoughts": list(self.active_thoughts),
            "working_memory_snapshot": list(self.working_memory_snapshot),
            "emotional_state": dict(self.emotional_state),
            "hormone_state": dict(self.hormone_state),
            "uncertainty": self.uncertainty,
            "attachment_state": self.attachment_state,
            "temporal_marker": self.temporal_marker,
            "uptime": self.uptime,
            "timestamp": self.timestamp,
            "thinking_mode": self.thinking_mode,
            "active_theories": list(self.active_theories),
            "imagination_active": self.imagination_active,
            "safety_level": self.safety_level,
            "pending_confirmations": list(self.pending_confirmations),
            "last_violation": self.last_violation,
        }
