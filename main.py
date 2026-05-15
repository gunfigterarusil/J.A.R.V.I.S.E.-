"""main.py — JAV Cognitive Brain entry point.

Stable repaired entry point.

Usage:
    python main.py                  # kernel only/headless
    python main.py --doctor         # diagnostics
    python main.py --chat           # terminal chat
    python main.py --desktop        # desktop UI
    python main.py --web            # web dashboard
    python main.py --init-portable  # create portable data folders/.env
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import KernelConfig
from core.kernel import Kernel, KernelAPI
from core.event_bus import Priority

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def build_kernel(cfg: KernelConfig) -> Kernel:
    kernel = Kernel(config=cfg)
    kernel.lifecycle.startup(kernel)
    logger.info("[Main] Kernel ready with %s module(s)", len(kernel.modules))
    return kernel


async def run_headless(kernel: Kernel) -> None:
    logger.info("[Main] Starting cognitive runtime (headless mode)")
    try:
        await kernel.start()
    except KeyboardInterrupt:
        pass
    finally:
        kernel.shutdown()


def run_with_web(host: str, port: int) -> None:
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install -r requirements.txt")
        sys.exit(1)
    url = f"http://{host}:{port}"
    logger.info("[Main] Starting web dashboard at %s", url)
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("interfaces.web_ui.app:app", host=host, port=port, reload=False, log_level="info")


def run_chat() -> None:
    # Keep interactive chat readable; run --doctor for verbose diagnostics.
    logging.getLogger().setLevel(logging.WARNING)
    cfg = KernelConfig()
    kernel = build_kernel(cfg)
    api = KernelAPI(kernel)
    api.start_in_background()
    # Give the background runtime a moment to enter its loop.
    deadline = time.time() + 3
    while not kernel.running and time.time() < deadline:
        time.sleep(0.05)
    print("JAV chat mode. Type /help or /exit.")
    last_seen = 0
    try:
        while True:
            try:
                text = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text.lower() in {"/exit", "exit", "quit", "/quit"}:
                break
            if text.lower() in {"/help", "help"}:
                print("JAV> Commands: /help /status /modules /memory /events /exit. Anything else is sent to the brain.")
                continue
            if text.lower() == "/status":
                state = api.get_state()
                cs = state.get("core_state", {})
                print(f"JAV> running={state.get('running')} uptime={cs.get('uptime', 0):.1f}s safety={cs.get('safety_level')}")
                continue
            if text.lower() == "/modules":
                mods = api.get_modules()
                print("JAV> " + ", ".join(m.get("module_id", "?") for m in mods))
                continue
            if text.lower() == "/events":
                for e in api.get_events()[:20]:
                    print(f" - {e.get('type')} from {e.get('source_module')}")
                continue
            if text.lower() == "/memory":
                print(f"JAV> Data dir: {Path(cfg.persistence_dir).expanduser()}")
                print("JAV> Basic memory module is active. SQLite/vector memory is queued for the next restoration step.")
                continue

            before = len(api.get_events())
            api.emit_event("user_utterance", {"text": text, "input_mode": "chat"}, Priority.REALTIME)
            deadline = time.time() + 45
            printed = False
            while time.time() < deadline:
                events = api.get_events()
                for e in events[: max(0, len(events) - before + 20)]:
                    if e.get("type") == "response_generated" and e.get("timestamp", 0) > last_seen:
                        last_seen = e.get("timestamp", 0)
                        print("JAV> " + e.get("data", {}).get("text", ""))
                        printed = True
                        break
                if printed:
                    break
                time.sleep(0.15)
            if not printed:
                print("JAV> No response yet. Check /events or run --doctor if this repeats.")
    finally:
        api.shutdown()


def init_portable(target: str | None = None) -> None:
    root = Path(target).expanduser().resolve() if target else _ROOT
    for sub in ["data/brain", "data/workspace", "data/screenshots", "data/brain/logs"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    env_path = root / ".env"
    if not env_path.exists():
        env_path.write_text(
            "JAV_PORTABLE=true\n"
            "JARVIS_DATA_DIR=data/brain\n"
            "ACTION_WORKSPACE_PATH=data/workspace\n"
            "SCREENSHOT_DIR=data/screenshots\n"
            "WEB_HOST=127.0.0.1\n"
            "WEB_PORT=8000\n"
            "GEMINI_API_KEY=\n"
            "OLLAMA_HOST=http://localhost:11434\n"
            "OLLAMA_MODEL=llama3.2\n",
            encoding="utf-8",
        )
    print(f"Portable JAV structure initialized at: {root}")


def main() -> None:
    parser = argparse.ArgumentParser(description="JAV Cognitive Brain Runtime")
    parser.add_argument("--web", action="store_true", help="Start web dashboard")
    parser.add_argument("--chat", action="store_true", help="Start terminal chat")
    parser.add_argument("--desktop", action="store_true", help="Start desktop UI")
    parser.add_argument("--doctor", action="store_true", help="Run diagnostics")
    parser.add_argument("--init-portable", nargs="?", const="", help="Create portable data folders and .env")
    parser.add_argument("--host", default=None, help="Web UI host")
    parser.add_argument("--port", type=int, default=None, help="Web UI port")
    args = parser.parse_args()

    if args.doctor:
        from scripts.doctor import run_doctor
        raise SystemExit(run_doctor(_ROOT))

    if args.init_portable is not None:
        init_portable(args.init_portable or None)
        return

    cfg = KernelConfig()

    if args.desktop:
        try:
            from interfaces.desktop.desktop_app import run_desktop
            run_desktop()
        except Exception as exc:
            log_dir = Path(cfg.persistence_dir).expanduser() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            crash = log_dir / "desktop_crash.log"
            crash.write_text(str(exc), encoding="utf-8")
            print(f"Desktop failed: {exc}\nCrash log: {crash}")
            raise SystemExit(1)
        return

    if args.chat:
        run_chat()
        return

    if args.web:
        run_with_web(args.host or cfg.web_host, args.port or cfg.web_port)
        return

    kernel = build_kernel(cfg)
    asyncio.run(run_headless(kernel))


if __name__ == "__main__":
    main()
