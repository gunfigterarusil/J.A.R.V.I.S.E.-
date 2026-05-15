"""Tier 2: Audio Module
Simulates audio perception (e.g., microphone input, speech detection).
"""
from __future__ import annotations

import os
import time
import logging
from typing import Dict, Any

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("audio")

VIRTUAL_AUDIO = [
    {"type": "speech", "text": "Hello", "confidence": 0.95},
    {"type": "noise", "level": 0.3},
]


class AudioModule(CognitiveModule):
    def __init__(self) -> None:
        super().__init__(
            module_id="audio",
            cost={"cpu": 0.10, "gpu": 0.05, "ram": 0.08},
        )
        self._last_emit = 0.0
        self._period = 1.5  # ~0.67 Hz
        self._simulation_enabled = os.environ.get("AUDIO_SIMULATION_ENABLED", "false").lower() == "true"

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["audio_focus", "efference_copy"],
        )

    def update(self, dt: float) -> None:
        now = time.time()
        if not self._simulation_enabled:
            return
        if now - self._last_emit >= self._period:
            self._last_emit = now
            event = Event(
                type="audio_detected",
                data={
                    "timestamp": now,
                    "streams": VIRTUAL_AUDIO,
                },
            )
            if self.kernel:
                self.kernel.event_bus.emit(event, Priority.COGNITIVE)
                logger.info("[Audio] audio_detected emitted")

    async def on_event(self, event: Event) -> None:
        if event.type == "audio_focus":
            self._period = 0.5
            logger.info("[Audio] focus detected, increasing frequency")
        elif event.type == "efference_copy":
            logger.info("[Audio] efference_copy received, suppressing predicted")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["period"] = self._period
        base["simulation_enabled"] = self._simulation_enabled
        return base


def create_module():
    return AudioModule()
