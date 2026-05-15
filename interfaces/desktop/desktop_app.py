"""V15 native Assistant Shell for JAV / Jarvis Brain Core.

V15 upgrades the old technical desktop window into a daily-use assistant shell:
- dashboard status cards for runtime/system/models/memory/tasks/actions
- dedicated tabs for chat, activity, tasks, approvals, memory/skills, models and events
- optional tray icon and desktop notifications
- voice process launcher / stop button
- safer approval panel and command palette
- still pure Tkinter so it works without heavy UI dependencies
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, TclError
from pathlib import Path
from typing import Any, Dict, Optional

from config import KernelConfig
from core.kernel import Kernel, KernelAPI
from core.event_bus import CognitiveEvent, Priority
from core.safety.permission_manager import PermissionLevel
from main import build_kernel
from interfaces.desktop.settings_window import SettingsWindow
from interfaces.desktop.notifier import DesktopNotifier
from interfaces.desktop.tray import AssistantTray


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#0d1117")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))


class InfoCard(ttk.Frame):
    def __init__(self, master, title: str, value: str = "—", subtitle: str = "") -> None:
        super().__init__(master, style="Card.TFrame", padding=10)
        self.title = ttk.Label(self, text=title, style="Muted.Card.TLabel", font=("Segoe UI", 9))
        self.value = ttk.Label(self, text=value, style="Card.TLabel", font=("Segoe UI", 13, "bold"))
        self.subtitle = ttk.Label(self, text=subtitle, style="Muted.Card.TLabel", font=("Segoe UI", 8), wraplength=210)
        self.title.pack(anchor="w")
        self.value.pack(anchor="w", pady=(2, 0))
        self.subtitle.pack(anchor="w", pady=(2, 0))

    def set(self, value: str, subtitle: str = "") -> None:
        self.value.configure(text=value)
        self.subtitle.configure(text=subtitle)


class DesktopApp:
    def __init__(self, cfg: KernelConfig | None = None) -> None:
        self.cfg = cfg or KernelConfig()
        self.messages: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.recent_events: list[dict] = []
        self.pending_approvals: Dict[str, dict] = {}
        self.voice_process: Optional[subprocess.Popen] = None
        self._last_event_by_type: Dict[str, dict] = {}
        self._last_notification: Dict[str, float] = {}
        self.notifier = DesktopNotifier(enabled=os.environ.get("DESKTOP_NOTIFICATIONS_ENABLED", "true").lower() == "true")
        self.tray: Optional[AssistantTray] = None

        try:
            self.root = tk.Tk()
        except TclError as exc:
            raise RuntimeError(
                "Desktop UI could not start because Tk cannot open a display. "
                "On Windows, run this from a normal desktop session. On Linux, start it inside an X11/Wayland session, "
                "or use: python main.py --chat / --web / --service."
            ) from exc

        self.root.title("JAV — Assistant Shell")
        self.root.geometry(os.environ.get("DESKTOP_WINDOW_GEOMETRY", "1320x820"))
        self.root.minsize(980, 660)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        # Build the cognitive kernel only after the window exists. This makes desktop startup
        # failures visible and prevents a silent/crashing launch when no GUI display is available.
        try:
            self.kernel: Kernel = build_kernel(self.cfg)
            self.api = KernelAPI(self.kernel)
            self._patch_event_tap()
        except Exception as exc:
            try:
                messagebox.showerror("JAV startup error", f"Kernel failed to start:\n{exc}")
            finally:
                self.root.destroy()
            raise

        self._build_ui()
        self._start_optional_tray()
        if os.environ.get("DESKTOP_START_MINIMIZED", "false").lower() == "true":
            self.root.withdraw()
        self.api.start_in_background()
        self._append("system", "JAV Assistant Shell V15 started. Use natural language, voice process, command palette, or Settings Center.")
        self._tick_ui()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.configure(bg="#0d1117")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#0d1117")
        style.configure("Card.TFrame", background="#161b22", relief="flat")
        style.configure("TLabel", background="#0d1117", foreground="#e6edf3")
        style.configure("Card.TLabel", background="#161b22", foreground="#e6edf3")
        style.configure("Muted.Card.TLabel", background="#161b22", foreground="#8b949e")
        style.configure("Muted.TLabel", background="#0d1117", foreground="#8b949e")
        style.configure("TButton", padding=(8, 5))
        style.configure("Accent.TButton", padding=(10, 6))
        style.configure("Danger.TButton", padding=(8, 5))
        style.configure("TNotebook", background="#0d1117", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6))

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_header(outer)
        self._build_status_cards(outer)

        main = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        left = ttk.Frame(main)
        right = ttk.Frame(main, width=440)
        main.add(left, weight=5)
        main.add(right, weight=2)

        self._build_chat(left)
        self._build_right_tabs(right)

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_box, text="JAV Assistant Shell", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(title_box, text="Jarvis-like local AI core — voice, memory, tasks, GUI actions, monitor", style="Muted.TLabel").pack(anchor="w")

        self.status_label = ttk.Label(header, text="starting...", style="Muted.TLabel")
        self.status_label.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="Settings", command=self.open_settings).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="Voice", command=self.toggle_voice_process).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="Notify", command=lambda: self._notify("JAV", "Assistant Shell notifications are working.")).pack(side=tk.RIGHT, padx=(8, 0))

    def _build_status_cards(self, parent: ttk.Frame) -> None:
        grid = ttk.Frame(parent)
        grid.pack(fill=tk.X, pady=(10, 0))
        self.cards: Dict[str, InfoCard] = {}
        for i, key_title in enumerate([
            ("kernel", "Kernel"),
            ("models", "Models"),
            ("system", "System"),
            ("tasks", "Tasks"),
            ("approvals", "Approvals"),
            ("memory", "Memory"),
        ]):
            key, title = key_title
            card = InfoCard(grid, title)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            grid.columnconfigure(i, weight=1)
            self.cards[key] = card

    def _build_chat(self, parent: ttk.Frame) -> None:
        chat_card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        chat_card.pack(fill=tk.BOTH, expand=True)
        row = ttk.Frame(chat_card, style="Card.TFrame")
        row.pack(fill=tk.X)
        ttk.Label(row, text="Conversation", style="Card.TLabel", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(row, text="Clear", command=self._clear_chat).pack(side=tk.RIGHT)

        self.chat = scrolledtext.ScrolledText(
            chat_card, wrap=tk.WORD, state=tk.DISABLED, bg="#010409", fg="#e6edf3",
            insertbackground="#e6edf3", relief=tk.FLAT, font=("Consolas", 11), padx=12, pady=12,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, pady=(8, 0))
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_var, font=("Segoe UI", 11))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_entry.bind("<Return>", lambda _e: self.send_message())
        ttk.Button(input_frame, text="Send", style="Accent.TButton", command=self.send_message).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(input_frame, text="Ask screen", command=lambda: self._send_text("проаналізуй екран і скажи що робити")).pack(side=tk.RIGHT, padx=(8, 0))

    def _build_right_tabs(self, parent: ttk.Frame) -> None:
        tabs = ttk.Notebook(parent)
        tabs.pack(fill=tk.BOTH, expand=True)

        dashboard = ScrollableFrame(tabs)
        commands = ScrollableFrame(tabs)
        tasks = ScrollableFrame(tabs)
        approvals = ttk.Frame(tabs, padding=8)
        memory = ScrollableFrame(tabs)
        models = ScrollableFrame(tabs)
        events = ttk.Frame(tabs, padding=8)

        for frame, label in [
            (dashboard, "Dashboard"), (commands, "Commands"), (tasks, "Tasks"),
            (approvals, "Approvals"), (memory, "Memory/Skills"), (models, "Models"), (events, "Events"),
        ]:
            tabs.add(frame, text=label)

        self._build_dashboard_tab(dashboard)
        self._build_commands_tab(commands)
        self._build_tasks_tab(tasks)
        self._build_approvals_tab(approvals)
        self._build_memory_tab(memory)
        self._build_models_tab(models)
        self._build_events_tab(events)

    def _button(self, parent, text: str, command) -> None:
        ttk.Button(parent.body if isinstance(parent, ScrollableFrame) else parent, text=text, command=command).pack(fill=tk.X, pady=3, padx=4)

    def _label(self, parent, text: str, bold: bool = False) -> None:
        ttk.Label(parent.body if isinstance(parent, ScrollableFrame) else parent, text=text, font=("Segoe UI", 11, "bold") if bold else ("Segoe UI", 10)).pack(anchor="w", pady=(8 if bold else 2, 4), padx=4)

    def _build_dashboard_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Quick actions", True)
        for text, cmd in [
            ("System status", self.system_status), ("Diagnose system", self.system_diagnose),
            ("Model status", self.model_status), ("Memory status", self.memory_status),
            ("Runtime status", self.runtime_status), ("Proactive status", self.proactive_status),
            ("Daily summary", self.daily_summary), ("Sleep / consolidate", self.sleep_cycle),
            ("Understand GUI", self.understand_gui), ("Action status", self.action_status),
        ]:
            self._button(tab, text, cmd)
        self._label(tab, "Voice process", True)
        self.voice_status_label = ttk.Label(tab.body, text="Voice: stopped", style="Muted.TLabel")
        self.voice_status_label.pack(anchor="w", padx=4, pady=(0, 4))
        self._button(tab, "Start / stop voice mode", self.toggle_voice_process)
        self._label(tab, "Safety", True)
        for lvl, text in [(1, "L1 read-only"), (4, "L4 file-write"), (5, "L5 shell")]:
            self._button(tab, text, lambda l=lvl: self.set_safety(l))

    def _build_commands_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Command palette", True)
        examples = [
            "перевір систему", "діагностуй систему", "покажи статус моделей", "покажи стан пам'яті",
            "що ти помітив", "зроби підсумок дня", "запусти сон", "проаналізуй екран і скажи що натиснути",
            "знайди музику на YouTube", "продовжуй GUI задачу", "статус GUI", "розберися з помилками в .",
            "продовжуй задачу", "повний звіт задачі", "виправ помилки в .", "пошукай в інтернеті ",
            "вивчи ", "покажи навички", "знайди навичку ", "покажи граф знань", "згадай ",
            "прочитай файл README.md", "знайди error в .", "покажи файли .",
        ]
        for text in examples:
            self._button(tab, text, lambda t=text: self._prefill(t))

    def _build_tasks_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Task orchestration", True)
        for text, cmd in [
            ("New task: diagnose project", lambda: self._prefill("розберися з помилками в .")),
            ("Task status", self.task_status), ("Continue task", self.task_step),
            ("Full task report", lambda: self._send_text("повний звіт задачі")),
            ("GUI status", self.gui_status), ("Continue GUI", self.gui_step),
            ("New GUI task", lambda: self._prefill("знайди музику на YouTube")),
        ]:
            self._button(tab, text, cmd)
        self._label(tab, "Active task feed", True)
        self.task_feed = tk.Listbox(tab.body, height=12, bg="#010409", fg="#c9d1d9", relief=tk.FLAT)
        self.task_feed.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _build_approvals_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="Pending approvals", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.approval_list = tk.Listbox(tab, height=12, bg="#010409", fg="#c9d1d9", relief=tk.FLAT)
        self.approval_list.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        row = ttk.Frame(tab)
        row.pack(fill=tk.X)
        ttk.Button(row, text="Approve selected", command=self.approve_selected).pack(side=tk.LEFT)
        ttk.Button(row, text="Deny selected", command=self.deny_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Refresh action status", command=self.action_status).pack(side=tk.RIGHT)
        self.approval_detail = scrolledtext.ScrolledText(tab, height=8, wrap=tk.WORD, bg="#010409", fg="#c9d1d9", relief=tk.FLAT)
        self.approval_detail.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self.approval_list.bind("<<ListboxSelect>>", lambda _e: self._show_selected_approval())

    def _build_memory_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Memory and skills", True)
        for text, cmd in [
            ("Memory status", self.memory_status), ("Recall...", lambda: self._prefill("згадай ")),
            ("Skill library", lambda: self._send_text("покажи навички")),
            ("Find skill...", lambda: self._prefill("знайди навичку ")),
            ("Knowledge graph", lambda: self._send_text("покажи граф знань")),
            ("Learn skill...", lambda: self._prefill("запам'ятай навичку назва :: крок 1; крок 2; крок 3")),
        ]:
            self._button(tab, text, cmd)
        self._label(tab, "Memory browser placeholder", True)
        ttk.Label(tab.body, text="V15 keeps this panel ready for a future searchable memory table. Use /recall now.", style="Muted.TLabel", wraplength=360).pack(anchor="w", padx=4, pady=4)

    def _build_models_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Model router", True)
        self._button(tab, "Refresh model status", self.model_status)
        self._button(tab, "Open Settings / Model Profiles", self.open_settings)
        self.model_text = scrolledtext.ScrolledText(tab.body, height=18, wrap=tk.WORD, bg="#010409", fg="#c9d1d9", relief=tk.FLAT)
        self.model_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _build_events_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="Recent events", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.event_list = tk.Listbox(tab, height=20, bg="#010409", fg="#8b949e", relief=tk.FLAT)
        self.event_list.pack(fill=tk.BOTH, expand=True)
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(row, text="Clear events", command=lambda: self.event_list.delete(0, tk.END)).pack(side=tk.LEFT)
        ttk.Button(row, text="Runtime status", command=self.runtime_status).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _prefill(self, text: str) -> None:
        self.input_var.set(text)
        self.input_entry.focus_set()
        self.input_entry.icursor(tk.END)

    def _send_text(self, text: str) -> None:
        self.input_var.set(text)
        self.send_message()

    def _clear_chat(self) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _append(self, role: str, text: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        prefix = {"user": "You", "assistant": "Jarvis", "system": "System", "event": "Event"}.get(role, role)
        tag = prefix
        self.chat.insert(tk.END, f"{prefix}: {text}\n\n")
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _notify(self, title: str, message: str) -> None:
        key = f"{title}:{message[:80]}"
        now = time.time()
        cooldown = float(os.environ.get("DESKTOP_NOTIFICATION_COOLDOWN_SECONDS", "20"))
        if now - self._last_notification.get(key, 0) < cooldown:
            return
        self._last_notification[key] = now
        self.notifier.notify(title, message)

    def _start_optional_tray(self) -> None:
        if os.environ.get("DESKTOP_TRAY_ENABLED", "true").lower() != "true":
            return
        self.tray = AssistantTray(self._show_window, self.close, self.runtime_status)
        status = self.tray.start()
        if status.available:
            self._append("system", "Tray icon started.")
        else:
            self._append("system", f"Tray unavailable: {status.message}. Install optional deps: pip install pystray pillow")

    def _show_window(self) -> None:
        def _inner():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self.root.after(0, _inner)

    # ------------------------------------------------------------------
    # Periodic UI update and event tap
    # ------------------------------------------------------------------
    def _tick_ui(self) -> None:
        try:
            while True:
                role, text = self.messages.get_nowait()
                self._append(role, text)
        except queue.Empty:
            pass

        try:
            while True:
                event = self.events.get_nowait()
                self._consume_event_for_ui(event)
        except queue.Empty:
            pass

        self._update_cards()
        self._update_voice_status()
        self.root.after(300, self._tick_ui)

    def _consume_event_for_ui(self, event: dict) -> None:
        self.recent_events.insert(0, event)
        self.recent_events = self.recent_events[:250]
        label = f"{event.get('type')} ← {event.get('source_module')}"
        self.event_list.insert(0, label)
        if self.event_list.size() > 180:
            self.event_list.delete(180, tk.END)

        etype = str(event.get("type") or "")
        self._last_event_by_type[etype] = event
        data = event.get("data") or {}
        if etype in {"task_chain_created", "task_chain_step_completed", "task_chain_completed", "task_chain_failed", "task_chain_report_ready"}:
            task_label = f"{etype}: {data.get('task_id') or data.get('goal') or data.get('summary') or ''}"[:160]
            self.task_feed.insert(0, task_label)
            if self.task_feed.size() > 80:
                self.task_feed.delete(80, tk.END)
        if etype in {"action_pending_confirmation", "action_confirmation_required"}:
            pending_id = str(data.get("pending_id") or data.get("id") or data.get("request_id") or "").strip()
            if pending_id:
                self.pending_approvals[pending_id] = data
                self._refresh_approval_list()
                self._notify("JAV approval needed", f"Pending action {pending_id} needs your approval.")
        if etype in {"proactive_notification", "system_alert"}:
            text = str(data.get("text") or data.get("message") or data.get("summary") or "").strip()
            if text:
                self._notify("JAV noticed something", text)

    def _patch_event_tap(self) -> None:
        original_emit = self.kernel.event_bus.emit

        def tapped_emit(event: CognitiveEvent, priority: Priority) -> None:
            original_emit(event, priority)
            try:
                self.events.put_nowait({
                    "type": event.type,
                    "source_module": event.source_module,
                    "data": event.data,
                    "timestamp": event.timestamp,
                })
                text = ""
                if event.type == "response_generated":
                    text = str(event.data.get("text", "") or "").strip()
                elif event.type == "screen_parsed" and event.data.get("respond"):
                    text = str(event.data.get("summary", "") or "").strip()
                elif event.type == "sleep_cycle_completed":
                    text = "Sleep cycle completed. " + str(event.data.get("summary", "") or "").strip()
                elif event.type == "action_result" and event.data.get("respond_fallback"):
                    text = str(event.data)
                elif event.type == "proactive_notification":
                    text = str(event.data.get("text", "") or "").strip()
                elif event.type == "proactive_daily_summary":
                    text = str(event.data.get("text", "") or "").strip()
                elif event.type in {"system_status_report", "system_diagnosis_report", "runtime_status_report", "memory_status_report"}:
                    text = str(event.data.get("text") or event.data.get("summary") or "").strip()
                if text:
                    self.messages.put_nowait(("assistant", text))
            except Exception:
                pass

        self.kernel.event_bus.emit = tapped_emit  # type: ignore[method-assign]

    def _update_cards(self) -> None:
        state = self.api.get_state()
        running = state.get("running")
        safety = state.get("core_state", {}).get("safety_level", "?")
        mods = len(self.kernel.modules)
        self.status_label.configure(text=f"running={running} | modules={mods} | safety=L{safety}")
        self.cards["kernel"].set(f"{'ON' if running else 'OFF'} / {mods} mods", f"Safety L{safety}")

        router = getattr(self.kernel, "llm_router", None)
        if router is not None and hasattr(router, "status"):
            try:
                status = router.status(refresh=False)
                roles = status.get("roles") or {}
                available = sum(1 for r in roles.values() if r.get("available"))
                self.cards["models"].set(f"{available}/{len(roles)} roles", str(status.get("profile") or "profile"))
            except Exception:
                self.cards["models"].set("unknown", "router error")

        self.cards["approvals"].set(str(len(self.pending_approvals)), "pending confirmations")
        mem_dir = getattr(self.cfg.memory, "data_dir", "")
        self.cards["memory"].set("SQLite/vector", str(mem_dir)[:42])
        last_sys = self._last_event_by_type.get("system_status_report") or self._last_event_by_type.get("system_snapshot")
        if last_sys:
            data = last_sys.get("data") or {}
            self.cards["system"].set(str(data.get("status") or data.get("summary") or "OK")[:24], str(data.get("text") or "")[:42])
        else:
            self.cards["system"].set("monitoring", "use Diagnose system")
        task_events = [e for e in self.recent_events[:60] if str(e.get("type", "")).startswith("task_chain")]
        self.cards["tasks"].set(str(len(task_events)), "recent task events")

    def _update_voice_status(self) -> None:
        if self.voice_process and self.voice_process.poll() is None:
            text = f"Voice: running pid={self.voice_process.pid}"
        else:
            text = "Voice: stopped"
        try:
            self.voice_status_label.configure(text=text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event and command routing
    # ------------------------------------------------------------------
    def emit(self, type_: str, data: Dict[str, Any], priority: Priority = Priority.COGNITIVE) -> None:
        self.api.emit_event(type_, data, priority)

    def send_message(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        self._append("user", text)
        self._route_text(text)

    def _route_text(self, text: str) -> None:
        lower = text.lower()
        if lower in {"/see", "/screen", "/read-screen", "/explain-screen"}:
            self.read_screen(); return
        if lower in {"/vision", "/gui", "/understand-screen", "/analyze-screen"}:
            self.understand_gui(); return
        if lower in {"/sleep", "/dream", "/consolidate", "/memory-consolidate"}:
            self.sleep_cycle(); return
        if lower in {"/actions", "/workspace", "/action-status"}:
            self.action_status(); return
        if lower in {"/memory", "/memory-status", "/storage"}:
            self.memory_status(); return
        if lower in {"/models", "/model-status", "/model-health", "/model-profile"}:
            self.model_status(); return
        if lower in {"/runtime", "/runtime-status", "/health", "/service-status"}:
            self.runtime_status(); return
        if lower in {"/self-test", "/runtime-self-test", "/health-check"}:
            self.runtime_self_test(); return
        if lower in {"/system", "/monitor", "/system-status"}:
            self.system_status(); return
        if lower in {"/diagnose-system"}:
            self.system_diagnose(); return
        if lower in {"/proactive", "/proactive-status", "/companion"}:
            self.proactive_status(); return
        if lower in {"/daily-summary", "/summary", "/companion-summary"}:
            self.daily_summary(); return
        if lower in {"/tasks", "/task-status"} or lower.startswith("/task-status "):
            self.emit("task_chain_status_requested", {"task_id": text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else "", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/task-report"):
            self.emit("task_chain_report_requested", {"task_id": text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else "", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/task-step") or lower.startswith("/continue-task"):
            self.emit("task_chain_step_requested", {"task_id": text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else "", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/task "):
            self.emit("task_chain_requested", {"goal": text.split(maxsplit=1)[1].strip(), "autonomy": "guided", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/task-auto "):
            self.emit("task_chain_requested", {"goal": text.split(maxsplit=1)[1].strip(), "autonomy": "auto", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/gui-task "):
            self.emit("gui_task_requested", {"goal": text.split(maxsplit=1)[1].strip(), "mode": "guided", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/gui-auto "):
            self.emit("gui_task_requested", {"goal": text.split(maxsplit=1)[1].strip(), "mode": "auto", "respond": True}, Priority.COGNITIVE); return
        if lower in {"/gui-status", "/gui-tasks"} or lower.startswith("/gui-status "):
            self.emit("gui_task_status_requested", {"task_id": text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else "", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/gui-step") or lower.startswith("/gui-continue"):
            self.emit("gui_task_step_requested", {"task_id": text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else "", "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/web-search "):
            self.emit("web_search_requested", {"query": text.split(maxsplit=1)[1], "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/web-learn "):
            self.emit("web_learn_requested", {"topic": text.split(maxsplit=1)[1], "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/approve"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                self._approve_id(parts[1].strip())
            else:
                self._append("system", "Usage: /approve <pending_id>")
            return
        if lower.startswith("/deny"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                self._deny_id(parts[1].strip())
            else:
                self._append("system", "Usage: /deny <pending_id>")
            return
        self.emit("user_utterance", {"text": text, "input_mode": "desktop"}, Priority.REALTIME)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def read_screen(self) -> None:
        self.emit("screen_capture_requested", {"request_id": f"desktop_screen_{int(time.time())}", "reason": "desktop_button", "respond": True}, Priority.REALTIME)

    def understand_gui(self) -> None:
        self.emit("screen_understand_requested", {"request_id": f"desktop_gui_{int(time.time())}", "reason": "desktop_button", "mode": "gui_understanding", "respond": True}, Priority.REALTIME)

    def sleep_cycle(self) -> None:
        self.emit("sleep_cycle_requested", {"reason": "desktop_button", "force": True, "respond": True}, Priority.COGNITIVE)

    def action_status(self) -> None:
        self.emit("action_status_requested", {"respond": True}, Priority.COGNITIVE)

    def memory_status(self) -> None:
        self.emit("memory_status_requested", {"respond": True}, Priority.COGNITIVE)

    def task_status(self) -> None:
        self.emit("task_chain_status_requested", {"respond": True}, Priority.COGNITIVE)

    def task_step(self) -> None:
        self.emit("task_chain_step_requested", {"respond": True}, Priority.COGNITIVE)

    def gui_status(self) -> None:
        self.emit("gui_task_status_requested", {"respond": True}, Priority.COGNITIVE)

    def gui_step(self) -> None:
        self.emit("gui_task_step_requested", {"respond": True}, Priority.COGNITIVE)

    def model_status(self) -> None:
        router = getattr(self.kernel, "llm_router", None)
        if router is None or not hasattr(router, "status"):
            self._append("system", "Model router is not available.")
            return
        status = router.status(refresh=True)
        lines = [f"Model router profile: {status.get('profile')}"]
        for role in ["fast", "reason", "code", "critic", "vision", "embedding", "action"]:
            info = (status.get("roles") or {}).get(role) or {}
            lines.append(f"- {role}: {info.get('provider', 'not configured')} / {info.get('model', '')} available={info.get('available', False)}")
        lines.append(f"available providers: {', '.join(status.get('available') or [])}")
        text = "\n".join(lines)
        self._append("system", text)
        try:
            self.model_text.delete("1.0", tk.END)
            self.model_text.insert(tk.END, text)
        except Exception:
            pass

    def runtime_status(self) -> None:
        self.emit("runtime_status_requested", {"respond": True}, Priority.COGNITIVE)

    def runtime_self_test(self) -> None:
        self.emit("runtime_self_test_requested", {"respond": True}, Priority.COGNITIVE)

    def system_status(self) -> None:
        self.emit("system_status_requested", {"respond": True}, Priority.COGNITIVE)

    def system_diagnose(self) -> None:
        self.emit("system_diagnose_requested", {"respond": True}, Priority.COGNITIVE)

    def proactive_status(self) -> None:
        self.emit("proactive_status_requested", {"respond": True}, Priority.COGNITIVE)

    def daily_summary(self) -> None:
        self.emit("daily_summary_requested", {"respond": True}, Priority.COGNITIVE)

    def approve_selected(self) -> None:
        pid = self._selected_approval_id()
        if pid:
            self._approve_id(pid)

    def deny_selected(self) -> None:
        pid = self._selected_approval_id()
        if pid:
            self._deny_id(pid)

    def _approve_id(self, pending_id: str) -> None:
        self.emit("v7_user_approval", {"pending_id": pending_id}, Priority.REALTIME)
        self.pending_approvals.pop(pending_id, None)
        self._refresh_approval_list()
        self._append("system", f"Approved pending action {pending_id}.")

    def _deny_id(self, pending_id: str) -> None:
        self.emit("v7_user_deny", {"pending_id": pending_id}, Priority.REALTIME)
        self.pending_approvals.pop(pending_id, None)
        self._refresh_approval_list()
        self._append("system", f"Denied pending action {pending_id}.")

    def _selected_approval_id(self) -> str:
        sel = self.approval_list.curselection()
        if not sel:
            messagebox.showinfo("Approvals", "Select a pending approval first.")
            return ""
        item = self.approval_list.get(sel[0])
        return item.split(" ", 1)[0].strip()

    def _refresh_approval_list(self) -> None:
        self.approval_list.delete(0, tk.END)
        for pid, data in self.pending_approvals.items():
            action = data.get("action_type") or data.get("type") or data.get("action") or "action"
            self.approval_list.insert(tk.END, f"{pid}  {action}")
        self._show_selected_approval()

    def _show_selected_approval(self) -> None:
        self.approval_detail.configure(state=tk.NORMAL)
        self.approval_detail.delete("1.0", tk.END)
        pid = ""
        try:
            sel = self.approval_list.curselection()
            if sel:
                pid = self.approval_list.get(sel[0]).split(" ", 1)[0].strip()
        except Exception:
            pass
        if pid and pid in self.pending_approvals:
            self.approval_detail.insert(tk.END, repr(self.pending_approvals[pid]))
        else:
            self.approval_detail.insert(tk.END, "No approval selected.")
        self.approval_detail.configure(state=tk.DISABLED)

    def toggle_voice_process(self) -> None:
        if self.voice_process and self.voice_process.poll() is None:
            try:
                self.voice_process.terminate()
                self._append("system", "Voice process stopped.")
            except Exception as exc:
                self._append("system", f"Could not stop voice process: {exc}")
            return
        try:
            root = Path(__file__).resolve().parents[2]
            self.voice_process = subprocess.Popen([sys.executable, str(root / "main.py"), "--voice"], cwd=str(root))
            self._append("system", f"Voice process started pid={self.voice_process.pid}. It runs as a separate process.")
        except Exception as exc:
            self._append("system", f"Could not start voice process: {exc}")

    def open_settings(self) -> None:
        SettingsWindow(self.root, on_saved=self._settings_saved)

    def _settings_saved(self, updates: Dict[str, str]) -> None:
        try:
            actions = getattr(self.kernel.config, "actions", None)
            if actions is not None:
                if "ACTION_WORKSPACE_PATH" in updates:
                    actions.workspace_path = updates["ACTION_WORKSPACE_PATH"]
                if "ACTION_ALLOW_SHELL" in updates:
                    actions.allow_shell = updates["ACTION_ALLOW_SHELL"].lower() == "true"
                if "ACTIONS_V7_ENABLED" in updates:
                    actions.enabled = updates["ACTIONS_V7_ENABLED"].lower() == "true"
            self._append("system", "Settings saved. Restart JAV for provider/path/voice/OCR/UI settings to fully reload. Some action settings were applied live.")
        except Exception as exc:
            self._append("system", f"Settings saved, but live apply failed: {exc}")

    def set_safety(self, level: int) -> None:
        try:
            self.kernel.permission_manager.set_level(PermissionLevel(level))
            self.kernel.core_state.safety_level = level
            self._append("system", f"Safety level set to L{level}.")
        except Exception as exc:
            messagebox.showerror("Safety error", str(exc))

    def close(self) -> None:
        try:
            if self.voice_process and self.voice_process.poll() is None:
                try:
                    self.voice_process.terminate()
                except Exception:
                    pass
            if self.tray:
                self.tray.stop()
            self._append("system", "Shutting down...")
            self.api.shutdown()
        finally:
            try:
                self.root.destroy()
            except Exception:
                pass

    def run(self) -> None:
        self.input_entry.focus_set()
        self.root.mainloop()


def _write_desktop_crash_log(cfg: KernelConfig | None, exc: BaseException) -> Path:
    try:
        base = Path(getattr(cfg, "persistence_dir", "~/.jarvis_brain")).expanduser() if cfg else Path.home() / ".jarvis_brain"
        log_dir = base / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "desktop_crash.log"
        import traceback
        path.write_text(traceback.format_exc(), encoding="utf-8")
        return path
    except Exception:
        return Path("desktop_crash.log")


def run_desktop_app(cfg: KernelConfig | None = None) -> None:
    try:
        app = DesktopApp(cfg)
        app.run()
    except Exception as exc:
        crash_log = _write_desktop_crash_log(cfg, exc)
        print(f"JAV desktop failed to start: {exc}", file=sys.stderr)
        print(f"Crash log: {crash_log}", file=sys.stderr)
        raise
