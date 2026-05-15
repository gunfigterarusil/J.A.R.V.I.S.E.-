"""modules/tier3_reasoning/imagination/theory_builder.py

TheoryBuilderModule — orchestrates the full imagination cycle.

When triggered by a significant event, it:
  1. Selects cognition depth via ThinkingModeSelector
  2. If mode >= IMAGINATION: runs HypothesisEngine + ScenarioSimulator
  3. Emits theory_generated for each theory
  4. Emits imagination_complete when done
  5. Stores all theories in IdeaMemory

Listens to: user_utterance, goal_failed, thought_generated, context_ready,
            imagination_requested
Emits:      imagination_started, theory_generated, imagination_complete (COGNITIVE)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("imagination.theory_builder")


class TheoryBuilderModule(CognitiveModule):
    """Orchestrates hypothesis generation and scenario simulation."""

    def __init__(self) -> None:
        super().__init__(
            module_id="theory_builder",
            cost={"cpu": 0.35, "gpu": 0.10, "ram": 0.20},
        )
        self._hypothesis_engine = None
        self._scenario_simulator = None
        self._idea_memory = None
        self._mode_selector = None
        self._running = False   # prevent concurrent imagination cycles

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        from core.llm_router import LLMRouter
        from core.thinking_modes import ThinkingModeSelector
        from modules.tier3_reasoning.imagination.hypothesis_engine import HypothesisEngine
        from modules.tier3_reasoning.imagination.scenario_simulator import ScenarioSimulator
        from modules.tier3_reasoning.imagination.idea_memory import IdeaMemory

        router: LLMRouter = kernel.llm_router
        self._hypothesis_engine = HypothesisEngine(router)
        self._scenario_simulator = ScenarioSimulator(router)
        self._idea_memory = IdeaMemory(kernel.persistence)
        self._idea_memory.load()
        self._mode_selector = ThinkingModeSelector()

        # Expose IdeaMemory on kernel for other modules (e.g. counterfactuals)
        kernel._idea_memory = self._idea_memory

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "user_utterance",
                "goal_failed",
                "thought_generated",
                "context_ready",
                "imagination_requested",
            ],
        )
        kernel.core_state.patch({"imagination_active": False})
        logger.info("[TheoryBuilder] Initialized with HypothesisEngine + ScenarioSimulator")

    async def on_event(self, event: Event) -> None:
        if self._running or not self.kernel:
            return

        from core.thinking_modes import ThinkingMode
        mode = self._mode_selector.select(event, self.kernel.core_state)

        if mode < ThinkingMode.IMAGINATION:
            return  # not warranted for this event

        # Build problem description from event
        problem = _extract_problem(event)
        if not problem:
            return

        context = _build_context(event, self.kernel.core_state)

        # Run imagination asynchronously without blocking the event dispatch loop
        asyncio.ensure_future(self._imagine(problem, context, causal_id=event._id))

    async def _imagine(
        self,
        problem: str,
        context: Dict[str, Any],
        causal_id: Optional[int] = None,
    ) -> None:
        self._running = True
        if not self.kernel:
            self._running = False
            return
        try:
            self.kernel.core_state.patch({"imagination_active": True})
            self.kernel.event_bus.emit(
                Event(
                    type="imagination_started",
                    data={"problem": problem[:200]},
                    source_module=self.module_id,
                    causal_parent_id=causal_id,
                ),
                Priority.COGNITIVE,
            )

            # Generate theories
            theories = await self._hypothesis_engine.generate(problem, context, n=5)

            # Simulate scenarios for each theory
            for theory in theories:
                scenarios = await self._scenario_simulator.simulate(theory, context, n_scenarios=2)
                theory.predicted_outcomes = [s.description for s in scenarios]
                # Store in persistent memory
                self._idea_memory.store(theory)
                # Emit individual theory event
                self.kernel.event_bus.emit(
                    Event(
                        type="theory_generated",
                        data=theory.to_dict(),
                        source_module=self.module_id,
                        causal_parent_id=causal_id,
                    ),
                    Priority.COGNITIVE,
                )

            # Update core state
            self.kernel.core_state.patch({
                "imagination_active": False,
                "active_theories": [t.id for t in theories],
            })

            # Emit completion
            self.kernel.event_bus.emit(
                Event(
                    type="imagination_complete",
                    data={
                        "theories": [t.to_dict() for t in theories],
                        "count": len(theories),
                        "problem": problem[:200],
                    },
                    source_module=self.module_id,
                    causal_parent_id=causal_id,
                ),
                Priority.COGNITIVE,
            )
            logger.info(
                f"[TheoryBuilder] Imagination complete: {len(theories)} theories for '{problem[:60]}'"
            )
        except Exception as exc:
            logger.error(f"[TheoryBuilder] _imagine error: {exc}")
            self.kernel.core_state.patch({"imagination_active": False})
        finally:
            self._running = False

    def shutdown(self) -> None:
        if self._idea_memory:
            self._idea_memory.save()

    def to_dict(self):
        base = super().to_dict()
        base["running"] = self._running
        if self._idea_memory:
            base["stored_theories"] = len(self._idea_memory.get_recent(500))
        return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_problem(event: Event) -> str:
    data = event.data
    # Try common fields
    for key in ("text", "reason", "error", "content", "goal", "description"):
        val = data.get(key)
        if val and isinstance(val, str) and len(val) > 3:
            return val[:400]
    # Fallback to event type
    if event.type in ("goal_failed", "plan_failed"):
        return f"Failed: {event.type} — {str(data)[:150]}"
    return str(data)[:200] if data else ""


def _build_context(event: Event, core_state) -> Dict[str, Any]:
    return {
        "event_type": event.type,
        "source_module": event.source_module,
        "active_goals": list(core_state.active_goals),
        "emotional_state": dict(core_state.emotional_state),
        "uncertainty": core_state.uncertainty,
        "energy_level": core_state.energy_level,
        "active_thoughts": list(core_state.active_thoughts)[:3],
    }


def create_module():
    return TheoryBuilderModule()
