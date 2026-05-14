"""Connector — bridge between FastAPI web UI and the PCA Kernel.

This module:
  1. Imports Kernel and KernelAPI from kernel_main.
  2. Starts the kernel in a background thread with its own event loop.
  3. Exposes async functions that FastAPI endpoints can await.
  4. Provides a queue of JSON state updates that the WebSocket endpoint can consume.

Typical usage from a FastAPI module::

    from interfaces.web_ui.connector import kernel_connector
    from fastapi import FastAPI, WebSocket

    app = FastAPI()

    @app.on_event("startup")
    async def startup():
        await kernel_connector.start()

    @app.on_event("shutdown")
    async def shutdown():
        await kernel_connector.stop()

    @app.get("/api/state")
    async def get_state():
        return kernel_connector.get_state()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        queue = kernel_connector.subscribe_state_updates()
        try:
            while True:
                msg = await queue.get()
                await websocket.send_text(msg)
        except Exception:
            pass
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from asyncio import Queue
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Kernel imports — allow running while the root is on PYTHONPATH or similar
# ---------------------------------------------------------------------------
try:
    from kernel_main import Kernel, KernelAPI, Priority, Event
except ImportError:  # pragma: no cover
    import sys, os

    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.abspath(os.path.join(_here, "..", ".."))
    sys.path.insert(0, _root)
    from kernel_main import Kernel, KernelAPI, Priority, Event

logger = logging.getLogger("connector")


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------
class KernelConnector:
    """Manages a Kernel instance running in a background thread.

    Attributes:
        kernel_api: The KernelAPI wrapper instance (valid after start()).
        state_queue: An asyncio.Queue that receives JSON state strings
                     whenever the kernel broadcasts an update.
    """

    def __init__(self, tick_rate: float = 0.1) -> None:
        self._tick_rate = tick_rate
        self._kernel_api: Optional[KernelAPI] = None

        # Book-keeping for the background thread
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

        # Queue of JSON-encoded state updates (for WebSocket consumers)
        self.state_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)

        # Internal subscriber list so we can broadcast into *state_queue*
        self._subscriptions: List[Queue] = [self.state_queue]

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Create the kernel, wrap it in KernelAPI, and start it in a background thread.

        FastAPI's `on_event("startup")` should call this.
        """
        if self._running:
            return
        self._running = True

        kernel = Kernel(tick_rate=self._tick_rate)
        self._kernel_api = KernelAPI(kernel)

        # Register a callback so broadcast_state() pushes into our queue
        def _enqueue(payload: str) -> None:
            try:
                # Best-effort put — run in our loop if available, otherwise ignore
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(self._enqueue_state, payload)
            except Exception:
                pass

        self._kernel_api._ws_clients.append(_enqueue)

        # Start in a background thread with its own event loop
        def _thread_target() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_kernel())
            finally:
                self._loop = None

        self._thread = threading.Thread(target=_thread_target, daemon=True)
        self._thread.start()

    async def _run_kernel(self) -> None:
        """Internal: start the KernelAPI background runner."""
        if self._kernel_api is not None:
            self._kernel_api.start_in_background()

    async def stop(self) -> None:
        """Shutdown the kernel and join the background thread.

        FastAPI's `on_event("shutdown")` should call this.
        """
        self._running = False
        if self._kernel_api:
            self._kernel_api.shutdown()
        if self._thread:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _enqueue_state(self, payload: str) -> None:
        """Push a state payload into the queue (called from kernel thread)."""
        for q in self._subscriptions:
            if q is None or q.full():
                continue
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # API surface for FastAPI endpoints
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        """Return current kernel state."""
        if not self._kernel_api:
            return {"error": "kernel not started"}
        return self._kernel_api.get_state()

    def get_modules(self) -> list[dict]:
        if not self._kernel_api:
            return []
        return self._kernel_api.get_modules()

    def toggle_module(self, module_id: str) -> bool:
        if not self._kernel_api:
            return False
        result = self._kernel_api.toggle_module(module_id)
        self._kernel_api.broadcast_state()
        return result

    def set_focus(self, items: list[str]) -> None:
        if not self._kernel_api:
            return
        self._kernel_api.set_focus(items)
        self._kernel_api.broadcast_state()

    def get_events(self) -> list[dict]:
        if not self._kernel_api:
            return []
        return self._kernel_api.get_events()

    def emit_event(self, type_: str, data: dict, priority: str = "cognitive") -> None:
        if not self._kernel_api:
            return
        prio = Priority[priority.upper()] if priority.upper() in {p.name for p in Priority} else Priority.COGNITIVE
        self._kernel_api.emit_event(type_, data, prio)

    def load_module(self, path: str) -> bool:
        if not self._kernel_api:
            return False
        return self._kernel_api.load_module(path)

    def subscribe_state_updates(self) -> asyncio.Queue[str]:
        """Return a new queue that will receive JSON state updates.

        FastAPI WebSocket endpoint should use this to stream state to the client.
        """
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscriptions.append(q)
        return q

    def unsubscribe_state_updates(self, queue: asyncio.Queue[str]) -> None:
        """Remove a previously-subscribed queue."""
        if queue in self._subscriptions:
            self._subscriptions.remove(queue)

    # ------------------------------------------------------------------
    # Convenience: JSON helpers
    # ------------------------------------------------------------------
    def get_state_json(self) -> str:
        """Return current kernel state as a JSON string."""
        return json.dumps(self.get_state())


# ---------------------------------------------------------------------------
# Global singleton connector instance (imported by FastAPI app)
# ---------------------------------------------------------------------------
kernel_connector = KernelConnector()
