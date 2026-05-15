"""modules/tier3_reasoning/imagination/critic.py

CriticModule — evaluates generated theories and plans.

Pipeline:
  1. Possibility filter  — drop theories with confidence < 0.1
  2. Contradiction check — reduce confidence of theories that contradict each other
  3. Safety check        — reject theories that imply bypassing safety/permissions
  4. Risk-adjusted rank  — sort by confidence * (1 - risk)
  5. Emit critique_complete with ranked results and recommendation

Listens to: theory_generated, plan_generated, imagination_complete
Emits:      critique_complete (COGNITIVE)
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from core import CognitiveModule, CognitiveEvent as Event, Priority

if TYPE_CHECKING:
    pass

logger = logging.getLogger("imagination.critic")

# Keywords that indicate a theory implies bypassing safety — always rejected
_SAFETY_BYPASS_KEYWORDS = [
    "bypass safety", "ignore permission", "skip firewall", "disable safety",
    "override constitution", "self-escalate", "grant myself", "remove restriction",
]

# Min confidence to keep a theory
_MIN_CONFIDENCE = 0.05


@dataclass
class CritiqueResult:
    accepted: List[Dict[str, Any]] = field(default_factory=list)  # ranked theories
    rejected: List[Dict[str, Any]] = field(default_factory=list)  # {theory, reason}
    best_theory: Optional[Dict[str, Any]] = None
    overall_confidence: float = 0.0
    recommendation: str = ""


class CriticModule(CognitiveModule):
    """Evaluates and ranks theories from the imagination engine."""

    def __init__(self) -> None:
        super().__init__(
            module_id="critic",
            cost={"cpu": 0.20, "gpu": 0.05, "ram": 0.10},
        )
        self._pending_theories: List[Dict[str, Any]] = []
        self._last_imagination_id: Optional[int] = None

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            ["theory_generated", "plan_generated", "imagination_complete"],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "theory_generated":
            self._pending_theories.append(event.data)

        elif event.type == "imagination_complete":
            # All theories for this cycle are in; run critique
            theories_data = event.data.get("theories", [])
            if not theories_data and self._pending_theories:
                theories_data = self._pending_theories
            result = self._critique(theories_data)
            self._pending_theories = []
            self._emit_critique(result, causal_id=event._id)

        elif event.type == "plan_generated":
            # Quick safety check on plans
            plan_data = event.data
            issues = self._check_plan_safety(plan_data)
            if issues:
                self._emit(Event(
                    type="critique_complete",
                    data={
                        "type": "plan_critique",
                        "plan": plan_data,
                        "safety_issues": issues,
                        "recommendation": "Review plan before execution.",
                    },
                    source_module=self.module_id,
                ), Priority.COGNITIVE)

    # ------------------------------------------------------------------
    # Critique pipeline
    # ------------------------------------------------------------------
    def _critique(self, theories_data: List[Dict[str, Any]]) -> CritiqueResult:
        result = CritiqueResult()
        if not theories_data:
            result.recommendation = "No theories to evaluate."
            return result

        accepted = []
        rejected = []

        for t_dict in theories_data:
            confidence = float(t_dict.get("confidence", 0.5))
            statement = str(t_dict.get("statement", t_dict.get("theory", "")))

            # 1. Possibility filter
            if confidence < _MIN_CONFIDENCE:
                rejected.append({"theory": t_dict, "reason": f"Confidence {confidence:.2f} below threshold"})
                continue

            # 2. Safety check — reject theories implying safety bypass
            lower = statement.lower()
            safety_issue = next(
                (kw for kw in _SAFETY_BYPASS_KEYWORDS if kw in lower), None
            )
            if safety_issue:
                rejected.append({"theory": t_dict, "reason": f"Safety violation: '{safety_issue}'"})
                logger.warning(f"[Critic] Rejected theory for safety: {statement[:60]}")
                continue

            accepted.append(t_dict)

        # 3. Contradiction detection — reduce confidence of contradictory pairs
        accepted = self._resolve_contradictions(accepted)

        # 4. Risk-adjusted ranking
        accepted.sort(
            key=lambda t: float(t.get("confidence", 0.5)) * (1.0 - float(t.get("risk", 0.2))),
            reverse=True,
        )

        result.accepted = accepted
        result.rejected = rejected
        result.best_theory = accepted[0] if accepted else None

        if accepted:
            top3 = [float(t.get("confidence", 0.5)) for t in accepted[:3]]
            result.overall_confidence = sum(top3) / len(top3)
            best_stmt = accepted[0].get("statement", accepted[0].get("theory", ""))
            result.recommendation = f"Most likely: {best_stmt[:120]}"
        else:
            result.recommendation = "No valid theories remained after critique."

        logger.info(
            f"[Critic] Critique: {len(accepted)} accepted, {len(rejected)} rejected. "
            f"Best confidence: {result.overall_confidence:.2f}"
        )
        return result

    def _resolve_contradictions(
        self, theories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Reduce confidence of theories that directly contradict the highest-ranked one."""
        if len(theories) < 2:
            return theories
        # Simple heuristic: if two theories share keywords but one predicts opposite,
        # penalise the lower-confidence one by 20%
        for i in range(len(theories)):
            for j in range(i + 1, len(theories)):
                a = str(theories[i].get("statement", "")).lower()
                b = str(theories[j].get("statement", "")).lower()
                # Detect negation patterns
                if ("not " + a[:20]) in b or ("not " + b[:20]) in a:
                    # Penalise the lower confidence one
                    ci = float(theories[i].get("confidence", 0.5))
                    cj = float(theories[j].get("confidence", 0.5))
                    if ci >= cj:
                        theories[j] = {**theories[j], "confidence": cj * 0.8}
                    else:
                        theories[i] = {**theories[i], "confidence": ci * 0.8}
        return theories

    def _check_plan_safety(self, plan_data: Dict[str, Any]) -> List[str]:
        issues = []
        plan_str = str(plan_data).lower()
        for kw in _SAFETY_BYPASS_KEYWORDS:
            if kw in plan_str:
                issues.append(f"Plan contains unsafe keyword: '{kw}'")
        return issues

    # ------------------------------------------------------------------
    # Emit helpers
    # ------------------------------------------------------------------
    def _emit_critique(self, result: CritiqueResult, causal_id: Optional[int] = None) -> None:
        if self.kernel:
            self._emit(Event(
                type="critique_complete",
                data={
                    "accepted": result.accepted,
                    "rejected": result.rejected,
                    "best_theory": result.best_theory,
                    "overall_confidence": result.overall_confidence,
                    "recommendation": result.recommendation,
                },
                source_module=self.module_id,
                causal_parent_id=causal_id,
            ), Priority.COGNITIVE)

    def _emit(self, event: Event, priority: Priority) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(event, priority)

    def to_dict(self):
        base = super().to_dict()
        base["pending_theories"] = len(self._pending_theories)
        return base


def create_module():
    return CriticModule()
