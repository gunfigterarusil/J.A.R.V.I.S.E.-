"""Tier 1 Essential: Self Model Module

The SelfModel gives the brain an internal representation of who it is.
This is the cognitive foundation for identity continuity across restarts,
consistent personality, and coherent self-narration.

State persists to ~/.jarvis_brain/self_model.json

The self model feeds LLMModule as the "who I am" context block injected
into every reasoning prompt.

Emits:
  - self_model_updated (BACKGROUND) — full snapshot for LLM context injection

Listens:
  - personality_changed, learning_applied, goal_achieved, goal_failed,
    emotion_changed, kernel_started
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("self_model")

_SNAPSHOT_INTERVAL = 30.0  # seconds between self_model_updated emissions


class SelfModelModule(CognitiveModule):
    """Internal model of the brain's identity, capabilities, and relationship state."""

    MODULE_DESCRIPTION = "Self model — persistent identity, capabilities, confidence, and attachment"

    def __init__(self) -> None:
        super().__init__(
            module_id="self_model",
            cost={"cpu": 0.04, "gpu": 0.0, "ram": 0.04},
        )
        # Core identity
        self.identity_name: str = "Jarvis"
        self.role: str = "persistent cognitive assistant"
        self.communication_style: str = "direct and warm"
        self.identity_version: int = 1

        # Dynamic state
        self.confidence: float = 0.7          # 0..1
        self.attachment_level: float = 0.5    # to the primary user, 0..1
        self.capabilities: List[str] = [
            "memory recall",
            "goal tracking",
            "emotional awareness",
            "contextual reasoning",
            "screen perception",
            "voice interaction",
        ]

        # History
        self._goal_success_count = 0
        self._goal_fail_count = 0
        self._last_snapshot = 0.0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "personality_changed",
                "learning_applied",
                "goal_achieved",
                "goal_failed",
                "emotion_changed",
                "kernel_started",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "kernel_started":
            self._load()
        elif event.type == "goal_achieved":
            self._goal_success_count += 1
            self.confidence = min(1.0, self.confidence + 0.01)
        elif event.type == "goal_failed":
            self._goal_fail_count += 1
            self.confidence = max(0.1, self.confidence - 0.01)
        elif event.type == "learning_applied":
            # Learning events slowly build capability confidence
            self.confidence = min(1.0, self.confidence + 0.005)
        elif event.type == "emotion_changed":
            valence = event.data.get("valence", 0.0)
            # Positive interactions strengthen attachment
            if valence > 0.3:
                self.attachment_level = min(1.0, self.attachment_level + 0.005)
            elif valence < -0.5:
                self.attachment_level = max(0.0, self.attachment_level - 0.003)
        elif event.type == "personality_changed":
            trait = event.data.get("trait", "")
            value = event.data.get("value", 0.5)
            if trait == "extraversion":
                self.communication_style = "outgoing and expressive" if value > 0.6 else "direct and warm"

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_snapshot >= _SNAPSHOT_INTERVAL and self.kernel:
            self._last_snapshot = now
            snap = self._build_snapshot()
            # Push attachment to CoreState
            self.kernel.core_state.patch({"attachment_state": self.attachment_level})
            self.kernel.event_bus.emit(
                Event(
                    type="self_model_updated",
                    data=snap,
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )

    def _build_snapshot(self) -> Dict[str, Any]:
        total = max(1, self._goal_success_count + self._goal_fail_count)
        return {
            "identity_name": self.identity_name,
            "role": self.role,
            "communication_style": self.communication_style,
            "identity_version": self.identity_version,
            "confidence": round(self.confidence, 3),
            "attachment_level": round(self.attachment_level, 3),
            "capabilities": list(self.capabilities),
            "goal_success_rate": round(self._goal_success_count / total, 3),
            "timestamp": time.time(),
        }

    def shutdown(self) -> None:
        self._save()

    def _save(self) -> None:
        if self.kernel:
            data = self._build_snapshot()
            data["identity_version"] = self.identity_version + 1
            self.kernel.persistence.save("self_model", data)
            logger.info("[SelfModel] Identity saved to disk")

    def _load(self) -> None:
        if self.kernel:
            data = self.kernel.persistence.load("self_model")
            if data:
                self.identity_name = data.get("identity_name", self.identity_name)
                self.role = data.get("role", self.role)
                self.communication_style = data.get("communication_style", self.communication_style)
                self.identity_version = data.get("identity_version", self.identity_version)
                self.confidence = data.get("confidence", self.confidence)
                self.attachment_level = data.get("attachment_level", self.attachment_level)
                self.capabilities = data.get("capabilities", self.capabilities)
                logger.info(f"[SelfModel] Identity loaded: {self.identity_name} v{self.identity_version}")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(self._build_snapshot())
        return base


def create_module() -> SelfModelModule:
    return SelfModelModule()
