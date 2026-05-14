"""core/scheduler.py — Delayed and periodic task scheduler.

The Scheduler runs inside the kernel's asyncio event loop.
Modules use it via:
  kernel.scheduler.schedule_once(fn, delay_sec)
  kernel.scheduler.schedule_repeating(fn, interval_sec, task_id)
  kernel.scheduler.cancel(task_id)

This replaces all the ad-hoc `if now - self._last_x > interval` patterns
scattered through modules.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("core.scheduler")


class Scheduler:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._id_counter = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._running = True

    def stop(self) -> None:
        self._running = False
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def _next_id(self) -> str:
        self._id_counter += 1
        return f"sched_{self._id_counter}"

    def schedule_once(self, fn: Callable, delay: float,
                      task_id: Optional[str] = None) -> str:
        """Run fn() once after `delay` seconds. Returns task_id."""
        tid = task_id or self._next_id()

        async def _run() -> None:
            await asyncio.sleep(delay)
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error(f"[Scheduler] once task {tid} error: {exc}")
            finally:
                self._tasks.pop(tid, None)

        if self._loop and self._running:
            task = self._loop.create_task(_run())
            self._tasks[tid] = task
        return tid

    def schedule_repeating(self, fn: Callable, interval: float,
                           task_id: Optional[str] = None) -> str:
        """Run fn() every `interval` seconds until cancelled. Returns task_id."""
        tid = task_id or self._next_id()

        async def _run() -> None:
            while self._running:
                await asyncio.sleep(interval)
                try:
                    result = fn()
                    if asyncio.iscoroutine(result):
                        await result
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error(f"[Scheduler] repeating task {tid} error: {exc}")

        if self._loop and self._running:
            task = self._loop.create_task(_run())
            self._tasks[tid] = task
        return tid

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.pop(task_id, None)
        if task:
            task.cancel()
            return True
        return False

    @property
    def active_count(self) -> int:
        return len(self._tasks)
