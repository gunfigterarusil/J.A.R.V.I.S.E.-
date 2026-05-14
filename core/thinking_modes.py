"""core/thinking_modes.py — Cognition depth selector.

Six modes from reflex (no LLM) to deep analysis (full imagination chain).
The ThinkingModeSelector picks the appropriate mode for each incoming event
based on urgency, energy level, uncertainty, and event type.
"""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.event_bus import CognitiveEvent, Priority
    from core.state import CoreState

logger = logging.getLogger("core.thinking_modes")


class ThinkingMode(IntEnum):
    REFLEX = 0        # <100ms  — pattern match only, no LLM
    REACTIVE = 1      # <1s     — single LLM call, no chaining
    DELIBERATIVE = 2  # <5s     — multi-step: LLM + planner
    IMAGINATION = 3   # <30s    — HypothesisEngine + ScenarioSimulator
    DEEP_ANALYSIS = 4 # <120s   — IMAGINATION + CriticModule + counterfactuals
    BACKGROUND = 5    # no SLA  — async, scheduler-driven, low priority


# Event types that elevate to imagination by default
_IMAGINATION_TRIGGERS = {
    "goal_failed",
    "plan_failed",
    "error_encountered",
    "uncertainty_high",
    "imagination_requested",
}

# Event types that stay at reactive level
_REACTIVE_EVENTS = {
    "user_utterance",
    "context_request",
    "memory_retrieved",
}

# Event types that are background-only
_BACKGROUND_EVENTS = {
    "internal_monologue",
    "temporal_tick",
    "memory_decayed",
    "dream_narrative",
    "pattern_detected",
}


class ThinkingModeSelector:
    """Stateless selector — call `select()` for each incoming event."""

    def select(self, event: "CognitiveEvent", core_state: "CoreState") -> ThinkingMode:
        from core.event_bus import Priority

        event_type = event.type
        priority = getattr(event, "_priority", None)

        # 1. Danger / realtime system events → REFLEX (no LLM overhead)
        data_str = str(event.data).lower()
        if "danger" in data_str or "critical" in data_str:
            return ThinkingMode.REFLEX

        # 2. Background-only events
        if event_type in _BACKGROUND_EVENTS:
            return ThinkingMode.BACKGROUND

        # 3. Low energy — conserve computation
        if core_state.energy_level < 0.3:
            return ThinkingMode.REACTIVE

        # 4. High uncertainty or failure → imagination needed
        if event_type in _IMAGINATION_TRIGGERS:
            if core_state.uncertainty > 0.85:
                return ThinkingMode.DEEP_ANALYSIS
            return ThinkingMode.IMAGINATION

        # 5. Long user input → deliberative
        if event_type == "user_utterance":
            text = event.data.get("text", "")
            if len(text) > 200:
                return ThinkingMode.DELIBERATIVE
            return ThinkingMode.REACTIVE

        # 6. Uncertainty above threshold → at least deliberative
        if core_state.uncertainty > 0.7:
            return ThinkingMode.IMAGINATION

        # 7. Standard cognitive events
        if event_type in _REACTIVE_EVENTS:
            return ThinkingMode.REACTIVE

        # Default
        return ThinkingMode.REACTIVE

    def mode_name(self, mode: ThinkingMode) -> str:
        return mode.name

    def describe(self, mode: ThinkingMode) -> str:
        descriptions = {
            ThinkingMode.REFLEX: "Immediate pattern response — no LLM",
            ThinkingMode.REACTIVE: "Single LLM call, direct response",
            ThinkingMode.DELIBERATIVE: "Multi-step reasoning with planner",
            ThinkingMode.IMAGINATION: "Full hypothesis generation + scenario simulation",
            ThinkingMode.DEEP_ANALYSIS: "Imagination + critic + counterfactuals",
            ThinkingMode.BACKGROUND: "Async background cognition, no time constraint",
        }
        return descriptions.get(mode, "Unknown mode")
