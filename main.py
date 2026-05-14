"""main.py — Cognitive Brain entry point.

Starts the cognitive runtime kernel with all tier modules auto-discovered.

Usage:
    python main.py                  # kernel only (headless)
    python main.py --web            # kernel + web dashboard on port 8000
    python main.py --voice          # kernel + microphone STT + Piper/pyttsx3 TTS
    python main.py --chat           # terminal dialogue loop
    python main.py --web --port 9000
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import webbrowser
from pathlib import Path

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import KernelConfig
from core.kernel import Kernel, KernelAPI
from core.lifecycle import LifecycleManager
from core.event_bus import CognitiveEvent, Priority
from core.safety.permission_manager import PermissionLevel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def build_kernel(cfg: KernelConfig) -> Kernel:
    """Create kernel — lifecycle.startup() handles module discovery."""
    kernel = Kernel(config=cfg)
    kernel.lifecycle.startup(kernel)
    logger.info(f"[Main] Kernel ready with {len(kernel.modules)} module(s)")
    return kernel


async def run_headless(kernel: Kernel) -> None:
    """Run kernel without web UI until Ctrl+C."""
    logger.info("[Main] Starting cognitive runtime (headless mode)")
    try:
        await kernel.start()
    except KeyboardInterrupt:
        pass
    finally:
        kernel.shutdown()


async def run_with_voice(kernel: Kernel) -> None:
    """Run kernel and voice interface in the same asyncio loop."""
    from interfaces.voice.voice_loop import VoiceLoop

    logger.info("[Main] Starting cognitive runtime with voice interface")
    voice = VoiceLoop(kernel)
    kernel_task = asyncio.create_task(kernel.start())
    voice_task = asyncio.create_task(voice.run())

    try:
        done, pending = await asyncio.wait(
            {kernel_task, voice_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exc = task.exception()
            if exc:
                raise exc
    except KeyboardInterrupt:
        pass
    finally:
        voice.stop()
        kernel.shutdown()
        for task in (kernel_task, voice_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(kernel_task, voice_task, return_exceptions=True)


async def run_with_chat(kernel: Kernel) -> None:
    """Run kernel with an interactive terminal dialogue loop."""
    logger.info("[Main] Starting cognitive runtime with terminal chat")

    response_queue: asyncio.Queue[str] = asyncio.Queue()
    original_emit = kernel.event_bus.emit

    def _capture_responses(event, priority):
        original_emit(event, priority)
        et = getattr(event, "type", "")
        text = ""
        if et == "response_generated":
            text = str(event.data.get("text", "") or "")
        elif et == "sleep_cycle_completed":
            text = "Sleep cycle completed. " + str(event.data.get("summary", "") or "")
        elif et == "dream_narrative":
            # Keep dream narratives available in chat only when manually requested.
            if event.data.get("requested_by") == "cli_chat":
                text = str(event.data.get("narrative", "") or "")
        elif et == "action_result":
            # Usually action_executor also emits response_generated, but keep this fallback.
            if event.data.get("respond_fallback"):
                text = str(event.data)
        if text:
            try:
                loop.call_soon_threadsafe(response_queue.put_nowait, text)
            except RuntimeError:
                pass

    loop = asyncio.get_running_loop()
    kernel.event_bus.emit = _capture_responses  # type: ignore[method-assign]
    kernel_task = asyncio.create_task(kernel.start())

    def emit_action(action_type: str, payload: dict, respond: bool = True) -> None:
        payload = dict(payload)
        request_id = payload.get("request_id") or f"cli_action_{int(__import__('time').time() * 1000)}"
        payload["request_id"] = request_id
        # The firewall expects an already resolved path for path-based checks.
        top_path = payload.get("path") or payload.get("cwd")
        if top_path:
            raw_path = Path(str(top_path)).expanduser()
            if not raw_path.is_absolute():
                workspace = Path(getattr(getattr(kernel.config, "actions", None), "workspace_path", "~/jarvis_workspace")).expanduser()
                top_path = str((workspace / raw_path).resolve())
            else:
                top_path = str(raw_path.resolve())
        kernel.event_bus.emit(
            CognitiveEvent(
                type="action_request",
                data={
                    "action_type": action_type,
                    "payload": payload,
                    "path": top_path,
                    "request_id": request_id,
                    "respond": respond,
                },
                source_module="cli_chat",
            ),
            Priority.REALTIME,
        )

    async def wait_action_response(timeout: float = 30.0) -> None:
        try:
            response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
            print(f"Jarvis: {response}\n")
        except asyncio.TimeoutError:
            print("Jarvis: No action response yet. Check whether action_executor is loaded and safety settings allow this action.\n")

    print("Jarvis chat mode. Type /see, /self, /world, /sleep, /dream, /consolidate, /actions, /ls, /read, /write, /search, /mkdir, /run, /safety, /approve, or /exit.\n")
    try:
        while kernel.running or not kernel_task.done():
            user_text = await asyncio.to_thread(input, "You: ")
            user_text = user_text.strip()
            if not user_text:
                continue
            if user_text.lower() in {"/exit", "/quit", "exit", "quit"}:
                break


            # V7 safe PC automation commands
            lower = user_text.lower()
            if lower in {"/actions", "/action-status", "/workspace"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="action_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response()
                continue

            if lower.startswith("/safety"):
                parts = user_text.split(maxsplit=1)
                if len(parts) == 1:
                    pm = kernel.permission_manager
                    print(f"Jarvis safety level: L{int(pm.current_level)} {pm.current_level.name}\n")
                else:
                    try:
                        level_int = int(parts[1].strip().lstrip("Ll"))
                        kernel.permission_manager.set_level(PermissionLevel(level_int))
                        kernel.core_state.safety_level = level_int
                        print(f"Jarvis: safety level set to L{level_int} {PermissionLevel(level_int).name}.\n")
                    except Exception as exc:
                        print(f"Jarvis: invalid safety level. Use /safety 0..6. Error: {exc}\n")
                continue

            if lower.startswith("/approve"):
                parts = user_text.split(maxsplit=1)
                if len(parts) < 2:
                    print("Jarvis: usage: /approve <pending_id>\n")
                else:
                    kernel.event_bus.emit(CognitiveEvent(type="v7_user_approval", data={"pending_id": parts[1].strip()}, source_module="cli_chat"), Priority.REALTIME)
                    await wait_action_response()
                continue

            if lower.startswith("/deny"):
                parts = user_text.split(maxsplit=1)
                if len(parts) < 2:
                    print("Jarvis: usage: /deny <pending_id>\n")
                else:
                    kernel.event_bus.emit(CognitiveEvent(type="v7_user_deny", data={"pending_id": parts[1].strip()}, source_module="cli_chat"), Priority.REALTIME)
                    await wait_action_response()
                continue

            if lower.startswith("/ls"):
                path = user_text.split(maxsplit=1)[1] if len(user_text.split(maxsplit=1)) > 1 else "."
                emit_action("list_files", {"path": path})
                await wait_action_response()
                continue

            if lower.startswith("/read "):
                path = user_text.split(maxsplit=1)[1].strip()
                emit_action("read_file", {"path": path})
                await wait_action_response()
                continue

            if lower.startswith("/search "):
                rest = user_text.split(maxsplit=1)[1].strip()
                # Syntax: /search query OR /search query :: path
                if "::" in rest:
                    query, path = [x.strip() for x in rest.split("::", 1)]
                else:
                    query, path = rest, "."
                emit_action("search_files", {"path": path, "query": query})
                await wait_action_response()
                continue

            if lower.startswith("/mkdir "):
                path = user_text.split(maxsplit=1)[1].strip()
                emit_action("create_dir", {"path": path})
                await wait_action_response()
                continue

            if lower.startswith("/write "):
                rest = user_text.split(maxsplit=1)[1]
                if "::" not in rest:
                    print("Jarvis: usage: /write <path> :: <content>\n")
                else:
                    path, content = [x.strip() for x in rest.split("::", 1)]
                    emit_action("write_file", {"path": path, "content": content})
                    await wait_action_response()
                continue

            if lower.startswith("/append "):
                rest = user_text.split(maxsplit=1)[1]
                if "::" not in rest:
                    print("Jarvis: usage: /append <path> :: <content>\n")
                else:
                    path, content = [x.strip() for x in rest.split("::", 1)]
                    emit_action("write_file", {"path": path, "content": content, "append": True})
                    await wait_action_response()
                continue

            if lower.startswith("/run "):
                command = user_text.split(maxsplit=1)[1].strip()
                emit_action("run_command", {"cwd": ".", "command": command})
                await wait_action_response(timeout=60.0)
                continue


            if user_text.lower() in {"/sleep", "/dream", "/consolidate", "/memory-consolidate"}:
                command = user_text.lower().lstrip("/")
                event_type = "sleep_cycle_requested" if command in {"sleep", "dream"} else "memory_consolidation_requested"
                kernel.event_bus.emit(
                    __import__("core.event_bus", fromlist=["CognitiveEvent"]).CognitiveEvent(
                        type=event_type,
                        data={
                            "reason": f"cli_command:{command}",
                            "force": True,
                            "respond": True,
                        },
                        source_module="cli_chat",
                    ),
                    __import__("core.event_bus", fromlist=["Priority"]).Priority.COGNITIVE,
                )
                try:
                    response = await asyncio.wait_for(response_queue.get(), timeout=20.0)
                    print(f"Jarvis: {response}\n")
                except asyncio.TimeoutError:
                    print("Jarvis: Sleep/consolidation module did not respond. Check whether dream module is loaded.\n")
                continue

            if user_text.lower() in {"/self", "/whoami", "/identity"}:
                mod = kernel.modules.get("self_model")
                if mod is None:
                    print("Jarvis: self_model module is not loaded.\n")
                else:
                    snap = mod.to_dict()
                    print("Jarvis self-model:")
                    print(f"- identity: {snap.get('identity_name')} / {snap.get('role')}")
                    print(f"- confidence: {snap.get('confidence')} reliability: {snap.get('reliability')} maturity: {snap.get('cognitive_maturity')}")
                    print(f"- interfaces: {', '.join(map(str, snap.get('active_interfaces', [])))}")
                    print(f"- capabilities: {', '.join(list((snap.get('capabilities') or {}).keys())[:12])}\n")
                continue

            if user_text.lower() in {"/world", "/context", "/projects"}:
                mod = kernel.modules.get("world_model")
                if mod is None:
                    print("Jarvis: world_model module is not loaded.\n")
                else:
                    snap = mod.to_dict()
                    print("Jarvis world-model:")
                    print(f"- active projects: {', '.join(map(str, snap.get('active_projects', [])))}")
                    print(f"- open loops: {snap.get('open_loop_count')} patterns: {snap.get('pattern_count')}")
                    print(f"- top intents: {snap.get('top_intents')}")
                    print(f"- environment: {snap.get('environment')}\n")
                continue

            if user_text.lower() in {"/see", "/screen", "/read-screen", "/explain-screen"}:
                request_id = f"cli_screen_{int(__import__('time').time())}"
                kernel.event_bus.emit(
                    __import__("core.event_bus", fromlist=["CognitiveEvent"]).CognitiveEvent(
                        type="screen_capture_requested",
                        data={
                            "request_id": request_id,
                            "reason": "cli_user_requested_screen_read",
                            "respond": True,
                        },
                        source_module="cli_chat",
                    ),
                    __import__("core.event_bus", fromlist=["Priority"]).Priority.REALTIME,
                )
            else:
                kernel.event_bus.emit(
                    __import__("core.event_bus", fromlist=["CognitiveEvent"]).CognitiveEvent(
                        type="user_utterance",
                        data={"text": user_text, "input_mode": "cli"},
                        source_module="cli_chat",
                    ),
                    __import__("core.event_bus", fromlist=["Priority"]).Priority.REALTIME,
                )
            try:
                response = await asyncio.wait_for(response_queue.get(), timeout=90.0)
                print(f"Jarvis: {response}\n")
            except asyncio.TimeoutError:
                print("Jarvis: No response yet. Check the LLM provider or logs.\n")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        kernel.shutdown()
        if not kernel_task.done():
            kernel_task.cancel()
        await asyncio.gather(kernel_task, return_exceptions=True)


def run_with_web(kernel: Kernel, host: str, port: int) -> None:
    """Start kernel in background thread, serve web UI in main thread."""
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install uvicorn fastapi")
        sys.exit(1)

    api = KernelAPI(kernel)
    api.start_in_background()
    logger.info(f"[Main] Cognitive runtime running in background. Dashboard at http://{host}:{port}")

    # Re-use the web UI app which also starts the kernel
    # For standalone, just run uvicorn against interfaces.web_ui.app
    uvicorn.run(
        "interfaces.web_ui.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


def main() -> None:
    cfg = KernelConfig()

    parser = argparse.ArgumentParser(description="Cognitive Brain Runtime")
    parser.add_argument("--web", action="store_true", help="Start web dashboard")
    parser.add_argument("--voice", action="store_true", help="Start voice mode: microphone STT + Piper/pyttsx3 TTS")
    parser.add_argument("--chat", action="store_true", help="Start terminal dialogue mode")
    parser.add_argument("--host", default=cfg.web_host, help="Web UI host")
    parser.add_argument("--port", type=int, default=cfg.web_port, help="Web UI port")
    args = parser.parse_args()

    selected_modes = sum(1 for enabled in (args.web, args.voice, args.chat) if enabled)
    if selected_modes > 1:
        logger.error("--web, --voice and --chat are separate modes for now. Start one at a time.")
        sys.exit(2)

    if args.web:
        # The web UI app manages its own kernel lifecycle
        try:
            import uvicorn
        except ImportError:
            logger.error("uvicorn not installed. Run: pip install uvicorn fastapi")
            sys.exit(1)
        url = f"http://{args.host}:{args.port}"
        logger.info(f"[Main] Starting web dashboard at {url}")
        # Open browser after server has had 1.5s to start
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        uvicorn.run(
            "interfaces.web_ui.app:app",
            host=args.host,
            port=args.port,
            reload=False,
            log_level="info",
        )
    elif args.voice:
        cfg.voice.enabled = True
        kernel = build_kernel(cfg)
        asyncio.run(run_with_voice(kernel))
    elif args.chat:
        kernel = build_kernel(cfg)
        asyncio.run(run_with_chat(kernel))
    else:
        kernel = build_kernel(cfg)
        asyncio.run(run_headless(kernel))


if __name__ == "__main__":
    main()
