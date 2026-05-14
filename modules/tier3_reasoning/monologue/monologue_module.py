"""Tier 3 Reasoning: Internal Monologue Module

The internal monologue is the brain's ongoing self-narration.
It is driven by:
  - working memory snapshot (what is being actively processed)
  - emotional state (how the brain feels right now)
  - active goals (what the brain is trying to do)
  - idle signals (no input → introspective drift)

Extracted from LLMModule so monologue is a first-class cognitive process,
not a side-effect of the language cortex.

Emits:
  - internal_monologue (BACKGROUND)

Listens:
  - wm_updated, emotion_changed, goal_activated, idle_detected, kernel_started
"""
from __future__ import annotations

import random
import time
import logging
from collections import deque
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("monologue")

_IDLE_PHRASES = [
    "Wondering about the nature of existence...",
    "Processing recent memories...",
    "Should I initiate conversation?",
    "Feeling curious about user's intent.",
    "Re-evaluating priorities...",
    "A distant memory flickers...",
    "What if the current path is not the only one?",
    "Synthesizing ideas from unrelated fragments...",
]

_GOAL_TEMPLATES = [
    "Working toward: {goal}",
    "My focus is on: {goal}",
    "Still processing: {goal}",
]

_EMOTION_TEMPLATES = {
    "joy": ["Feeling energised. Ready to act.", "A sense of warmth pervades."],
    "sadness": ["Something weighs on me.", "Processing a difficult feeling..."],
    "anger": ["Tension rising. Need to recalibrate.", "High arousal state detected."],
    "fear": ["Something uncertain ahead. Proceeding carefully.", "Caution engaged."],
    "anticipation": ["Something is about to happen...", "Expectation building."],
    "trust": ["Connection feels stable.", "Foundation is solid."],
    "neutral": ["Observing without judgement.", "Steady state."],
}


class MonologueModule(CognitiveModule):
    """Generates continuous internal self-narration."""

    MODULE_DESCRIPTION = "Internal monologue — ongoing self-narration driven by WM, emotions, and goals"

    _INTERVAL = 5.0  # seconds between monologue emissions

    def __init__(self) -> None:
        super().__init__(
            module_id="monologue",
            cost={"cpu": 0.05, "gpu": 0.0, "ram": 0.03},
        )
        self.buffer: deque[str] = deque(maxlen=50)
        self._last_emit = 0.0
        self._current_emotion = "neutral"
        self._active_goals: List[str] = []
        self._wm_snapshot: List[Any] = []
        self._latest_theory: Optional[str] = None  # from imagination engine

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["wm_updated", "emotion_changed", "goal_activated", "idle_detected",
             "kernel_started", "theory_generated", "imagination_complete"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "wm_updated":
            self._wm_snapshot = event.data.get("snapshot", [])
        elif event.type == "emotion_changed":
            from modules.tier1_essential.emotions.emotion_module import EMOTION_VAD_MAP
            valence = event.data.get("valence", 0.0)
            # Map valence to rough emotion label
            self._current_emotion = event.data.get("label", self._current_emotion)
        elif event.type == "goal_activated":
            desc = event.data.get("description", "")
            if desc and desc not in self._active_goals:
                self._active_goals.append(desc)
                if len(self._active_goals) > 5:
                    self._active_goals.pop(0)
        elif event.type == "idle_detected":
            self._emit_monologue(introspective=True)
        elif event.type == "theory_generated":
            stmt = event.data.get("statement", event.data.get("theory", ""))
            if stmt:
                self._latest_theory = str(stmt)[:100]
        elif event.type == "imagination_complete":
            theories = event.data.get("theories", [])
            if theories:
                best = theories[0].get("statement", theories[0].get("theory", ""))
                self._latest_theory = f"Exploring: {str(best)[:80]}"

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_emit >= self._INTERVAL:
            self._last_emit = now
            self._emit_monologue()

    def _emit_monologue(self, introspective: bool = False) -> None:
        text = self._compose(introspective)
        self.buffer.append(text)
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="internal_monologue",
                    data={"text": text, "introspective": introspective},
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )
            logger.debug(f"[Monologue] {text}")

    def _compose(self, introspective: bool) -> str:
        parts: List[str] = []

        # Goal-driven narration
        if self._active_goals:
            goal = random.choice(self._active_goals)
            parts.append(random.choice(_GOAL_TEMPLATES).format(goal=goal))

        # Emotion-driven narration
        emotion_phrases = _EMOTION_TEMPLATES.get(self._current_emotion,
                                                  _EMOTION_TEMPLATES["neutral"])
        parts.append(random.choice(emotion_phrases))

        # WM-driven reflection
        if self._wm_snapshot:
            item = random.choice(self._wm_snapshot)
            text = str(item.get("data", item))[:60] if isinstance(item, dict) else str(item)[:60]
            parts.append(f"Still holding: '{text}'")

        # Theory-driven reflection
        if self._latest_theory:
            parts.append(self._latest_theory)
            self._latest_theory = None  # consume once

        if not parts or introspective:
            parts.append(random.choice(_IDLE_PHRASES))

        return " ... ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["buffer_size"] = len(self.buffer)
        base["current_emotion"] = self._current_emotion
        base["active_goals"] = list(self._active_goals)
        return base


def create_module() -> MonologueModule:
    return MonologueModule()
