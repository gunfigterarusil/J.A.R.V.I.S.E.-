"""Tier 5: Self-Learning Module
Analyzes outcomes and feedback to update internal weights/heuristics.
"""
from __future__ import annotations

import time
import logging
import random
from typing import Dict, Any, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("self_learning")


class SelfLearningModule(CognitiveModule):
    """
    Learns from success/failure events, user feedback, and system errors.
    Maintains a mapping from context+action -> success probability.
    Emits: learning_applied, new_heuristic, weight_adjusted.
    """

    LEARNABLE_EVENTS = [
        "goal_achieved",
        "goal_failed",
        "user_praise",
        "user_criticism",
        "error_encountered",
    ]

    def __init__(self) -> None:
        super().__init__(
            module_id="self_learning",
            cost={"cpu": 0.30, "gpu": 0.05, "ram": 0.20},
        )
        # (context, action) -> {successes, failures, last_updated}
        self._weights: Dict[tuple, Dict[str, Any]] = {}
        self._heuristics: Dict[str, float] = {
            "risk_tolerance": 0.50,
            "exploration_rate": 0.50,
            "patience": 0.50,
            "optimism": 0.50,
            "adaptability": 0.50,
        }
        self._adjustment_log: List[Dict[str, Any]] = []

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(self.module_id, self.LEARNABLE_EVENTS)

    async def on_event(self, event: Event) -> None:
        if event.type == "goal_achieved":
            self._update_weight("goal", "achieve", success=True)
            self._adjust_heuristic("optimism", +0.05)
            self._adjust_heuristic("risk_tolerance", +0.02)
            self._emit("learning_applied", {"type": "success", "context": "goal"})
        elif event.type == "goal_failed":
            self._update_weight("goal", "achieve", success=False)
            self._adjust_heuristic("optimism", -0.05)
            self._adjust_heuristic("risk_tolerance", -0.03)
            self._emit("learning_applied", {"type": "failure", "context": "goal"})
        elif event.type == "user_praise":
            self._adjust_heuristic("optimism", +0.10)
            self._adjust_heuristic("exploration_rate", +0.05)
        elif event.type == "user_criticism":
            self._adjust_heuristic("optimism", -0.10)
            self._adjust_heuristic("patience", +0.08)
        elif event.type == "error_encountered":
            self._adjust_heuristic("risk_tolerance", -0.04)
            self._adjust_heuristic("adaptability", +0.02)
    
    def _emit(self, type_: str, data: Dict[str, Any]) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(type=type_, data=data),
                Priority.BACKGROUND,
            )

    def _update_weight(self, context: str, action: str, success: bool) -> None:
        key = (context, action)
        entry = self._weights.setdefault(key, {"successes": 0, "failures": 0, "last_updated": time.time()})
        if success:
            entry["successes"] += 1
        else:
            entry["failures"] += 1
        entry["last_updated"] = time.time()
        logger.info(f"[SelfLearn] Weight updated: {key} -> successes={entry['successes']}, failures={entry['failures']}")

    def _adjust_heuristic(self, name: str, delta: float) -> None:
        if name in self._heuristics:
            old_val = self._heuristics[name]
            new_val = max(0.0, min(1.0, self._heuristics[name] + delta))
            self._heuristics[name] = new_val
            if abs(delta) > 0.01 and self.kernel:
                self.kernel.event_bus.emit(
                    Event(type="weight_adjusted", data={"heuristic": name, "old": old_val, "new": new_val}),
                    Priority.BACKGROUND,
                )

    def update(self, dt: float) -> None:
        pass

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["heuristics"] = self._heuristics
        base["learned_entries"] = len(self._weights)
        return base


def create_module():
    return SelfLearningModule()
