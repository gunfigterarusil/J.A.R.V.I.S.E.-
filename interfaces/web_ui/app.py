"""
interfaces/web_ui/app.py — Cognitive Brain Web Dashboard

FastAPI server wired to the real Kernel via KernelAPI.
All state, events, and module data come from the live cognitive runtime —
no fake simulation.

Run:
    python -m uvicorn interfaces.web_ui.app:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    raise ImportError("Install: pip install fastapi uvicorn websockets")

from core.kernel import Kernel, KernelAPI
from core.event_bus import Priority, CognitiveEvent
from config import KernelConfig, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"

logger = logging.getLogger("web_ui")

# ---------------------------------------------------------------------------
# Build Kernel + KernelAPI  (module registration happens here)
# ---------------------------------------------------------------------------
def _build_kernel() -> KernelAPI:
    cfg = KernelConfig()
    kernel = Kernel(config=cfg)
    # lifecycle.startup() handles auto-discovery + state restore
    kernel.lifecycle.startup(kernel)
    logger.info(f"[WebUI] Kernel ready with {len(kernel.modules)} module(s)")
    return KernelAPI(kernel)


kernel_api: Optional[KernelAPI] = None


# ---------------------------------------------------------------------------
# WebSocket manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.discard(ws) if hasattr(self.connections, "discard") else None
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: str) -> None:
        dead: List[WebSocket] = []
        for ws in list(self.connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def _broadcast_loop() -> None:
    """Push kernel state to all WS clients every second."""
    while True:
        await asyncio.sleep(1.0)
        if kernel_api and manager.connections:
            try:
                payload = json.dumps({
                    "type": "state_update",
                    "data": kernel_api.get_state(),
                    "modules": kernel_api.get_modules(),
                })
                await manager.broadcast(payload)
            except Exception as exc:
                logger.warning(f"[WebUI] broadcast error: {exc}")


async def _event_broadcast_loop() -> None:
    """Push new kernel events to all WS clients every 250ms."""
    last_ts: float = 0.0
    while True:
        await asyncio.sleep(0.25)
        if not kernel_api or not manager.connections:
            continue
        try:
            events = kernel_api.get_events()
            new_events = [e for e in events if e.get("timestamp", 0) > last_ts]
            if new_events:
                last_ts = max(e.get("timestamp", 0) for e in new_events)
                payload = json.dumps({"type": "event_update", "events": new_events})
                await manager.broadcast(payload)
        except Exception as exc:
            logger.warning(f"[WebUI] event broadcast error: {exc}")


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global kernel_api
    kernel_api = _build_kernel()
    kernel_api.start_in_background()
    broadcast_task = asyncio.create_task(_broadcast_loop())
    event_task = asyncio.create_task(_event_broadcast_loop())
    logger.info("[WebUI] Kernel started in background thread")
    yield
    broadcast_task.cancel()
    event_task.cancel()
    if kernel_api:
        kernel_api.shutdown()
    logger.info("[WebUI] Shutdown complete")


app = FastAPI(
    title="Cognitive Brain Dashboard",
    description="Live monitoring and control for the persistent cognitive runtime",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.web_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def require_api_token(authorization: Optional[str] = Header(default=None)) -> None:
    """Protect control endpoints when WEB_UI_API_TOKEN is configured.

    Local development remains frictionless when the token is empty.
    For any exposed server, set WEB_UI_API_TOKEN and send:
    Authorization: Bearer <token>
    """
    token = config.web_api_token
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid API token")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    tmpl = TEMPLATES_DIR / "index.html"
    if not tmpl.exists():
        return HTMLResponse("<h1>Cognitive Brain — Dashboard template not found</h1>")
    return HTMLResponse(content=tmpl.read_text(encoding="utf-8"))


@app.get("/api/state")
async def get_state():
    if not kernel_api:
        raise HTTPException(503, "Kernel not ready")
    return kernel_api.get_state()


@app.get("/api/modules")
async def get_modules():
    if not kernel_api:
        raise HTTPException(503, "Kernel not ready")
    return kernel_api.get_modules()


@app.post("/api/modules/{module_id}/toggle")
async def toggle_module(module_id: str, _auth: None = Depends(require_api_token)):
    if not kernel_api:
        raise HTTPException(503, "Kernel not ready")
    success = kernel_api.toggle_module(module_id)
    if not success:
        raise HTTPException(404, f"Module '{module_id}' not found")
    return {"success": True, "module_id": module_id}


@app.post("/api/focus")
async def set_focus(body: dict, _auth: None = Depends(require_api_token)):
    if not kernel_api:
        raise HTTPException(503, "Kernel not ready")
    items = body.get("focus", [])
    if not isinstance(items, list):
        raise HTTPException(400, "focus must be a list of strings")
    kernel_api.set_focus(items)
    return {"success": True, "focus": items}


@app.get("/api/events")
async def get_events():
    if not kernel_api:
        raise HTTPException(503, "Kernel not ready")
    return kernel_api.get_events()


@app.post("/api/event/emit")
async def emit_event(body: dict, _auth: None = Depends(require_api_token)):
    if not kernel_api:
        raise HTTPException(503, "Kernel not ready")
    event_type = body.get("type", "custom")
    data = body.get("data", {})
    priority_str = body.get("priority", "cognitive").upper()
    priority = Priority[priority_str] if priority_str in Priority.__members__ else Priority.COGNITIVE
    kernel_api.emit_event(event_type, data, priority)
    return {"success": True, "type": event_type}


@app.post("/api/shutdown")
async def shutdown(_auth: None = Depends(require_api_token)):
    if kernel_api:
        asyncio.create_task(_delayed_shutdown())
    return {"success": True, "message": "Shutdown initiated"}


async def _delayed_shutdown() -> None:
    await asyncio.sleep(0.5)
    if kernel_api:
        kernel_api.shutdown()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                action = msg.get("action")
                if action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
                elif action == "get_state" and kernel_api:
                    await websocket.send_text(json.dumps({
                        "type": "state_update",
                        "data": kernel_api.get_state(),
                    }))
                elif action == "chat" and kernel_api:
                    text = msg.get("text", "").strip()
                    if text:
                        kernel_api.emit_event(
                            "user_utterance", {"text": text}, Priority.REALTIME
                        )
                elif action == "emit_event" and kernel_api:
                    # WebSocket control actions are intended for local/dev dashboard usage.
                    # Do not expose the dashboard publicly without a reverse proxy/VPN.
                    kernel_api.emit_event(
                        msg.get("event_type", "custom"),
                        msg.get("data", {}),
                    )
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "msg": "Invalid JSON"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"[WebUI] WS error: {exc}")
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cfg = KernelConfig()
    uvicorn.run(
        "interfaces.web_ui.app:app",
        host=cfg.web_host,
        port=cfg.web_port,
        reload=cfg.ws_reload,
    )
