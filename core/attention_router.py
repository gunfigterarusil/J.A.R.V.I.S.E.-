"""core/attention_router.py — Attention budget allocation and event scoring.

The AttentionRouter decides:
1. Which modules get CPU time this tick (budget allocation).
2. What attention_weight to attach to incoming events before dispatch.

Attention is driven by:
  - novelty (event types not seen recently)
  - danger (hormone spike, danger flags)
  - emotional intensity (valence/arousal delta)
  - goal relevance (event related to active goals)
  - uncertainty (low-confidence events)
"""
from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.module_base import CognitiveModule
    from core.event_bus import CognitiveEvent
    from core.state import CoreState

BUDGET_UNITS = 1000   # total attention units per tick

# Base weights for scoring events
_EVENT_WEIGHTS: dict[str, float] = {
    "hormone_spike": 5.0,
    "user_utterance": 4.0,
    "goal_blocked": 3.5,
    "emotion_changed": 3.0,
    "goal_failed": 3.0,
    "goal_achieved": 2.5,
    "sensory_input": 2.0,
    "memory_retrieved": 1.5,
    "thought_generated": 1.2,
    "internal_monologue": 0.5,
    "memory_decayed": 0.3,
    # Imagination engine events
    "critique_complete": 2.5,
    "imagination_complete": 2.0,
    "theory_generated": 1.5,
    "thinking_mode_changed": 1.0,
    "counterfactual_generated": 0.8,
    "imagination_started": 0.6,
}

# How long an event type must be absent to count as "novel"
_NOVELTY_WINDOW_SEC = 30.0


class AttentionRouter:
    """Allocates cognitive budget and scores events for attention weighting."""

    def __init__(self, budget: int = BUDGET_UNITS) -> None:
        self.budget = budget
        # rolling window: event_type → last seen timestamp
        self._last_seen: dict[str, float] = {}
        # recent attention scores for dashboard inspection
        self.recent_scores: deque[dict] = deque(maxlen=50)

    # ------------------------------------------------------------------
    # Event scoring
    # ------------------------------------------------------------------
    def score_event(self, event: "CognitiveEvent", core_state: Optional["CoreState"] = None) -> float:
        """Return a 0..10 attention score for this event."""
        base = _EVENT_WEIGHTS.get(event.type, 1.0)

        # Novelty bonus: event type not seen recently
        now = time.time()
        last = self._last_seen.get(event.type, 0.0)
        novelty = 2.0 if (now - last) > _NOVELTY_WINDOW_SEC else 0.0
        self._last_seen[event.type] = now

        # Danger flag in data
        danger = 3.0 if event.data.get("danger") else 0.0

        # Emotional intensity
        emotional = abs(event.data.get("valence", 0.0)) * 2.0

        # Uncertainty
        uncertainty_bonus = 0.0
        if core_state:
            uncertainty_bonus = core_state.uncertainty * 1.5

        score = min(10.0, base + novelty + danger + emotional + uncertainty_bonus)
        self.recent_scores.append({"type": event.type, "score": score, "ts": now})
        return score

    def enrich_event(self, event: "CognitiveEvent",
                     core_state: Optional["CoreState"] = None) -> "CognitiveEvent":
        """Attach attention_weight to an event in-place before dispatch."""
        event.attention_weight = self.score_event(event, core_state)
        return event

    # ------------------------------------------------------------------
    # Budget allocation
    # ------------------------------------------------------------------
    def allocate(self, modules: list["CognitiveModule"],
                 core_state: Optional["CoreState"] = None) -> tuple[list, list]:
        """Select which modules run this tick within the attention budget.

        Returns (selected, throttled).
        """
        if not modules:
            return [], []

        active_focus = core_state.active_focus if core_state else []

        weighted: list[tuple[float, "CognitiveModule"]] = []
        for mod in modules:
            if not mod.enabled:
                continue
            mod_cost = sum(mod.cost.values())
            focus_multiplier = 3.0 if mod.module_id in active_focus else 1.0
            # Higher score = higher priority (we want lower cost, higher focus)
            score = focus_multiplier / (mod_cost + 0.001)
            weighted.append((score, mod))

        weighted.sort(key=lambda x: x[0], reverse=True)

        selected: list["CognitiveModule"] = []
        throttled: list["CognitiveModule"] = []
        total_cost = 0.0

        for score, mod in weighted:
            mod_cost = sum(mod.cost.values())
            if total_cost + mod_cost <= self.budget:
                selected.append(mod)
                total_cost += mod_cost
            else:
                throttled.append(mod)

        return selected, throttled
