"""main.py — Cognitive Brain entry point.

Starts the cognitive runtime kernel with all tier modules auto-discovered.

Usage:
    python main.py                  # kernel only (headless)
    python main.py --web            # kernel + web dashboard on port 8000
    python main.py --voice          # kernel + microphone STT + Piper/pyttsx3 TTS
    python main.py --chat           # terminal dialogue loop
    python main.py --desktop        # native desktop app (Tkinter)
    python main.py --web --port 9000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure source/bundled resources and the movable app folder are importable.
# In PyInstaller onedir builds, Python resources live in sys._MEIPASS/_internal,
# while .env/data should live beside the executable so the app can be moved.
_RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
_ROOT = _APP_ROOT
for _path in (_RESOURCE_ROOT, _APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

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


def configure_runtime_logging(cfg: KernelConfig, service: bool = False) -> None:
    """Configure console + rotating file logging for long-running modes."""
    level_name = getattr(getattr(cfg, "logging", None), "level", "INFO")
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    fmt = getattr(getattr(cfg, "logging", None), "format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    datefmt = getattr(getattr(cfg, "logging", None), "date_format", "%H:%M:%S")
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root_logger.addHandler(stream)
    runtime = getattr(cfg, "runtime", None)
    if runtime is not None and bool(getattr(runtime, "log_to_file", True)):
        data_dir = Path(getattr(cfg, "persistence_dir", "~/.jarvis_brain")).expanduser()
        log_dir = Path(runtime.resolve_log_dir(str(data_dir))).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / ("jav_service.log" if service else "jav.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=int(getattr(runtime, "log_max_bytes", 2_097_152)),
            backupCount=int(getattr(runtime, "log_backup_count", 5)),
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        root_logger.addHandler(file_handler)
        logger.info("[Main] File logging enabled: %s", log_file)


def build_kernel(cfg: KernelConfig) -> Kernel:
    """Create kernel — lifecycle.startup() handles module discovery."""
    kernel = Kernel(config=cfg)
    kernel.lifecycle.startup(kernel)
    logger.info(f"[Main] Kernel ready with {len(kernel.modules)} module(s)")
    return kernel


async def run_headless(kernel: Kernel, mode_name: str = "headless") -> None:
    """Run kernel without UI until Ctrl+C/service signal."""
    logger.info("[Main] Starting cognitive runtime (%s mode)", mode_name)
    stop_event = asyncio.Event()

    def _request_stop(*_args) -> None:
        try:
            stop_event.set()
            kernel.shutdown()
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is not None:
                try:
                    loop.add_signal_handler(sig, _request_stop)
                except (NotImplementedError, RuntimeError, ValueError):
                    signal.signal(sig, lambda *_: _request_stop())
    except Exception:
        pass

    task = asyncio.create_task(kernel.start())
    try:
        if mode_name == "service":
            stop_task = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait({task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t is task:
                    exc = t.exception()
                    if exc:
                        raise exc
            for t in pending:
                t.cancel()
        else:
            await task
    except KeyboardInterrupt:
        _request_stop()
    finally:
        kernel.shutdown()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


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

    print("Jarvis chat mode. Type /models, /system, /proactive, /daily-summary, /model-health, /see, /vision, /gui, /gui-task, /gui-auto, /gui-step, /gui-status, /gui-cancel, /self, /world, /memory, /recall, /web-search, /web-learn, /task, /tasks, /task-step, /task-retry, /task-report, /task-auto, /skills, /skill, /learn-skill, /knowledge, /kg, /sleep, /dream, /consolidate, /actions, /repair, /apply-repair, /ls, /read, /write, /search, /mkdir, /run, /safety, /approve, or /exit. Natural language works too.\n")
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
            if lower in {"/memory", "/memory-status", "/storage"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="memory_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response()
                continue

            if lower.startswith("/recall ") or lower.startswith("/memory-search "):
                query = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="memory_search_requested", data={"query_text": query, "top_k": 8, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response()
                continue

            if lower in {"/models", "/model-status", "/model-health", "/model-profile"}:
                router = getattr(kernel, "llm_router", None)
                if router is None or not hasattr(router, "status"):
                    print("Jarvis: model router is not available.\n")
                else:
                    status = router.status(refresh=True)
                    print(f"Jarvis model router V10 profile: {status.get('profile')}")
                    for role in ["fast", "reason", "code", "critic", "vision", "embedding", "action"]:
                        info = (status.get("roles") or {}).get(role) or {}
                        print(f"- {role}: {info.get('provider', 'not configured')} available={info.get('available', False)}")
                    print(f"available providers: {', '.join(status.get('available') or [])}\n")
                continue

            if lower in {"/runtime", "/runtime-status", "/health", "/service-status"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="runtime_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response()
                continue

            if lower in {"/self-test", "/runtime-self-test", "/health-check"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="runtime_self_test_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response()
                continue

            if lower in {"/system", "/monitor", "/system-status", "/diagnose-system"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="system_diagnose_requested" if lower == "/diagnose-system" else "system_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=45.0)
                continue

            if lower in {"/proactive", "/proactive-status", "/companion"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="proactive_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower in {"/daily-summary", "/summary", "/companion-summary"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="daily_summary_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue


            if lower.startswith("/gui-task "):
                goal = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="gui_task_requested", data={"goal": goal, "mode": "guided", "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/gui-auto "):
                goal = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="gui_task_requested", data={"goal": goal, "mode": "auto", "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower in {"/gui-status", "/gui-tasks"} or lower.startswith("/gui-status "):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="gui_task_status_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/gui-step") or lower.startswith("/gui-continue"):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="gui_task_step_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/gui-cancel"):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="gui_task_cancel_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue


            if lower in {"/skills", "/skill-status", "/skills-status", "/skill-list"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="skill_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/skill ") or lower.startswith("/find-skill "):
                query = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="skill_search_requested", data={"query": query, "top_k": 6, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/learn-skill "):
                rest = user_text.split(maxsplit=1)[1].strip()
                if "::" in rest:
                    name, steps = [x.strip() for x in rest.split("::", 1)]
                else:
                    name, steps = rest, ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="skill_store_requested", data={"name": name, "steps": steps, "source": "cli_chat", "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower in {"/knowledge", "/kg", "/knowledge-graph"}:
                kernel.event_bus.emit(
                    CognitiveEvent(type="knowledge_graph_status_requested", data={"respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/knowledge ") or lower.startswith("/kg "):
                query = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="knowledge_query_requested", data={"query": query, "top_k": 8, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/web-search "):
                query = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="web_search_requested", data={"query": query, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=45.0)
                continue

            if lower.startswith("/task "):
                goal = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_requested", data={"goal": goal, "autonomy": "guided", "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/task-auto "):
                goal = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_requested", data={"goal": goal, "autonomy": "auto", "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower in {"/tasks", "/task-status"} or lower.startswith("/task-status "):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_status_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/task-report"):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_report_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/task-retry"):
                parts = user_text.split()
                task_id = parts[1].strip() if len(parts) > 1 else ""
                step_id = parts[2].strip() if len(parts) > 2 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_retry_requested", data={"task_id": task_id, "step_id": step_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/task-step") or lower.startswith("/continue-task"):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_step_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/task-resume"):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_resume_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/task-cancel"):
                task_id = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="task_chain_cancel_requested", data={"task_id": task_id, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=30.0)
                continue

            if lower.startswith("/web-learn ") or lower.startswith("/learn-web "):
                topic = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="web_learn_requested", data={"topic": topic, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/web-fetch ") or lower.startswith("/read-url "):
                url = user_text.split(maxsplit=1)[1].strip()
                kernel.event_bus.emit(
                    CognitiveEvent(type="web_fetch_requested", data={"url": url, "respond": True}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=60.0)
                continue

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

            if lower.startswith("/repair"):
                path = user_text.split(maxsplit=1)[1].strip() if len(user_text.split(maxsplit=1)) > 1 else "."
                kernel.event_bus.emit(
                    CognitiveEvent(type="code_repair_requested", data={"path": path, "request_id": f"cli_repair_{int(__import__('time').time() * 1000)}", "request_text": user_text}, source_module="cli_chat"),
                    Priority.COGNITIVE,
                )
                await wait_action_response(timeout=120.0)
                continue

            if lower.startswith("/apply-repair") or lower.startswith("/apply repair"):
                parts = user_text.split(maxsplit=1)
                proposal_id = parts[1].strip() if len(parts) > 1 else ""
                kernel.event_bus.emit(
                    CognitiveEvent(type="code_repair_apply_requested", data={"proposal_id": proposal_id}, source_module="cli_chat"),
                    Priority.REALTIME,
                )
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

            if user_text.lower() in {"/see", "/screen", "/read-screen", "/explain-screen", "/vision", "/gui", "/understand-screen", "/analyze-screen"}:
                request_id = f"cli_screen_{int(__import__('time').time())}"
                is_gui = user_text.lower() in {"/vision", "/gui", "/understand-screen", "/analyze-screen"}
                kernel.event_bus.emit(
                    __import__("core.event_bus", fromlist=["CognitiveEvent"]).CognitiveEvent(
                        type="screen_understand_requested" if is_gui else "screen_capture_requested",
                        data={
                            "request_id": request_id,
                            "reason": "cli_user_requested_gui_understanding" if is_gui else "cli_user_requested_screen_read",
                            "mode": "gui_understanding" if is_gui else "screen_read",
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



def init_portable_layout(target: str | None = None) -> Path:
    """Create a portable data layout and .env defaults.

    If target is omitted, it uses the current project directory. This does not
    copy files; use scripts/install_portable.py to clone the whole app to a drive.
    """
    root = Path(target).expanduser().resolve() if target else _ROOT
    data = root / "data"
    brain = data / "brain"
    workspace = data / "workspace"
    screenshots = data / "screenshots"
    for folder in (brain, workspace, screenshots):
        folder.mkdir(parents=True, exist_ok=True)
    env_path = root / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    updates = {
        "JAV_PORTABLE": "true",
        "JARVIS_DATA_DIR": "data/brain",
        "ACTION_WORKSPACE_PATH": "data/workspace",
        "SCREENSHOT_DIR": "data/screenshots",
        "MEMORY_SQLITE_ENABLED": "true",
        "MEMORY_VECTOR_ENABLED": "true",
        "MEMORY_VECTOR_DIMENSIONS": "256",
        "MEMORY_EPISODIC_RETENTION_DAYS": "3650",
        "MEMORY_EPISODIC_MAX_ITEMS": "100000",
        "MEMORY_SEARCH_TOP_K": "8",
        "MODEL_PROFILE": "offline",
        "MODEL_FAST_PROVIDER": "ollama",
        "MODEL_FAST_NAME": "qwen2.5:7b",
        "MODEL_REASON_PROVIDER": "ollama",
        "MODEL_REASON_NAME": "llama3.1:8b",
        "MODEL_CODE_PROVIDER": "ollama",
        "MODEL_CODE_NAME": "qwen2.5-coder:7b",
        "MODEL_ACTION_PROVIDER": "ollama",
        "MODEL_ACTION_NAME": "qwen2.5:7b",
        "JAV_SERVICE_MODE": "false",
        "JAV_WATCHDOG_ENABLED": "true",
        "RUNTIME_LOG_TO_FILE": "true",
        "RUNTIME_LOG_DIR": "data/brain/logs",
        "RUNTIME_HEARTBEAT_FILE": "data/brain/runtime_heartbeat.json",
        "RUNTIME_PID_FILE": "data/brain/runtime.pid",
        "GUI_AUTOMATION_ENABLED": "true",
        "GUI_AUTOMATION_AUTO_ENABLED": "false",
        "GUI_AUTOMATION_MAX_STEPS": "12",
        "GUI_AUTOMATION_BLOCK_SENSITIVE": "true",
        "SYSTEM_MONITOR_ENABLED": "true",
        "SYSTEM_MONITOR_INTERVAL_SECONDS": "20",
        "SYSTEM_CHECK_OLLAMA": "true",
        "SYSTEM_CHECK_MODELS": "true",
        "PROACTIVE_COMPANION_ENABLED": "true",
        "PROACTIVE_CHAT_NOTIFICATIONS": "true",
        "PROACTIVE_SPEAK_NOTIFICATIONS": "false",
        "PROACTIVE_MIN_IMPORTANCE": "0.55",
        "PROACTIVE_COOLDOWN_SECONDS": "300",
        "PROACTIVE_DAILY_SUMMARY_ENABLED": "true",
        "SKILL_LEARNING_ENABLED": "true",
        "SKILL_AUTO_LEARN_ENABLED": "true",
        "SKILL_MAX_SKILLS": "1000",
        "KNOWLEDGE_GRAPH_MAX_EDGES": "5000",
    }
    existing = {line.split("=", 1)[0].strip() for line in lines if "=" in line and not line.lstrip().startswith("#")}
    out = list(lines)
    for key, value in updates.items():
        if key in existing:
            out = [f"{key}={value}" if line.split("=", 1)[0].strip() == key and "=" in line and not line.lstrip().startswith("#") else line for line in out]
        else:
            out.append(f"{key}={value}")
    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return root

def _init_watchdog() -> int:
    """Register a Windows Startup shortcut that launches the JAV watchdog on login."""
    from scripts.create_windows_startup_shortcut import main as _create
    return _create()


def _remove_watchdog() -> int:
    """Remove the JAV watchdog Windows Startup shortcut if it exists."""
    import os
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        print("APPDATA is not set. This command is Windows-only.")
        return 1
    bat = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "JAV Watchdog.bat"
    if bat.exists():
        bat.unlink()
        print(f"Removed watchdog startup shortcut: {bat}")
    else:
        print("Watchdog startup shortcut not found — nothing to remove.")
    return 0


def _is_first_launch(cfg: "KernelConfig") -> bool:
    """Return True if no data directory exists and the setup sentinel is missing."""
    sentinel = _APP_ROOT / ".jav_setup_complete"
    if sentinel.exists():
        return False
    data_dir = Path(cfg.persistence_dir).expanduser()
    # If data/brain already has content, user has used JAV before — skip wizard
    if data_dir.exists() and any(data_dir.iterdir()):
        return False
    return True


def _run_first_launch_wizard(cfg: "KernelConfig") -> None:
    """Show the first-launch wizard modally before the main UI opens."""
    import tkinter as tk
    from interfaces.desktop.first_launch_wizard import FirstLaunchWizard

    root = tk.Tk()
    root.withdraw()  # hide dummy root; wizard is a Toplevel

    wizard_done = threading.Event()

    def on_complete(collected: dict) -> None:
        wizard_done.set()
        root.quit()

    def on_cancel() -> None:
        logger.info("[Main] First-launch wizard cancelled — launching with current settings.")
        wizard_done.set()
        root.quit()

    FirstLaunchWizard(root, on_complete=on_complete, on_cancel=on_cancel)
    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass


def main() -> None:
    cfg = KernelConfig()

    parser = argparse.ArgumentParser(description="Cognitive Brain Runtime")
    parser.add_argument("--web", action="store_true", help="Start web dashboard")
    parser.add_argument("--voice", action="store_true", help="Start voice mode: microphone STT + Piper/pyttsx3 TTS")
    parser.add_argument("--chat", action="store_true", help="Start terminal dialogue mode")
    parser.add_argument("--desktop", action="store_true", help="Start native desktop interface instead of browser UI")
    parser.add_argument("--service", action="store_true", help="Start headless service mode with heartbeat/logging for watchdog/systemd")
    parser.add_argument("--doctor", action="store_true", help="Run startup diagnostics and dependency checks")
    parser.add_argument("--init-portable", nargs="?", const=".", help="Create portable data folders and .env in this project or target folder")
    parser.add_argument("--init-watchdog", action="store_true", help="Register JAV watchdog Windows Startup shortcut (auto-restart on crash)")
    parser.add_argument("--remove-watchdog", action="store_true", help="Remove JAV watchdog Windows Startup shortcut")
    parser.add_argument("--host", default=cfg.web_host, help="Web UI host")
    parser.add_argument("--port", type=int, default=cfg.web_port, help="Web UI port")
    args = parser.parse_args()

    if args.service:
        cfg.runtime.service_mode = True
    configure_runtime_logging(cfg, service=bool(args.service))

    if args.init_portable:
        target = None if args.init_portable == "." else args.init_portable
        root = init_portable_layout(target)
        print(f"Portable layout initialized at: {root}")
        print(f"Memory: {root / 'data' / 'brain'}")
        print(f"Workspace: {root / 'data' / 'workspace'}")
        print(".env uses relative paths so a portable drive can change drive letter/mount point.")
        return

    if args.init_watchdog:
        sys.exit(_init_watchdog())

    if args.remove_watchdog:
        sys.exit(_remove_watchdog())

    if args.doctor:
        from scripts.doctor import main as doctor_main
        sys.exit(doctor_main())

    selected_modes = sum(1 for enabled in (args.web, args.voice, args.chat, args.desktop, args.service) if enabled)
    # A built desktop app should open the GUI on double-click. Source/dev mode
    # keeps the historical headless default for terminal users.
    if selected_modes == 0 and getattr(sys, "frozen", False):
        args.desktop = True
        selected_modes = 1
    if selected_modes > 1:
        logger.error("--web, --voice, --chat, --desktop and --service are separate modes for now. Start one at a time.")
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
    elif args.desktop:
        if _is_first_launch(cfg):
            _run_first_launch_wizard(cfg)
            # Re-construct cfg so wizard's .env changes take effect
            cfg = KernelConfig()
        from interfaces.desktop.desktop_app import run_desktop_app
        run_desktop_app(cfg)
    elif args.chat:
        kernel = build_kernel(cfg)
        asyncio.run(run_with_chat(kernel))
    elif args.service:
        kernel = build_kernel(cfg)
        asyncio.run(run_headless(kernel, mode_name="service"))
    else:
        kernel = build_kernel(cfg)
        asyncio.run(run_headless(kernel))


if __name__ == "__main__":
    main()
