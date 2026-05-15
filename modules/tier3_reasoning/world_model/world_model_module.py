"""Tier 3 Reasoning: World Model Module

Builds a persistent model of the user's patterns, habits, and causal relations.
The brain should eventually become *predictive* rather than reactive.

Stores observed patterns as:
  { context_key: { frequency, last_seen, outcomes: {outcome: count}, confidence } }

Persists to ~/.jarvis_brain/world_model.json

Emits:
  - pattern_detected   (BACKGROUND) — when a pattern exceeds frequency threshold
  - world_model_updated (BACKGROUND) — periodic snapshot

Listens:
  - user_utterance, memory_stored, goal_achieved, goal_failed,
    emotion_changed, kernel_started
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("world_model")

_PATTERN_THRESHOLD = 3   # minimum occurrences before emitting pattern_detected
_SNAPSHOT_INTERVAL = 60.0  # seconds between world_model_updated emissions


class WorldModelModule(CognitiveModule):
    """Persistent model of user patterns and causal relations."""

    MODULE_DESCRIPTION = "World model — tracks user habits, patterns, and causal relations"

    def __init__(self) -> None:
        super().__init__(
            module_id="world_model",
            cost={"cpu": 0.08, "gpu": 0.0, "ram": 0.10},
        )
        # context_key → {frequency, last_seen, outcomes, confidence}
        self._patterns: Dict[str, Dict[str, Any]] = {}
        self._last_snapshot = 0.0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "user_utterance",
                "memory_stored",
                "goal_achieved",
                "goal_failed",
                "emotion_changed",
                "kernel_started",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "kernel_started":
            self._load()
        elif event.type == "user_utterance":
            text = event.data.get("text", "")
            if text:
                key = self._normalise_key(text)
                self._observe(key, outcome="utterance")
        elif event.type == "goal_achieved":
            desc = event.data.get("description", "goal")
            self._observe(self._normalise_key(desc), outcome="success")
        elif event.type == "goal_failed":
            desc = event.data.get("description", "goal")
            self._observe(self._normalise_key(desc), outcome="failure")
        elif event.type == "emotion_changed":
            label = event.data.get("label", "")
            if label:
                self._observe(f"emotion:{label}", outcome="observed")

    def _normalise_key(self, text: str) -> str:
        words = text.lower().split()[:5]
        return "_".join(w for w in words if len(w) > 2)

    def _observe(self, key: str, outcome: str) -> None:
        if not key:
            return
        entry = self._patterns.setdefault(key, {
            "frequency": 0,
            "last_seen": 0.0,
            "outcomes": {},
            "confidence": 0.0,
        })
        entry["frequency"] += 1
        entry["last_seen"] = time.time()
        entry["outcomes"][outcome] = entry["outcomes"].get(outcome, 0) + 1
        total = entry["frequency"]
        entry["confidence"] = min(1.0, total / 10.0)

        if entry["frequency"] == _PATTERN_THRESHOLD and self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="pattern_detected",
                    data={"key": key, "entry": entry},
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )
            logger.info(f"[WorldModel] Pattern detected: {key} (freq={total})")

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_snapshot >= _SNAPSHOT_INTERVAL and self.kernel:
            self._last_snapshot = now
            self.kernel.event_bus.emit(
                Event(
                    type="world_model_updated",
                    data={"pattern_count": len(self._patterns)},
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )

    def shutdown(self) -> None:
        self._save()

    def _save(self) -> None:
        if self.kernel:
            self.kernel.persistence.save("world_model", self._patterns)
            logger.info("[WorldModel] Saved to disk")

    def _load(self) -> None:
        if self.kernel:
            data = self.kernel.persistence.load("world_model")
            if data:
                self._patterns = data
                logger.info(f"[WorldModel] Loaded {len(data)} patterns from disk")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["pattern_count"] = len(self._patterns)
        top = sorted(self._patterns.items(),
                     key=lambda x: x[1]["frequency"], reverse=True)[:5]
        base["top_patterns"] = [{"key": k, "freq": v["frequency"]} for k, v in top]
        return base


def create_module() -> WorldModelModule:
    return WorldModelModule()
