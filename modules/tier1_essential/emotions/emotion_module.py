"""Tier 1: Emotion Module

Maps hormone levels to discrete emotions and vice versa.
Emotions: joy, sadness, anger, fear, surprise, disgust, anticipation, trust
Valence/Arousal/Dominance mapping.

Emits events:
- "emotion_changed" (COGNITIVE) - when valence shifts > 0.2
- "mood_shift" (BACKGROUND)     - gradual mood drift
- "emotional_tag" (COGNITIVE)   - attaches emotion to events for memory

Listens: "hormone_levels", "sensory_input", "memory_retrieved",
          "goal_achieved", "goal_failed"
"""
from __future__ import annotations

import math
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("emotion")

EMOTION_VAD_MAP: Dict[str, Dict[str, List[float]]] = {
    "joy": {"valence": [0.6, 1.0], "arousal": [0.5, 1.0], "dominance": [0.4, 1.0]},
    "sadness": {"valence": [-1.0, -0.2], "arousal": [0.0, 0.4], "dominance": [0.0, 0.3]},
    "anger": {"valence": [-1.0, -0.2], "arousal": [0.7, 1.0], "dominance": [0.5, 1.0]},
    "fear": {"valence": [-1.0, -0.2], "arousal": [0.6, 1.0], "dominance": [0.0, 0.3]},
    "surprise": {"valence": [-0.2, 0.4], "arousal": [0.6, 1.0], "dominance": [0.3, 0.7]},
    "disgust": {"valence": [-0.8, -0.2], "arousal": [0.4, 0.7], "dominance": [0.0, 1.0]},
    "anticipation": {"valence": [0.2, 0.7], "arousal": [0.5, 0.9], "dominance": [0.3, 0.7]},
    "trust": {"valence": [0.5, 1.0], "arousal": [0.3, 1.0], "dominance": [0.4, 1.0]},
}

# Mapping from hormone names to their emotional weight vectors
HORMONE_EMO_WEIGHTS: Dict[str, Dict[str, float]] = {
    "dopamine": {"valence": 0.5, "arousal": 0.3, "dominance": 0.2},
    "cortisol": {"valence": -0.6, "arousal": 0.5, "dominance": -0.3},
    "oxytocin": {"valence": 0.5, "arousal": 0.0, "dominance": 0.1},
    "serotonin": {"valence": 0.3, "arousal": -0.1, "dominance": 0.1},
    "adrenaline": {"valence": -0.2, "arousal": 0.8, "dominance": -0.2},
}


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class EmotionModule(CognitiveModule):
    """
    Tier 1: Emotion Engine
    Maintains VAD vector, computes discrete emotions from VAD or hormones,
    emits events when significant changes occur.
    """

    def __init__(self) -> None:
        super().__init__(
            module_id="emotion_module",
            cost={"cpu": 0.12, "gpu": 0.0, "ram": 0.08},
        )
        self._kernel: Optional["Kernel"] = None
        # VAD state
        self._valence = 0.0
        self._arousal = 0.0
        self._dominance = 0.0
        # Mood (slowly-shifting background VAD)
        self._mood_valence = 0.0
        self._mood_arousal = 0.0
        self._mood_dominance = 0.0
        # Tracking
        self._last_valence = 0.0
        self._last_triggers: List[str] = []
        self._last_mood_shift_time = 0.0
        self._mood_shift_interval = 10.0

    def initialize(self, kernel: "Kernel") -> None:
        super().initialize(kernel)
        self._kernel = kernel
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "hormone_levels",
                "sensory_input",
                "memory_retrieved",
                "goal_achieved",
                "goal_failed",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if not self._kernel:
            return
        new_valence = 0.0
        new_arousal = 0.0
        new_dominance = 0.0
        if event.type == "hormone_levels":
            new_valence, new_arousal, new_dominance = self._compute_vad_from_hormones(event.data)
        elif event.type == "sensory_input":
            valence, arousal, dominance = self._compute_vad_from_sensory(event.data)
            new_valence += valence
            new_arousal += arousal
            new_dominance += dominance
        elif event.type == "memory_retrieved":
            valence, arousal, dominance = self._compute_vad_from_memory(event.data)
            new_valence += valence
            new_arousal += arousal
            new_dominance += dominance
        elif event.type == "goal_achieved":
            new_valence += 0.5
            new_arousal += 0.3
            self._last_triggers.append("goal_achieved")
        elif event.type == "goal_failed":
            new_valence -= 0.5
            new_arousal += 0.2
            self._last_triggers.append("goal_failed")

        self._update_vad(new_valence, new_arousal, new_dominance)

        # Emit if valence shifted significantly
        valence_delta = abs(self._valence - self._last_valence)
        if valence_delta > 0.2:
            self._kernel.event_bus.emit(
                Event(
                    type="emotion_changed",
                    data={
                        "valence": self._valence,
                        "arousal": self._arousal,
                        "dominance": self._dominance,
                        "delta": valence_delta,
                    },
                ),
                Priority.COGNITIVE,
            )
            self._last_valence = self._valence

        # Emit emotional tag for memory
        emotional_tag = self._dominant_emotion()
        self._kernel.event_bus.emit(
            Event(
                type="emotional_tag",
                data={
                    "target_event": event.type,
                    "tag": emotional_tag,
                    "valence": self._valence,
                    "arousal": self._arousal,
                },
            ),
            Priority.COGNITIVE,
        )

    def _compute_vad_from_hormones(self, data: Dict[str, Any]) -> Tuple[float, float, float]:
        hormones = data if isinstance(data, dict) else {}
        valence = 0.0
        arousal = 0.0
        dominance = 0.0
        for hormone, level in hormones.items():
            if hormone in HORMONE_EMO_WEIGHTS:
                valence += HORMONE_EMO_WEIGHTS[hormone]["valence"] * level
                arousal += HORMONE_EMO_WEIGHTS[hormone]["arousal"] * level
                dominance += HORMONE_EMO_WEIGHTS[hormone]["dominance"] * level
        valence = _clamp(valence)
        arousal = _clamp(arousal)
        dominance = _clamp(dominance)
        return valence, arousal, dominance

    def _compute_vad_from_sensory(self, data: Dict[str, Any]) -> Tuple[float, float, float]:
        # Simple heuristic based on data intensity and valence hints
        intensity = data.get("intensity", 0.0)
        valence_hint = data.get("valence_hint", 0.0)
        return valence_hint * intensity, intensity * 0.5, intensity * 0.2

    def _compute_vad_from_memory(self, data: Dict[str, Any]) -> Tuple[float, float, float]:
        # memories can be positive or negative based on emotional content
        valence = 0.0
        arousal = 0.0
        if "episodic_recalls" in data:
            for mem in data["episodic_recalls"]:
                if not isinstance(mem, dict):
                    continue
                exp = mem.get("experience", mem)
                if isinstance(exp, dict):
                    valence += float(exp.get("importance", mem.get("importance", 0.0)) or 0.0) * 0.1
                    tags = exp.get("emotion_tags", mem.get("emotion_tags", [])) or []
                else:
                    tags = []
                if isinstance(tags, list):
                    arousal += len(tags) * 0.1
                elif tags:
                    arousal += 0.1
        return _clamp(valence), _clamp(arousal), 0.0

    def _update_vad(self, d_valence: float, d_arousal: float, d_dominance: float) -> None:
        # Update VAD with some inertia
        self._valence = _clamp(self._valence * 0.8 + d_valence * 0.2)
        self._arousal = _clamp(self._arousal * 0.8 + d_arousal * 0.2)
        self._dominance = _clamp(self._dominance * 0.8 + d_dominance * 0.2)

    def _dominant_emotion(self) -> str:
        """Find discrete emotion closest to current VAD."""
        best = "neutral"
        best_score = -1.0
        for emotion, ranges in EMOTION_VAD_MAP.items():
            val_mid = sum(ranges["valence"]) / 2.0
            aro_mid = sum(ranges["arousal"]) / 2.0
            dom_mid = sum(ranges["dominance"]) / 2.0
            dist = math.sqrt(
                (self._valence - val_mid) ** 2
                + (self._arousal - aro_mid) ** 2
                + (self._dominance - dom_mid) ** 2
            )
            score = 1.0 / (1.0 + dist)
            if score > best_score:
                best_score = score
                best = emotion
        return best

    def update(self, dt: float) -> None:
        # Mood drift: slowly shift mood toward current VAD state
        alpha = 0.01
        self._mood_valence += (self._valence - self._mood_valence) * alpha
        self._mood_arousal += (self._arousal - self._mood_arousal) * alpha
        self._mood_dominance += (self._dominance - self._mood_dominance) * alpha

        # Emit mood shift periodically
        now = time.time()
        if self._kernel and (now - self._last_mood_shift_time > self._mood_shift_interval):
            self._last_mood_shift_time = now
            self._kernel.event_bus.emit(
                Event(
                    type="mood_shift",
                    data={
                        "mood_valence": self._mood_valence,
                        "mood_arousal": self._mood_arousal,
                        "mood_dominance": self._mood_dominance,
                    },
                ),
                Priority.BACKGROUND,
            )

    def shutdown(self) -> None:
        pass

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["emotions"] = {
            "dominant": self._dominant_emotion(),
            "valence": self._valence,
            "arousal": self._arousal,
            "dominance": self._dominance,
        }
        base["mood_vector"] = {
            "valence": self._mood_valence,
            "arousal": self._mood_arousal,
            "dominance": self._mood_dominance,
        }
        base["last_triggers"] = self._last_triggers[-10:]
        return base


def create_module():
    return EmotionModule()
