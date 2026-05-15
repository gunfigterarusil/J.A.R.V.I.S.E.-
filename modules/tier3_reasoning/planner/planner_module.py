"""Tier 3 Reasoning: Planner Module

Decomposes activated goals into ordered action sequences.
Uses LLMRouter for AI-driven planning when available; falls back to templates.
Incorporates best theory from imagination engine when present.

Emits:
  - plan_generated  (COGNITIVE)  — ordered list of steps
  - plan_failed     (COGNITIVE)  — could not decompose

Listens:
  - goal_activated, goal_completed, goal_failed, imagination_complete, critique_complete
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("planner")

_STEP_TEMPLATES: Dict[str, List[str]] = {
    "default": [
        "Assess current context",
        "Identify required resources",
        "Execute primary action",
        "Verify outcome",
    ],
    "user_command": [
        "Parse user intent",
        "Retrieve relevant memory",
        "Generate response plan",
        "Execute response",
        "Confirm with user",
    ],
    "react": [
        "Identify trigger source",
        "Assess severity",
        "Select response action",
        "Execute response",
    ],
}


class PlannerModule(CognitiveModule):
    """Decomposes goals into action step sequences."""

    MODULE_DESCRIPTION = "Goal decomposition — converts active goals into ordered action plans"

    def __init__(self) -> None:
        super().__init__(
            module_id="planner",
            cost={"cpu": 0.10, "gpu": 0.0, "ram": 0.05},
        )
        self._active_plans: Dict[str, List[str]] = {}  # goal_id → steps
        self._best_theory: Optional[Dict[str, Any]] = None  # from imagination engine

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["goal_activated", "goal_completed", "goal_failed",
             "imagination_complete", "critique_complete"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "goal_activated":
            goal_id = event.data.get("goal_id", f"g_{int(time.time())}")
            description = event.data.get("description", "")
            asyncio.ensure_future(self._decompose_async(goal_id, description))
        elif event.type in ("goal_completed", "goal_failed"):
            goal_id = event.data.get("goal_id", "")
            self._active_plans.pop(goal_id, None)
        elif event.type == "imagination_complete":
            theories = event.data.get("theories", [])
            if theories:
                self._best_theory = theories[0]  # highest-confidence theory
        elif event.type == "critique_complete":
            best = event.data.get("best_theory")
            if best:
                self._best_theory = best

    async def _decompose_async(self, goal_id: str, description: str) -> None:
        if not self.kernel:
            return
        router = getattr(self.kernel, "llm_router", None)
        steps: List[str] = []

        if router:
            from core.llm_router import TaskType
            # Build planning context
            theory_context = ""
            if self._best_theory:
                stmt = self._best_theory.get("statement", self._best_theory.get("theory", ""))
                theory_context = f"\n\nBest available theory: {stmt[:200]}"

            prompt = (
                f"Decompose this goal into 4-6 concrete ordered steps:\n\n"
                f"GOAL: {description}{theory_context}\n\n"
                f"Return only a numbered list of steps. Be specific and actionable."
            )
            try:
                raw = await router.generate(prompt, task_type=TaskType.PLANNING,
                                            system="You are a precise action planner.")
                steps = _parse_steps(raw)
            except Exception as exc:
                logger.warning(f"[Planner] LLM decompose failed: {exc}")

        if not steps:
            steps = self._template_decompose(description)

        self._active_plans[goal_id] = steps
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="plan_generated",
                    data={
                        "goal_id": goal_id,
                        "description": description,
                        "steps": steps,
                        "theory_used": bool(self._best_theory),
                        "timestamp": time.time(),
                    },
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )
            logger.info(f"[Planner] Plan for goal {goal_id}: {len(steps)} steps")

    def _template_decompose(self, description: str) -> List[str]:
        template_key = "default"
        desc_lower = description.lower()
        if "user" in desc_lower or "command" in desc_lower:
            template_key = "user_command"
        elif "react" in desc_lower or "sensory" in desc_lower:
            template_key = "react"
        return list(_STEP_TEMPLATES.get(template_key, _STEP_TEMPLATES["default"]))

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["active_plans"] = len(self._active_plans)
        base["theory_available"] = self._best_theory is not None
        return base


def _parse_steps(raw: str) -> List[str]:
    """Extract numbered steps from LLM output."""
    steps = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Remove leading numbering (1. / 1) / - / *)
        import re
        cleaned = re.sub(r"^[\d]+[\.\)]\s*", "", line)
        cleaned = re.sub(r"^[-\*]\s*", "", cleaned)
        if cleaned and len(cleaned) > 3:
            steps.append(cleaned)
    return steps[:8] if steps else []


def create_module() -> PlannerModule:
    return PlannerModule()
