"""kernel_main.py — Backwards-compatibility shim.

All real logic has moved to the `core/` package.
This file re-exports the public surface so any external code that
still does `from kernel_main import ...` continues to work.

New code should import from `core` directly:
    from core import CognitiveModule, CognitiveEvent, Priority, CoreState
    from core.kernel import Kernel, KernelAPI
"""
from __future__ import annotations

# Re-export everything the old API exposed
from core import (
    CognitiveModule,
    CognitiveEvent,
    CognitiveEvent as Event,        # old name
    Priority,
    ThrottleEvent,
    EfferenceCopyEvent,
    CoreState,
    SubjectiveField,
    Kernel,
    KernelAPI,
)
from core.event_bus import EventBus
from core.attention_router import AttentionRouter as AttentionKernel  # old name

__all__ = [
    "CognitiveModule",
    "CognitiveEvent",
    "Event",
    "Priority",
    "ThrottleEvent",
    "EfferenceCopyEvent",
    "CoreState",
    "SubjectiveField",
    "Kernel",
    "KernelAPI",
    "EventBus",
    "AttentionKernel",
]
