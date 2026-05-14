"""Tier 1 Essential: Temporal Engine Module

Manages temporal continuity — the brain's sense of time passing.
This enables persistent identity across restarts: the brain knows
how long it's been running, when it last interacted with the user,
and how long the idle period was.

Persists to ~/.jarvis_brain/temporal.json

Emits:
  - temporal_tick    (BACKGROUND, every 60s)
  - idle_detected    (COGNITIVE, after IDLE_THRESHOLD seconds of no input)
  - session_resumed  (COGNITIVE, on startup when previous session data exists)

Listens:
  - user_utterance, sensory_input, kernel_started
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("temporal_engine")

IDLE_THRESHOLD = 300.0    # 5 minutes of no input → idle_detected
TICK_INTERVAL = 60.0      # seconds between temporal_tick emissions


class TemporalModule(CognitiveModule):
    """Temporal continuity — tracks time, idle state, and session history."""

    MODULE_DESCRIPTION = "Temporal engine — time perception, idle detection, session continuity"

    def __init__(self) -> None:
        super().__init__(
            module_id="temporal_engine",
            cost={"cpu": 0.02, "gpu": 0.0, "ram": 0.02},
        )
        self._session_start = time.time()
        self._last_interaction = time.time()
        self._last_tick = 0.0
        self._session_count = 1
        self._idle_notified = False
        self._total_uptime = 0.0    # cumulative across sessions

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["user_utterance", "sensory_input", "kernel_started"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "kernel_started":
            self._load()
            self._session_start = time.time()
            self._last_interaction = time.time()
        elif event.type in ("user_utterance", "sensory_input"):
            # Any input resets idle timer
            was_idle = self._idle_notified
            self._last_interaction = time.time()
            self._idle_notified = False
            if was_idle and self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="activity_resumed",
                        data={"after_idle": True},
                        source_module=self.module_id,
                    ),
                    Priority.COGNITIVE,
                )

    def update(self, dt: float) -> None:
        now = time.time()

        # Update CoreState temporal marker
        if self.kernel:
            self.kernel.core_state.patch({"temporal_marker": now})

        # Idle detection
        idle_duration = now - self._last_interaction
        if idle_duration >= IDLE_THRESHOLD and not self._idle_notified:
            self._idle_notified = True
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="idle_detected",
                        data={
                            "idle_duration": idle_duration,
                            "session_uptime": now - self._session_start,
                        },
                        source_module=self.module_id,
                    ),
                    Priority.COGNITIVE,
                )
                logger.info(f"[Temporal] Idle detected after {idle_duration:.0f}s")

        # Periodic temporal tick
        if now - self._last_tick >= TICK_INTERVAL:
            self._last_tick = now
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="temporal_tick",
                        data={
                            "session_uptime": now - self._session_start,
                            "session_count": self._session_count,
                            "total_uptime": self._total_uptime + (now - self._session_start),
                            "idle_duration": now - self._last_interaction,
                        },
                        source_module=self.module_id,
                    ),
                    Priority.BACKGROUND,
                )

    def shutdown(self) -> None:
        self._save()

    def _save(self) -> None:
        if self.kernel:
            now = time.time()
            self.kernel.persistence.save("temporal", {
                "session_count": self._session_count + 1,
                "total_uptime": self._total_uptime + (now - self._session_start),
                "last_shutdown": now,
            })

    def _load(self) -> None:
        if self.kernel:
            data = self.kernel.persistence.load("temporal")
            if data:
                self._session_count = data.get("session_count", 1)
                self._total_uptime = data.get("total_uptime", 0.0)
                last_shutdown = data.get("last_shutdown", 0.0)
                gap = time.time() - last_shutdown if last_shutdown else 0.0
                logger.info(
                    f"[Temporal] Session {self._session_count} started. "
                    f"Total uptime: {self._total_uptime:.0f}s. Gap: {gap:.0f}s"
                )
                # Emit session_resumed so other modules know the brain restarted
                self.kernel.event_bus.emit(
                    Event(
                        type="session_resumed",
                        data={
                            "session_count": self._session_count,
                            "gap_seconds": gap,
                            "total_uptime": self._total_uptime,
                        },
                        source_module=self.module_id,
                    ),
                    Priority.COGNITIVE,
                )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        now = time.time()
        base["session_uptime"] = now - self._session_start
        base["session_count"] = self._session_count
        base["total_uptime"] = self._total_uptime + (now - self._session_start)
        base["idle_duration"] = now - self._last_interaction
        base["idle_notified"] = self._idle_notified
        return base


def create_module() -> TemporalModule:
    return TemporalModule()
