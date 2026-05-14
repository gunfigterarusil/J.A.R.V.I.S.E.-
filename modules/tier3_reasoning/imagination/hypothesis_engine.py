"""modules/tier3_reasoning/imagination/hypothesis_engine.py

HypothesisEngine — generates multiple competing theories for a given problem.

The Theory dataclass is defined here and imported by all other imagination modules.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm_router import LLMRouter

logger = logging.getLogger("imagination.hypothesis")


# ---------------------------------------------------------------------------
# Theory — shared data structure for all imagination modules
# ---------------------------------------------------------------------------
@dataclass
class Theory:
    """A single hypothesis about a problem, enriched with evidence and predictions."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    statement: str = ""
    confidence: float = 0.5          # 0..1 — how likely this theory is correct
    risk: float = 0.2                # 0..1 — how dangerous to act on this if wrong
    evidence: List[str] = field(default_factory=list)          # known supporting facts
    missing_evidence: List[str] = field(default_factory=list)  # what would confirm/deny
    possible_tests: List[str] = field(default_factory=list)    # how to test this
    predicted_outcomes: List[str] = field(default_factory=list)# if true, expect...
    alternative_explanations: List[str] = field(default_factory=list)
    source_module: str = "hypothesis_engine"
    timestamp: float = field(default_factory=time.time)
    status: str = "active"  # "active"|"confirmed"|"rejected"|"pending_test"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Theory":
        known = {k for k in d if k in cls.__dataclass_fields__}
        return cls(**{k: d[k] for k in known})

    @classmethod
    def from_llm_dict(cls, d: Dict[str, Any], source: str = "llm") -> "Theory":
        """Convert raw LLM output dict to a Theory object."""
        return cls(
            statement=str(d.get("theory", d.get("statement", "Unknown hypothesis"))),
            confidence=float(d.get("confidence", 0.4)),
            risk=float(d.get("risk", 0.2)),
            evidence=list(d.get("evidence", [])),
            missing_evidence=list(d.get("missing_evidence", [])),
            possible_tests=list(d.get("possible_tests", [])),
            predicted_outcomes=list(d.get("predicted_outcomes", [])),
            alternative_explanations=list(d.get("alternative_explanations", [])),
            source_module=source,
        )


# ---------------------------------------------------------------------------
# Fallback theories when LLM is unavailable
# ---------------------------------------------------------------------------
_FALLBACK_TEMPLATES = [
    "Root cause may be a configuration or environment mismatch.",
    "The problem could be a version incompatibility between dependencies.",
    "State corruption or race condition may be responsible.",
    "External service or resource unavailability is a possible cause.",
    "Logic error or off-by-one in core processing loop.",
]


class HypothesisEngine:
    """Generates N competing theories for a given problem using the LLM router."""

    def __init__(self, llm_router: "LLMRouter") -> None:
        self._llm = llm_router

    async def generate(
        self,
        problem: str,
        context: Dict[str, Any],
        n: int = 5,
    ) -> List[Theory]:
        """Return `n` competing theories sorted by confidence descending."""
        from core.llm_router import TaskType
        raw_theories = await self._llm.imagine(
            seed=problem,
            context=context,
            task_type=TaskType.CREATIVE_IMAGINATION,
        )

        theories: List[Theory] = []
        for raw in raw_theories[:n]:
            try:
                if isinstance(raw, dict):
                    t = Theory.from_llm_dict(raw)
                else:
                    t = Theory(statement=str(raw), confidence=0.3)
                theories.append(t)
            except Exception as exc:
                logger.warning(f"[HypothesisEngine] Could not parse theory: {exc}")

        # Fallback if LLM returned nothing useful
        if not theories:
            theories = self._fallback_theories(problem, n)

        # Clamp values and sort
        for t in theories:
            t.confidence = max(0.0, min(1.0, t.confidence))
            t.risk = max(0.0, min(1.0, t.risk))

        theories.sort(key=lambda t: t.confidence, reverse=True)
        logger.info(f"[HypothesisEngine] Generated {len(theories)} theories for: {problem[:60]}")
        return theories

    def _fallback_theories(self, problem: str, n: int) -> List[Theory]:
        result = []
        for i, template in enumerate(_FALLBACK_TEMPLATES[:n]):
            result.append(Theory(
                statement=template,
                confidence=0.3 - i * 0.02,
                risk=0.2,
                evidence=[],
                missing_evidence=["LLM analysis required for higher confidence"],
                possible_tests=["Enable an LLM provider for detailed hypothesis generation"],
                source_module="hypothesis_engine/fallback",
            ))
        return result
