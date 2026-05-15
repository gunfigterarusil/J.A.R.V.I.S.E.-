"""Tier 5: Personality Module
Tracks long-term personality traits (Big Five-like) and their evolution.
"""
from __future__ import annotations

import time
import logging
import random
from typing import Dict, Any, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("personality")


class PersonalityModule(CognitiveModule):
    """
    Maintains a personality profile and evolves it based on hormonal and emotional history.
    Emits: personality_snapshot, personality_changed, personality_insight
    """

    TRAITS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]

    def __init__(self) -> None:
        super().__init__(
            module_id="personality",
            cost={"cpu": 0.15, "gpu": 0.02, "ram": 0.10},
        )
        self._traits: Dict[str, float] = {
            trait: round(random.uniform(0.4, 0.8), 2) for trait in self.TRAITS
        }
        self._previous_traits: Dict[str, float] = dict(self._traits)
        self._trait_history: list = []  # {timestamp, traits}
        self._last_drift_time = 0.0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        self._load_persisted(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["hormone_levels", "emotion_changed", "mood_shift", "memory_stored"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "hormone_levels":
            data = event.data if isinstance(event.data, dict) else {}
            # Map hormones to traits
            self._nudge_trait("neuroticism", data.get("cortisol", 0.5), data.get("serotonin", 0.5), up=0.01, down=-0.01)
            self._nudge_trait("extraversion", data.get("dopamine", 0.5), 0.5, up=0.01, down=-0.008)
            self._nudge_trait("agreeableness", data.get("oxytocin", 0.5), 0.5, up=0.012, down=-0.01)
        elif event.type == "emotion_changed":
            valence = event.data.get("valence", 0.0) if isinstance(event.data, dict) else 0.0
            self._nudge_trait("openness", valence, 0.0, up=0.005, down=-0.003)
        elif event.type == "memory_stored":
            # Social memories influence agreeableness
            pass

    def _nudge_trait(self, trait: str, hormone_level: float, baseline: float, up: float, down: float) -> None:
        if trait not in self._traits:
            return
        if hormone_level > baseline + 0.2:
            self._traits[trait] += up
        elif hormone_level < baseline - 0.2:
            self._traits[trait] += down
        self._traits[trait] = round(max(0.0, min(1.0, self._traits[trait])), 3)

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_drift_time >= 10.0:
            self._last_drift_time = now
            # Natural drift towards baseline (towards 0.5)
            for trait in self.TRAITS:
                diff = 0.5 - self._traits[trait]
                self._traits[trait] += diff * 0.02  # very slow drift
                self._traits[trait] = round(max(0.0, min(1.0, self._traits[trait])), 3)

            # Check if any trait changed significantly (>0.05)
            for trait, value in self._traits.items():
                if abs(value - self._previous_traits.get(trait, value)) > 0.05:
                    if self.kernel:
                        self.kernel.event_bus.emit(
                            Event(
                                type="personality_changed",
                                data={"trait": trait, "value": value, "previous": self._previous_traits.get(trait)}
                            ),
                            Priority.BACKGROUND,
                        )
                        logger.info(f"[Personality] {trait} changed: {self._previous_traits.get(trait):.3f} -> {value:.3f}")
            self._previous_traits = dict(self._traits)
            self._trait_history.append({"timestamp": now, "traits": dict(self._traits)})

    def shutdown(self) -> None:
        if self.kernel:
            self.kernel.persistence.save("personality", {
                "traits": self._traits,
                "history": self._trait_history[-100:],
            })
            logger.info("[Personality] Traits saved to disk")

    def _load_persisted(self, kernel) -> None:
        data = kernel.persistence.load("personality")
        if data:
            self._traits = data.get("traits", self._traits)
            self._previous_traits = dict(self._traits)
            self._trait_history = data.get("history", [])
            logger.info(f"[Personality] Traits loaded from disk: {self._traits}")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["traits"] = self._traits
        base["history_entries"] = len(self._trait_history)
        return base


def create_module():
    return PersonalityModule()
