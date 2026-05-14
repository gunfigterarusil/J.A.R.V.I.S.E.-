"""core/kernel.py — Cognitive Runtime Kernel + KernelAPI.

The Kernel is the minimal runtime that:
  - owns the event loop and tick clock
  - holds the module registry
  - routes attention budget each tick
  - dispatches queued events
  - does NOT own emotions, memory, goals, or LLM logic

KernelAPI is the synchronous/async bridge for the web UI and external tools.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from core.event_bus import EventBus, CognitiveEvent, Priority, ThrottleEvent
from core.state import CoreState, SubjectiveField
from core.attention_router import AttentionRouter
from core.scheduler import Scheduler
from core.persistence import PersistenceManager
from core.module_manager import ModuleManager
from core.lifecycle import LifecycleManager
from core.module_base import CognitiveModule
from core.safety import (
    ActionFirewall, SafetyConstitution, RiskEngine,
    PermissionManager, PermissionLevel, Sandbox, AuditLog,
)
from core.llm_router import LLMRouter

if TYPE_CHECKING:
    from config import KernelConfig

logger = logging.getLogger("core.kernel")

TICK_RATE = 0.1   # seconds between ticks


class Kernel:
    """Cognitive runtime — tick loop, module registry, event dispatch."""

    def __init__(self, config: Optional["KernelConfig"] = None,
                 tick_rate: float = TICK_RATE) -> None:
        self.config = config
        self.tick_rate = tick_rate

        # Core subsystems
        self.event_bus = EventBus()
        self.event_bus.set_kernel(self)

        self.core_state = CoreState()
        self.subjective_field = SubjectiveField()
        self.attention_router = AttentionRouter()
        self.scheduler = Scheduler()
        self.module_manager = ModuleManager()
        self.module_manager.set_kernel(self)
        self.lifecycle = LifecycleManager()

        # Persistence directory from config or default
        persist_dir = "~/.jarvis_brain"
        if config and hasattr(config, "persistence_dir"):
            persist_dir = config.persistence_dir
        self.persistence = PersistenceManager(persist_dir)

        # Module registry
        self.modules: Dict[str, CognitiveModule] = {}

        # ── LLM Router — swappable AI provider abstraction ──────────────────
        llm_cfg = config.llm if (config and hasattr(config, "llm")) else None
        self.llm_router = LLMRouter(llm_cfg)

        # ── Safety layer — ALWAYS active, cannot be unloaded ────────────────
        self.audit_log = AuditLog(self.persistence._base)
        sandbox_allowed = list(getattr(config, "sandbox_extra_paths", []) if config else [])
        if config is not None:
            sandbox_allowed.extend([
                getattr(config, "persistence_dir", "~/.jarvis_brain"),
                getattr(getattr(config, "actions", None), "workspace_path", "~/jarvis_workspace"),
            ])
        self.sandbox = Sandbox(extra_allowed=sandbox_allowed)
        self.constitution = SafetyConstitution()
        self.risk_engine = RiskEngine()
        self.permission_manager = PermissionManager(
            default_level=PermissionLevel(
                getattr(config, "safety_default_level", 1) if config else 1
            )
        )
        self.permission_manager.load(self.persistence)
        self.safety = ActionFirewall(
            constitution=self.constitution,
            risk_engine=self.risk_engine,
            permission_manager=self.permission_manager,
            sandbox=self.sandbox,
            audit_log=self.audit_log,
        )
        # Sync initial safety_level into CoreState
        self.core_state.safety_level = int(self.permission_manager.current_level)

        self.running = False
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # Module registration
    # ------------------------------------------------------------------
    def register_module(self, module: CognitiveModule) -> None:
        if module.module_id in self.modules:
            logger.warning(f"[Kernel] Module {module.module_id} already registered — skipping")
            return
        self.modules[module.module_id] = module
        module.initialize(self)
        if module.module_id not in self.core_state.active_modules:
            self.core_state.active_modules.append(module.module_id)
        logger.debug(f"[Kernel] Registered module: {module.module_id}")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self.running = True
        self._start_time = time.time()

        # Async startup (scheduler, kernel_started event)
        await self.lifecycle.async_startup(self)

        logger.info("[Kernel] Cognitive runtime started")
        last = time.time()

        try:
            while self.running:
                now = time.time()
                dt = now - last
                last = now

                # Update kernel bookkeeping
                self.core_state.update(now)
                self.core_state.uptime = now - self._start_time
                self.subjective_field.update_delta(dt, {})

                # Tick all selected modules
                await self._tick_modules(dt)

                # Dispatch queued events
                await self.event_bus._dispatch()

                # Sleep remainder of tick
                elapsed = time.time() - now
                sleep_time = self.tick_rate - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            pass
        finally:
            if self.running:
                await self.lifecycle.shutdown(self)
                self.running = False
            logger.info("[Kernel] Stopped")

    async def _tick_modules(self, dt: float) -> None:
        modules_list = [m for m in self.modules.values() if m.enabled]
        selected, throttled = self.attention_router.allocate(modules_list, self.core_state)

        for mod in selected:
            try:
                await mod.tick(dt)
            except Exception as exc:
                logger.error(f"[Kernel] Error ticking {mod.module_id}: {exc}")

        # Notify throttled modules
        for mod in throttled:
            try:
                evt = ThrottleEvent(mod.module_id)
                await mod.on_event(evt)
            except Exception:
                pass

    def shutdown(self) -> None:
        """Thread-safe synchronous shutdown trigger."""
        self.running = False
        self.permission_manager.save(self.persistence)


# ---------------------------------------------------------------------------
# KernelAPI — thin wrapper for web UI / external control
# ---------------------------------------------------------------------------
class KernelAPI:
    """Synchronous / async bridge around the Kernel for the web dashboard."""

    def __init__(self, kernel: Kernel, max_events: int = 100) -> None:
        self.kernel = kernel
        self._event_buffer: deque[dict] = deque(maxlen=max_events)
        self._ws_callbacks: List[Callable] = []
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._started = False

        # Tap into event bus trace to populate buffer
        original_emit = kernel.event_bus.emit

        def _tapping_emit(event: CognitiveEvent, priority: Priority) -> None:
            original_emit(event, priority)
            self._event_buffer.appendleft({
                "type": event.type,
                "data": event.data,
                "source_module": event.source_module,
                "attention_weight": event.attention_weight,
                "timestamp": event.timestamp,
            })

        kernel.event_bus.emit = _tapping_emit  # type: ignore[method-assign]

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        k = self.kernel
        return {
            "running": k.running,
            "tick_rate": k.tick_rate,
            "core_state": k.core_state.to_dict(),
            "subjective_field": k.subjective_field.to_dict(),
        }

    def get_modules(self) -> list[dict]:
        return [m.to_dict() for m in self.kernel.modules.values()]

    def get_events(self) -> list[dict]:
        return list(self._event_buffer)

    def toggle_module(self, module_id: str) -> bool:
        mod = self.kernel.modules.get(module_id)
        if mod is None:
            return False
        mod.enabled = not mod.enabled
        return True

    def set_focus(self, items: list[str]) -> None:
        self.kernel.core_state.active_focus = list(items)

    def emit_event(self, type_: str, data: dict,
                   priority: Priority = Priority.COGNITIVE) -> None:
        event = CognitiveEvent(type=type_, data=data, source_module="api")
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._async_emit(event, priority), self._loop
            )
        else:
            self.kernel.event_bus.emit(event, priority)

    async def _async_emit(self, event: CognitiveEvent, priority: Priority) -> None:
        self.kernel.event_bus.emit(event, priority)

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------
    def start_in_background(self) -> None:
        if self._started:
            return
        self._started = True

        def _run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.kernel.start())
            finally:
                loop.close()
                self._loop = None

        self._thread = threading.Thread(target=_run, daemon=True, name="kernel-thread")
        self._thread.start()

    def shutdown(self) -> None:
        self.kernel.shutdown()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._started = False

    # ------------------------------------------------------------------
    # WebSocket broadcasting
    # ------------------------------------------------------------------
    def broadcast_state(self) -> None:
        import json
        payload = json.dumps({"type": "state_update", "data": self.get_state()})
        for cb in list(self._ws_callbacks):
            try:
                cb(payload)
            except Exception as exc:
                logger.warning(f"[KernelAPI] broadcast error: {exc}")
