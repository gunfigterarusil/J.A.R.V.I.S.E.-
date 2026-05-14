"""Tier 2: Vision Module
Simulates visual perception.
"""
from __future__ import annotations

import time
import logging
from typing import Dict, Any

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("vision")

VIRTUAL_OBJECTS = [
    {"label": "person", "confidence": 0.92, "bbox": [100, 200, 300, 600]},
    {"label": "laptop", "confidence": 0.87, "bbox": [400, 300, 700, 500]},
]


class VisionModule(CognitiveModule):
    def __init__(self) -> None:
        super().__init__(
            module_id="vision",
            cost={"cpu": 0.20, "gpu": 0.30, "ram": 0.15},
        )
        self._last_emit = 0.0
        self._period = 2.0  # 0.5 Hz

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["vision_focus", "efference_copy"],
        )

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_emit >= self._period:
            self._last_emit = now
            event = Event(
                type="object_detected",
                data={
                    "timestamp": now,
                    "objects": VIRTUAL_OBJECTS,
                },
            )
            if self.kernel:
                self.kernel.event_bus.emit(event, Priority.COGNITIVE)
                logger.info("[Vision] object_detected emitted")

    async def on_event(self, event: Event) -> None:
        if event.type == "vision_focus":
            self._period = 0.5
            logger.info("[Vision] focus detected, increasing frequency")
        elif event.type == "efference_copy":
            logger.info("[Vision] efference_copy received, suppressing predicted")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["period"] = self._period
        return base


def create_module():
    return VisionModule()
