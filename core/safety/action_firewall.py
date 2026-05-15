"""core/safety/action_firewall.py — The validation gate.

Every action_request event passes through ActionFirewall.validate() before
anything happens.  The chain is:

  1. SafetyConstitution.check()   — hard rules (always blocks, no override)
  2. Sandbox.check_path()         — filesystem restriction check
  3. RiskEngine.assess()          — numeric danger score
  4. PermissionManager.check()    — level 0-6 gate
  5. If risk requires confirmation and not pre-approved → PENDING
  6. All pass → APPROVED
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.event_bus import CognitiveEvent
    from core.safety.audit_log import AuditLog
    from core.safety.constitution import SafetyConstitution
    from core.safety.risk_engine import RiskEngine, RiskAssessment
    from core.safety.permission_manager import PermissionManager
    from core.safety.sandbox import Sandbox

from core.event_bus import CognitiveEvent, Priority
from core.safety.audit_log import AuditEntry
from core.safety.risk_engine import RiskAssessment, RiskCategory

logger = logging.getLogger("core.safety.firewall")


@dataclass
class ValidationResult:
    allowed: bool
    requires_confirmation: bool
    deny_reason: str
    risk: RiskAssessment
    rule_violated: Optional[str]
    friendly_reason: str = ""     # human-readable reason for UI
    rule_type: str = "technical"  # "technical" | "ethical"


class ActionFirewall:
    """Chains all safety checks and produces ValidationResult."""

    def __init__(
        self,
        constitution: "SafetyConstitution",
        risk_engine: "RiskEngine",
        permission_manager: "PermissionManager",
        sandbox: "Sandbox",
        audit_log: "AuditLog",
    ) -> None:
        self._constitution = constitution
        self._risk = risk_engine
        self._perm = permission_manager
        self._sandbox = sandbox
        self._audit = audit_log

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def validate(self, event: "CognitiveEvent") -> ValidationResult:
        action_type = event.data.get("action_type", "unknown")
        payload = event.data.get("payload", {})
        source = event.source_module

        # 1. Constitution (hard rules — unbypassable)
        const_result = self._constitution.check(action_type, event.data)
        if not const_result.allowed:
            result = ValidationResult(
                allowed=False,
                requires_confirmation=False,
                deny_reason=const_result.friendly_reason or const_result.reason,
                risk=self._risk.assess(action_type, event.data),
                rule_violated=const_result.rule_name,
                friendly_reason=const_result.friendly_reason,
                rule_type=const_result.rule_type,
            )
            self._record(result, action_type, source, event.data, "denied")
            return result

        # 2. Sandbox check (if a path is involved)
        path = _extract_path(event.data)
        if path:
            write_actions = {"write_file", "delete_file", "move_file", "create_dir",
                             "execute_script", "run_command"}
            if action_type in write_actions:
                ok, reason = self._sandbox.check_write(path)
            else:
                ok, reason = self._sandbox.check_read(path)
            if not ok:
                result = ValidationResult(
                    allowed=False,
                    requires_confirmation=False,
                    deny_reason=f"Sandbox violation: {reason}",
                    risk=self._risk.assess(action_type, event.data),
                    rule_violated=f"sandbox:{reason}",
                )
                self._record(result, action_type, source, event.data, "denied")
                return result

        # 3. Risk assessment
        risk = self._risk.assess(action_type, event.data)

        # 4. Permission level check
        ok, reason = self._perm.check(action_type)
        if not ok:
            result = ValidationResult(
                allowed=False,
                requires_confirmation=False,
                deny_reason=f"Permission denied: {reason}",
                risk=risk,
                rule_violated=None,
            )
            self._record(result, action_type, source, event.data, "denied")
            return result

        # 5. Confirmation required?
        approved_once = bool(event.data.get("_approved_once", False))
        if risk.requires_confirmation and not approved_once and action_type not in self._perm._granted_actions:
            result = ValidationResult(
                allowed=False,
                requires_confirmation=True,
                deny_reason=(
                    f"Action '{action_type}' has risk score {risk.score:.1f} "
                    f"({risk.category.name}) — user confirmation required."
                ),
                risk=risk,
                rule_violated=None,
            )
            self._record(result, action_type, source, event.data, "pending")
            return result

        # 6. All checks passed
        result = ValidationResult(
            allowed=True,
            requires_confirmation=False,
            deny_reason="",
            risk=risk,
            rule_violated=None,
        )
        self._record(result, action_type, source, event.data, "approved")
        return result

    # ------------------------------------------------------------------
    # Event factories
    # ------------------------------------------------------------------
    def _make_approved_event(self, original: "CognitiveEvent") -> "CognitiveEvent":
        return CognitiveEvent(
            type="action_approved",
            data=original.data,
            source_module="safety_firewall",
            causal_parent_id=original._id,
        )

    def _make_denied_event(
        self, original: "CognitiveEvent", result: ValidationResult
    ) -> "CognitiveEvent":
        return CognitiveEvent(
            type="action_denied",
            data={
                **original.data,
                "deny_reason": result.deny_reason,
                "rule_violated": result.rule_violated,
                "risk_score": result.risk.score,
            },
            source_module="safety_firewall",
            causal_parent_id=original._id,
        )

    def _make_pending_event(
        self, original: "CognitiveEvent", result: ValidationResult
    ) -> "CognitiveEvent":
        return CognitiveEvent(
            type="action_pending_confirmation",
            data={
                **original.data,
                "pending_reason": result.deny_reason,
                "risk_score": result.risk.score,
                "risk_category": result.risk.category.name,
                "risk_reasons": result.risk.reasons,
                # Embed original event id so it can be re-processed on approval
                "_original_event_id": original._id,
            },
            source_module="safety_firewall",
            causal_parent_id=original._id,
        )

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _record(
        self,
        result: ValidationResult,
        action_type: str,
        source: str,
        data: dict,
        decision: str,
    ) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            action_type=action_type,
            source_module=source,
            data_summary=_summarise(data),
            decision=decision,
            risk_score=result.risk.score,
            rule_violated=result.rule_violated,
            confirm_required=result.requires_confirmation,
            rule_type=getattr(result, "rule_type", "technical"),
            friendly_reason=getattr(result, "friendly_reason", ""),
        )
        self._audit.record(entry)
        if decision == "denied":
            logger.warning(
                f"[Firewall] DENIED {action_type} from '{source}' — {result.deny_reason}"
            )
        elif decision == "pending":
            logger.info(
                f"[Firewall] PENDING {action_type} from '{source}' — score={result.risk.score:.1f}"
            )
        else:
            logger.debug(
                f"[Firewall] APPROVED {action_type} from '{source}' — score={result.risk.score:.1f}"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_path(data: dict) -> Optional[str]:
    path = data.get("path")
    if path:
        return str(path)
    payload = data.get("payload", {})
    if isinstance(payload, dict):
        return payload.get("path")
    return None


def _summarise(data: dict, max_len: int = 200) -> str:
    """Safe, truncated representation of action data (no secrets)."""
    try:
        import json
        s = json.dumps(data, default=str)
        if len(s) > max_len:
            s = s[:max_len] + "…"
        return s
    except Exception:
        return str(data)[:max_len]
