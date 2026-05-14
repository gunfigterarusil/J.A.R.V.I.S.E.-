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
        if getattr(event, "type", "") == "response_generated":
            text = str(event.data.get("text", "") or "")
            try:
                loop.call_soon_threadsafe(response_queue.put_nowait, text)
            except RuntimeError:
                pass

    loop = asyncio.get_running_loop()
    kernel.event_bus.emit = _capture_responses  # type: ignore[method-assign]
    kernel_task = asyncio.create_task(kernel.start())

    print("Jarvis chat mode. Type /see to read the screen, /exit to stop.\n")
    try:
        while kernel.running or not kernel_task.done():
            user_text = await asyncio.to_thread(input, "You: ")
            user_text = user_text.strip()
            if not user_text:
                continue
            if user_text.lower() in {"/exit", "/quit", "exit", "quit"}:
                break

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
