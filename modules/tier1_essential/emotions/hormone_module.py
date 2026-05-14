"""Tier 1: Hormone Module

Manages 5 hormones with basal levels and event responses:
- dopamine (motivation, reward)
- cortisol (stress, danger)
- oxytocin (attachment, social)
- serotonin (mood stability)
- adrenaline (panic, emergency)

All hormones decay to basal over time.
Events can trigger hormone spikes or drops.

Emits:
- "hormone_levels" (BACKGROUND, periodic every 5s)
- "hormone_spike" (REALTIME if adrenaline or cortisol spike hard)

Listens: all event types (read emotional valence, stress markers, social cues)
"""
from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority, CoreState, SubjectiveField

logger = logging.getLogger("hormone")


class HormoneModule(CognitiveModule):
    """
    Tier 1: Hormone System
    Manages 5 hormones: dopamine, cortisol, oxytocin, serotonin, adrenaline.
    
    Emits periodic hormone_levels (BACKGROUND ~ every 5s).
    Emits hormone_spike (REALTIME) if adrenaline or cortisol spike hard.
    """

    HORMONE_NAMES = ["dopamine", "cortisol", "oxytocin", "serotonin", "adrenaline"]
    DEFAULT_BASAL = {
        "dopamine": 0.5,
        "cortisol": 0.2,
        "oxytocin": 0.3,
        "serotonin": 0.5,
        "adrenaline": 0.1,
    }
    # Natural decay to basal per tick (simulated per update dt ~ TICK_RATE)
    DECAY_RATE = 0.02
    # Threshold for a "spike" on adrenaline / cortisol
    SPIKE_THRESHOLD = 0.8
    # Interval for periodic hormone_levels emission (seconds)
    LEVELS_INTERVAL = 5.0

    def __init__(self) -> None:
        super().__init__(
            module_id="hormone_module",
            cost={"cpu": 0.08, "gpu": 0.0, "ram": 0.05},
        )
        self._kernel: Optional["Kernel"] = None
        # Basal and current hormone levels (0..1)
        self._basal: Dict[str, float] = dict(self.DEFAULT_BASAL)
        self._current: Dict[str, float] = {k: v for k, v in self.DEFAULT_BASAL.items()}
        # Trends: direction of last change
        self._trend: Dict[str, float] = {k: 0.0 for k in self.HORMONE_NAMES}
        # Track last triggers for spike logging
        self._last_triggers: List[str] = []
        self._last_levels_time = 0.0

    def initialize(self, kernel: "Kernel") -> None:
        super().initialize(kernel)
        self._kernel = kernel
        # Listen on all event types to modulate hormones from any source
        kernel.event_bus.register_consumer(
            self.module_id,
            ["*"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "hormone_levels":
            # Do not self-react to our own periodic emission
            return

        valence = event.data.get("valence", 0.0) if isinstance(event.data, dict) else 0.0
        intensity = event.data.get("intensity", 0.0) if isinstance(event.data, dict) else 0.0
        stress_flag = event.data.get("stress", False) if isinstance(event.data, dict) else False
        danger_flag = event.data.get("danger", False) if isinstance(event.data, dict) else False
        reward_flag = event.data.get("reward", False) if isinstance(event.data, dict) else False
        sosocial = event.data.get("social_cue", False) if isinstance(event.data, dict) else False

        # Event-based modulation
        if sosocial:
            # Social input boosts oxytocin
            self._modulate("oxytocin", 0.15)
        if reward_flag or (valence > 0.3):
            # Reward positivity boosts dopamine and serotonin
            self._modulate("dopamine", 0.1 + valence * 0.2)
            self._modulate("serotonin", 0.05 + valence * 0.05)
        if stress_flag or (valence < -0.3):
            # Stress negativity boosts cortisol and suppresses serotonin
            self._modulate("cortisol", 0.15 + abs(valence) * 0.2)
            self._modulate("serotonin", -0.05)
        if danger_flag or intensity > 0.8:
            # Danger / high intensity spikes adrenaline and cortisol
            self._modulate("adrenaline", 0.2 + intensity * 0.15)
            self._modulate("cortisol", 0.1 + intensity * 0.1)
        if event.type == "goal_achieved":
            self._modulate("dopamine", 0.25)
            self._modulate("serotonin", 0.15)
        elif event.type == "goal_failed":
            self._modulate("cortisol", 0.2)
            self._modulate("serotonin", -0.1)
        elif event.type == "goal_blocked":
            self._modulate("cortisol", 0.15)
            self._modulate("adrenaline", 0.1)

        # Check for spikes
        self._check_spikes()

    def _modulate(self, hormone: str, delta: float) -> None:
        if hormone not in self._current:
            return
        old = self._current[hormone]
        self._current[hormone] += delta
        # Clamp 0..1
        self._current[hormone] = max(0.0, min(1.0, self._current[hormone]))
        self._trend[hormone] = self._current[hormone] - old
        self._last_triggers.append(f"{hormone}:{delta:+.3f}")

    def _check_spikes(self) -> None:
        if not self._kernel:
            return
        for hormone in ("adrenaline", "cortisol"):
            if self._current[hormone] >= self.SPIKE_THRESHOLD:
                self._kernel.event_bus.emit(
                    Event(
                        type="hormone_spike",
                        data={"hormone": hormone, "level": self._current[hormone]}
                    ),
                    Priority.REALTIME,
                )

    def update(self, dt: float) -> None:
        # Apply decay toward basal per tick
        for hormone in self.HORMONE_NAMES:
            basal = self._basal[hormone]
            current = self._current[hormone]
            # Move toward basal with DECAY_RATE per tick, scaled by dt
            diff = basal - current
            new_val = current + diff * self.DECAY_RATE * (dt * 10.0)  # scale dt somewhat
            new_val = max(0.0, min(1.0, new_val))
            self._current[hormone] = new_val

        # Emit periodic hormone levels
        if self._kernel:
            now = time.time()
            if now - self._last_levels_time >= self.LEVELS_INTERVAL:
                self._last_levels_time = now
                self._kernel.event_bus.emit(
                    Event(
                        type="hormone_levels",
                        data={
                            "dopamine": self._current["dopamine"],
                            "cortisol": self._current["cortisol"],
                            "oxytocin": self._current["oxytocin"],
                            "serotonin": self._current["serotonin"],
                            "adrenaline": self._current["adrenaline"],
                        },
                    ),
                    Priority.BACKGROUND,
                )

    def shutdown(self) -> None:
        pass

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["hormone_levels"] = dict(self._current)
        base["hormone_basal"] = dict(self._basal)
        base["trends"] = dict(self._trend)
        base["last_triggers"] = self._last_triggers[-10:]
        return base


def create_module():
    return HormoneModule()
