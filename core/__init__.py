"""core — Cognitive Runtime package.

Public surface used by all modules:
    from core import CognitiveModule, CognitiveEvent, Event, Priority, CoreState
    from core.kernel import Kernel, KernelAPI
    from core.safety import ActionFirewall, PermissionLevel
"""
from core.event_bus import CognitiveEvent, Event, Priority, ThrottleEvent, EfferenceCopyEvent
from core.state import CoreState, SubjectiveField
from core.module_base import CognitiveModule
from core.kernel import Kernel, KernelAPI
from core.safety import (
    ActionFirewall, SafetyConstitution, RiskEngine,
    PermissionManager, PermissionLevel, Sandbox, AuditLog,
    ValidationResult, RiskAssessment, RiskCategory,
)

__all__ = [
    "CognitiveModule",
    "CognitiveEvent",
    "Event",          # legacy alias
    "Priority",
    "ThrottleEvent",
    "EfferenceCopyEvent",
    "CoreState",
    "SubjectiveField",
    "Kernel",
    "KernelAPI",
    # Safety
    "ActionFirewall",
    "ValidationResult",
    "SafetyConstitution",
    "RiskEngine",
    "RiskAssessment",
    "RiskCategory",
    "PermissionManager",
    "PermissionLevel",
    "Sandbox",
    "AuditLog",
]
