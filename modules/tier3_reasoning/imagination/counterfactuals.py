"""modules/tier3_reasoning/imagination/counterfactuals.py

CounterfactualModule — "what if X hadn't happened?" reasoning.

Activates on failures and rejected theories to generate alternative histories
and learn what could have been done differently.

Listens to: goal_failed, plan_failed, error_encountered, critique_complete (rejected)
Emits:      counterfactual_generated (BACKGROUND)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("imagination.counterfactuals")

_SYSTEM_PROMPT = (
    "You are a counterfactual reasoning engine. "
    "Given a failure or problem, generate 3 alternative scenarios: "
    "what could have been done differently to avoid or improve the outcome. "
    "Be specific. Format as numbered alternatives."
)


class CounterfactualModule(CognitiveModule):
    """Generates counterfactual alternatives for failures and rejected theories."""

    def __init__(self) -> None:
        super().__init__(
            module_id="counterfactuals",
            cost={"cpu": 0.15, "gpu": 0.05, "ram": 0.10},
        )
        self._recent_counterfactuals: List[Dict[str, Any]] = []

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["goal_failed", "plan_failed", "error_encountered", "critique_complete"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type in ("goal_failed", "plan_failed", "error_encountered"):
            context = _extract_context(event.data)
            problem = event.data.get("reason") or event.data.get("error") or str(event.data)[:120]
            await self._generate_counterfactuals(
                failure=problem,
                context=context,
                causal_id=event._id,
            )

        elif event.type == "critique_complete":
            rejected = event.data.get("rejected", [])
            for item in rejected[:2]:  # process at most 2 rejections per cycle
                theory = item.get("theory", {})
                stmt = str(theory.get("statement", theory.get("theory", "")))[:100]
                if stmt:
                    await self._generate_counterfactuals(
                        failure=f"Rejected theory: {stmt}",
                        context={"rejection_reason": item.get("reason", "")},
                        causal_id=event._id,
                    )

    async def _generate_counterfactuals(
        self,
        failure: str,
        context: Dict[str, Any],
        causal_id: Optional[int] = None,
    ) -> None:
        if not self.kernel:
            return
        from core.llm_router import TaskType
        router = getattr(self.kernel, "llm_router", None)
        if router is None:
            self._emit_stub(failure, causal_id)
            return

        import json
        ctx_str = json.dumps(context, default=str)[:300]
        prompt = (
            f"FAILURE: {failure}\n\nCONTEXT: {ctx_str}\n\n"
            f"Generate 3 counterfactual alternatives — what could have been done differently?"
        )
        raw = await router.generate(
            prompt,
            task_type=TaskType.COMPLEX_REASONING,
            system=_SYSTEM_PROMPT,
        )
        cf = {
            "failure": failure,
            "counterfactuals": raw,
            "context_keys": list(context.keys()),
        }
        self._recent_counterfactuals.append(cf)
        if len(self._recent_counterfactuals) > 50:
            self._recent_counterfactuals = self._recent_counterfactuals[-50:]

        # Store in idea_memory if available
        idea_mem = getattr(self.kernel, "_idea_memory", None)
        if idea_mem:
            from modules.tier3_reasoning.imagination.hypothesis_engine import Theory
            t = Theory(
                statement=f"[Counterfactual] {failure[:80]}",
                confidence=0.4,
                risk=0.1,
                evidence=[f"Based on failure: {failure[:60]}"],
                predicted_outcomes=[raw[:200]],
                source_module=self.module_id,
                status="active",
            )
            idea_mem.store(t)

        self.kernel.event_bus.emit(
            Event(
                type="counterfactual_generated",
                data=cf,
                source_module=self.module_id,
                causal_parent_id=causal_id,
            ),
            Priority.BACKGROUND,
        )
        logger.info(f"[Counterfactuals] Generated for failure: {failure[:60]}")

    def _emit_stub(self, failure: str, causal_id: Optional[int]) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="counterfactual_generated",
                    data={
                        "failure": failure,
                        "counterfactuals": "1. Act earlier.\n2. Use different approach.\n3. Gather more data first.",
                    },
                    source_module=self.module_id,
                    causal_parent_id=causal_id,
                ),
                Priority.BACKGROUND,
            )

    def to_dict(self):
        base = super().to_dict()
        base["recent_counterfactuals"] = len(self._recent_counterfactuals)
        return base


def _extract_context(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}


def create_module():
    return CounterfactualModule()
