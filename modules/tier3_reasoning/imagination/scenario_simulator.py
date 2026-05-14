"""modules/tier3_reasoning/imagination/scenario_simulator.py

ScenarioSimulator — generates possible future outcomes for each Theory.

For each theory the simulator asks: "If this theory is correct, what happens next?"
It produces 1-3 Scenarios per theory capturing probability, risks, and opportunities.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm_router import LLMRouter
    from modules.tier3_reasoning.imagination.hypothesis_engine import Theory

logger = logging.getLogger("imagination.scenario")


@dataclass
class Scenario:
    """A projected future state if a given theory proves correct."""
    description: str = ""
    probability: float = 0.5      # 0..1
    risks: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    timeline: str = "short-term"  # "immediate"|"short-term"|"long-term"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_SYSTEM_PROMPT = (
    "You are a scenario forecasting engine. "
    "Given a theory about a problem, generate 1-3 plausible future scenarios. "
    "Return a JSON array. Each scenario must have: "
    "description (string), probability (0-1), risks (list), "
    "opportunities (list), timeline ('immediate'|'short-term'|'long-term'). "
    "Be realistic. Distinguish optimistic, neutral, and pessimistic outcomes."
)


class ScenarioSimulator:
    """Generates future outcome scenarios for a Theory using the LLM router."""

    def __init__(self, llm_router: "LLMRouter") -> None:
        self._llm = llm_router

    async def simulate(
        self,
        theory: "Theory",
        context: Dict[str, Any],
        n_scenarios: int = 3,
    ) -> List[Scenario]:
        from core.llm_router import TaskType
        ctx_str = json.dumps(context, default=str)[:400]
        prompt = (
            f"Theory: {theory.statement}\n\n"
            f"Confidence: {theory.confidence:.2f}, Risk: {theory.risk:.2f}\n"
            f"Context: {ctx_str}\n\n"
            f"Generate {n_scenarios} future scenarios if this theory is correct. "
            f"Return a JSON array of scenario objects."
        )
        raw = await self._llm.generate(
            prompt, task_type=TaskType.COMPLEX_REASONING, system=_SYSTEM_PROMPT
        )
        scenarios = _parse_scenarios(raw)
        if not scenarios:
            scenarios = self._fallback_scenarios(theory)
        # Clamp probabilities
        for s in scenarios:
            s.probability = max(0.0, min(1.0, s.probability))
        logger.debug(f"[ScenarioSim] {len(scenarios)} scenarios for theory: {theory.statement[:50]}")
        return scenarios[:n_scenarios]

    def _fallback_scenarios(self, theory: "Theory") -> List[Scenario]:
        return [
            Scenario(
                description=f"If '{theory.statement[:80]}' is correct: situation resolves with targeted fix.",
                probability=0.5 * theory.confidence,
                risks=["May not address root cause"],
                opportunities=["Quick resolution if correct"],
                timeline="short-term",
            )
        ]


def _parse_scenarios(raw: str) -> List[Scenario]:
    raw = raw.strip()
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end != -1:
        try:
            data = json.loads(raw[start:end + 1])
            if isinstance(data, list):
                result = []
                for d in data:
                    if isinstance(d, dict):
                        result.append(Scenario(
                            description=str(d.get("description", "")),
                            probability=float(d.get("probability", 0.5)),
                            risks=list(d.get("risks", [])),
                            opportunities=list(d.get("opportunities", [])),
                            timeline=str(d.get("timeline", "short-term")),
                        ))
                return result
        except json.JSONDecodeError:
            pass
    return []
