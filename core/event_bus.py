"""core/event_bus.py — CognitiveEvent + async EventBus.

The EventBus is the sole communication channel between the kernel and all
modules.  Modules NEVER call each other directly; they emit events and
subscribe to event types they care about.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from core.kernel import Kernel

logger = logging.getLogger("core.event_bus")

# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------
class Priority(Enum):
    REALTIME = 0    # danger, hormone spikes, user input
    COGNITIVE = 1   # thoughts, goals, responses
    BACKGROUND = 2  # mood drift, dream, learning


# ---------------------------------------------------------------------------
# CognitiveEvent
# ---------------------------------------------------------------------------
_event_id_counter = itertools.count(start=1)


@dataclass
class CognitiveEvent:
    type: str
    data: dict = field(default_factory=dict)
    source_module: str = ""
    causal_parent_id: Optional[int] = None   # id of the event that caused this one
    emotional_weight: float = 0.0            # enriched by AttentionRouter
    attention_weight: float = 0.0            # enriched by AttentionRouter
    timestamp: float = field(default_factory=time.time)
    _id: int = field(default_factory=lambda: next(_event_id_counter))


# Legacy alias so old code using `Event` still works after shim import
Event = CognitiveEvent


# ---------------------------------------------------------------------------
# Specialised event subclasses (kept for semantic clarity)
# ---------------------------------------------------------------------------
class ThrottleEvent(CognitiveEvent):
    def __init__(self, module_id: str, timestamp: Optional[float] = None) -> None:
        super().__init__(
            type="throttle",
            data={"module_id": module_id},
            source_module="kernel",
            timestamp=timestamp or time.time(),
        )


class EfferenceCopyEvent(CognitiveEvent):
    def __init__(self, action: str, predicted_sensory_change: str,
                 source_module: str = "", timestamp: Optional[float] = None) -> None:
        super().__init__(
            type="efference_copy",
            data={"action": action, "predicted_change": predicted_sensory_change},
            source_module=source_module,
            timestamp=timestamp or time.time(),
        )


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------
class EventBus:
    """Async message bus with three priority queues.

    Routing:
    - Each module registers for a list of event types (or "*" for all).
    - On dispatch the bus iterates REALTIME → COGNITIVE → BACKGROUND and
      calls `module.on_event()` for every matching subscriber.
    - Supports delayed emission via `emit_after(event, delay, priority)`.
    """

    TRACE_SIZE = 200  # last N events kept for debugging

    def __init__(self) -> None:
        self.queues: dict[Priority, asyncio.PriorityQueue] = {
            Priority.REALTIME: asyncio.PriorityQueue(),
            Priority.COGNITIVE: asyncio.PriorityQueue(),
            Priority.BACKGROUND: asyncio.PriorityQueue(),
        }
        # module_id → set of event types it wants
        self._consumers: dict[str, set[str]] = {}
        # event_type → list[module_id]
        self._type_to_modules: dict[str, list[str]] = {}
        # rolling debug trace
        self.trace: deque[CognitiveEvent] = deque(maxlen=self.TRACE_SIZE)
        # back-reference set by Kernel after construction
        self._kernel: Optional["Kernel"] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register_consumer(self, module_id: str, event_types: list[str]) -> None:
        self._consumers[module_id] = set(event_types)
        for et in event_types:
            self._type_to_modules.setdefault(et, []).append(module_id)

    def unregister_consumer(self, module_id: str) -> None:
        types = self._consumers.pop(module_id, set())
        for et in types:
            lst = self._type_to_modules.get(et, [])
            if module_id in lst:
                lst.remove(module_id)

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------
    def emit(self, event: CognitiveEvent, priority: Priority) -> None:
        self.trace.append(event)
        q = self.queues[priority]
        # tuple: (priority_val, timestamp, unique_id, event)
        q.put_nowait((priority.value, event.timestamp, event._id, event))

    def emit_after(self, event: CognitiveEvent, delay: float,
                   priority: Priority = Priority.COGNITIVE) -> None:
        """Schedule an event to be emitted after `delay` seconds."""
        if self._kernel and self._kernel.scheduler:
            self._kernel.scheduler.schedule_once(
                lambda: self.emit(event, priority), delay
            )
        else:
            # Fallback: emit immediately if scheduler not ready
            self.emit(event, priority)

    # ------------------------------------------------------------------
    # Dispatch (called by Kernel each tick)
    # ------------------------------------------------------------------
    async def _dispatch(self) -> None:
        for prio in (Priority.REALTIME, Priority.COGNITIVE, Priority.BACKGROUND):
            q = self.queues[prio]
            while not q.empty():
                _, _ts, _uid, event = q.get_nowait()
                await self._route_event(event)

    async def _route_event(self, event: CognitiveEvent) -> None:
        if self._kernel is None:
            return

        # ── Safety intercept ────────────────────────────────────────────────
        # action_request events NEVER reach modules directly.
        # They are validated by the ActionFirewall first.
        if event.type == "action_request":
            safety = getattr(self._kernel, "safety", None)
            if safety is not None:
                result = await safety.validate(event)
                # Keep core_state in sync
                cs = self._kernel.core_state
                if result.rule_violated:
                    cs.last_violation = result.rule_violated
                cs.safety_level = int(self._kernel.permission_manager.current_level)

                if result.requires_confirmation:
                    # Need user Y/N — emit pending event
                    action_type = event.data.get("action_type", "unknown")
                    if action_type not in cs.pending_confirmations:
                        cs.pending_confirmations.append(action_type)
                    pending = safety._make_pending_event(event, result)
                    self.emit(pending, Priority.COGNITIVE)
                elif result.allowed:
                    approved = safety._make_approved_event(event)
                    self.emit(approved, Priority.REALTIME)
                else:
                    denied = safety._make_denied_event(event, result)
                    # Also emit safety_violation for hard constitution blocks
                    if result.rule_violated:
                        self.emit(
                            CognitiveEvent(
                                type="safety_violation",
                                data={
                                    "rule": result.rule_violated,
                                    "action_type": event.data.get("action_type", "unknown"),
                                    "source_module": event.source_module,
                                },
                                source_module="safety_firewall",
                                causal_parent_id=event._id,
                            ),
                            Priority.REALTIME,
                        )
                    self.emit(denied, Priority.COGNITIVE)
            return  # raw action_request never reaches modules

        # ── Permission grant/deny from user ─────────────────────────────────
        if event.type == "user_permission_grant":
            perm = getattr(self._kernel, "permission_manager", None)
            if perm is not None:
                action_type = event.data.get("action_type", "")
                if action_type:
                    perm.grant(action_type)
                    cs = self._kernel.core_state
                    if action_type in cs.pending_confirmations:
                        cs.pending_confirmations.remove(action_type)
                    # Re-emit as approved so the original requester can proceed
                    self.emit(
                        CognitiveEvent(
                            type="action_approved",
                            data=event.data,
                            source_module="safety_firewall",
                        ),
                        Priority.REALTIME,
                    )
            return

        if event.type == "user_permission_deny":
            perm = getattr(self._kernel, "permission_manager", None)
            if perm is not None:
                action_type = event.data.get("action_type", "")
                if action_type:
                    perm.deny(action_type)
                    cs = self._kernel.core_state
                    if action_type in cs.pending_confirmations:
                        cs.pending_confirmations.remove(action_type)
            return

        # ── Normal routing for all other events ─────────────────────────────
        targets = list(dict.fromkeys(
            self._type_to_modules.get(event.type, [])
            + self._type_to_modules.get("*", [])
        ))
        for mid in targets:
            mod = self._kernel.modules.get(mid)
            if mod is None or not mod.enabled:
                continue
            try:
                await mod.on_event(event)
            except Exception as exc:
                logger.error(f"Error routing {event.type} → {mid}: {exc}")

    def set_kernel(self, kernel: "Kernel") -> None:
        self._kernel = kernel
