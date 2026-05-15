"""core/lifecycle.py — Startup and shutdown sequencing.

LifecycleManager orchestrates the boot and teardown order so the kernel
itself stays clean.  It does not own any state — it just calls the right
things in the right order.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.kernel import Kernel

logger = logging.getLogger("core.lifecycle")


class LifecycleManager:

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    def startup(self, kernel: "Kernel") -> None:
        """Synchronous portion of startup — called before asyncio loop runs."""
        logger.info("[Lifecycle] Starting up...")

        # 1. Restore persisted CoreState (consciousness, energy, temporal marker …)
        kernel.persistence.restore_core_state(kernel.core_state)

        # 2. Auto-discover and load modules from configured tier paths
        if kernel.config and getattr(kernel.config, "module_auto_discover", False):
            paths = getattr(kernel.config, "module_tier_paths", [])
            count = kernel.module_manager.load_all(paths)
            logger.info(f"[Lifecycle] Auto-loaded {count} module(s) from tier paths")

            if kernel.module_manager.degraded_mode():
                failed = kernel.module_manager.get_failed_modules()
                logger.warning(
                    f"[Lifecycle] {len(failed)} module(s) failed to load — running in degraded mode"
                )
                from core.event_bus import CognitiveEvent, Priority
                kernel.event_bus.emit(
                    CognitiveEvent(
                        type="kernel_degraded",
                        source_module="lifecycle",
                        data={
                            "failed_modules": failed,
                            "message": (
                                f"{len(failed)} module(s) failed to load. "
                                "Some features may be unavailable."
                            ),
                        },
                    ),
                    Priority.COGNITIVE,
                )

    async def async_startup(self, kernel: "Kernel") -> None:
        """Async portion — called after asyncio loop is running."""
        # Start the scheduler inside the running loop
        kernel.scheduler.start(asyncio.get_event_loop())

        # Emit kernel_started event
        from core.event_bus import CognitiveEvent, Priority
        kernel.event_bus.emit(
            CognitiveEvent(type="kernel_started", source_module="lifecycle",
                           data={"timestamp": time.time()}),
            Priority.COGNITIVE,
        )
        logger.info("[Lifecycle] Kernel started event emitted")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    async def shutdown(self, kernel: "Kernel") -> None:
        """Graceful shutdown — call from kernel.shutdown()."""
        logger.info("[Lifecycle] Shutting down...")

        from core.event_bus import CognitiveEvent, Priority
        kernel.event_bus.emit(
            CognitiveEvent(type="kernel_stopping", source_module="lifecycle",
                           data={"timestamp": time.time()}),
            Priority.REALTIME,
        )

        # Drain in-flight events (max 2s)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            all_empty = all(
                q.empty() for q in kernel.event_bus.queues.values()
            )
            if all_empty:
                break
            await asyncio.sleep(0.05)

        # Shutdown all modules
        for mod in list(kernel.modules.values()):
            try:
                mod.shutdown()
            except Exception as exc:
                logger.error(f"[Lifecycle] Error shutting down {mod.module_id}: {exc}")

        # Checkpoint state
        kernel.persistence.checkpoint(kernel.core_state)
        kernel.scheduler.stop()
        logger.info("[Lifecycle] Shutdown complete")
