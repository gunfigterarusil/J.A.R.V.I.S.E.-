"""core/safety — Safety Constitution for Jarvis Brain Core.

This package is a non-optional kernel subsystem.  It cannot be unloaded,
disabled, or bypassed by any module or permission level.

Public surface:
    from core.safety import (
        ActionFirewall, SafetyConstitution, RiskEngine,
        PermissionManager, PermissionLevel, Sandbox, AuditLog,
        AuditEntry, ValidationResult, RiskAssessment, RiskCategory,
    )
"""
from core.safety.audit_log import AuditLog, AuditEntry
from core.safety.sandbox import Sandbox
from core.safety.constitution import SafetyConstitution, ConstitutionRule
from core.safety.risk_engine import RiskEngine, RiskAssessment, RiskCategory
from core.safety.permission_manager import PermissionManager, PermissionLevel, ACTION_LEVEL_MAP
from core.safety.action_firewall import ActionFirewall, ValidationResult

__all__ = [
    "ActionFirewall",
    "ValidationResult",
    "SafetyConstitution",
    "ConstitutionRule",
    "RiskEngine",
    "RiskAssessment",
    "RiskCategory",
    "PermissionManager",
    "PermissionLevel",
    "ACTION_LEVEL_MAP",
    "Sandbox",
    "AuditLog",
    "AuditEntry",
]
