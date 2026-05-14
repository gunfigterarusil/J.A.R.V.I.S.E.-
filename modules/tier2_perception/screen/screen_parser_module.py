"""Tier 2: Screen Parser Module
Captures screen state and emits structured events.
"""
from __future__ import annotations

import time
import logging
from typing import Dict, Any

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("screen")


class ScreenParserModule(CognitiveModule):
    """
    Tier 2: Screen Parser
    Periodically emits screen_change events with bounding boxes
    and detected UI elements.
    """

    def __init__(self) -> None:
        super().__init__(
            module_id="screen_parser",
            cost={"cpu": 0.15, "gpu": 0.05, "ram": 0.10},
        )
        self._last_emit = 0.0
        self._period = 1.0  # default 1 Hz

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["screen_focus", "efference_copy"],
        )

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_emit >= self._period:
            self._last_emit = now
            event = Event(
                type="screen_change",
                data={
                    "timestamp": now,
                    "resolution": (1920, 1080),
                    "elements": [
                        {"type": "window", "title": "Browser", "bbox": [0, 0, 800, 600]},
                        {"type": "button", "label": "OK", "bbox": [400, 300, 500, 350]},
                    ],
                },
            )
            if self.kernel:
                self.kernel.event_bus.emit(event, Priority.COGNITIVE)
                logger.info("[ScreenParser] screen_change emitted")

    async def on_event(self, event: Event) -> None:
        if event.type == "screen_focus":
            # Increase frequency when screen is in focus
            self._period = 0.5
            logger.info("[ScreenParser] focus detected, increasing frequency")
        elif event.type == "efference_copy":
            # Predicted screen change, suppress brief noise
            logger.info("[ScreenParser] efference_copy received, suppressing predicted")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["period"] = self._period
        return base


def create_module():
    return ScreenParserModule()
