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
import sqlite3
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, TclError
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


# Modern assistant-shell palette.  Still pure Tkinter/ttk, but the UI now behaves
# like a product dashboard instead of a technical debug window.
UI = {
    "bg": "#0b1020",
    "panel": "#111827",
    "panel_2": "#172033",
    "input": "#070b14",
    "border": "#263247",
    "text": "#f8fafc",
    "muted": "#94a3b8",
    "blue": "#38bdf8",
    "green": "#34d399",
    "orange": "#f59e0b",
    "red": "#fb7185",
    "purple": "#a78bfa",
}


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=UI["bg"])
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
        self._last_value: str = value
        self._last_subtitle: str = subtitle

    def set(self, value: str, subtitle: str = "") -> None:
        if value == self._last_value and subtitle == self._last_subtitle:
            return
        self._last_value = value
        self._last_subtitle = subtitle
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
        self._cached_model_status: Optional[dict] = None
        self._model_status_ts: float = 0.0
        self._model_status_refreshing: bool = False
        self._task_event_count: int = 0
        self.notifier = DesktopNotifier(enabled=os.environ.get("DESKTOP_NOTIFICATIONS_ENABLED", "true").lower() == "true")
        self.tray: Optional[AssistantTray] = None
        self.kernel: Optional[Kernel] = None
        self.api: Optional[KernelAPI] = None
        self.kernel_ready = False
        self._kernel_boot_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()

        try:
            self.root = tk.Tk()
        except TclError as exc:
            raise RuntimeError(
                "Desktop UI could not start because Tk cannot open a display. "
                "On Windows, run this from a normal desktop session. On Linux, start it inside an X11/Wayland session, "
                "or use: python main.py --chat / --web / --service."
            ) from exc

        self.root.title("JAV — Personal AI Assistant")
        self.root.geometry(os.environ.get("DESKTOP_WINDOW_GEOMETRY", "1320x820"))
        self.root.minsize(1080, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        # Build the window first, then boot the cognitive kernel in a background thread.
        # This prevents the common "black console with two startup lines" feeling when
        # module loading, optional network checks, or model health checks take a while.
        self._build_ui()
        self._start_optional_tray()
        if os.environ.get("DESKTOP_START_MINIMIZED", "false").lower() == "true":
            self.root.withdraw()
        self._append("system", "JAV Assistant Shell is opening. Booting cognitive kernel in the background…")
        self.status_label.configure(text="booting kernel…")
        self._start_kernel_boot()
        self._tick_ui()


    # ------------------------------------------------------------------
    # Kernel boot
    # ------------------------------------------------------------------
    def _start_kernel_boot(self) -> None:
        def worker() -> None:
            try:
                kernel = build_kernel(self.cfg)
                self._kernel_boot_queue.put(("ok", kernel))
            except Exception as exc:
                self._kernel_boot_queue.put(("error", exc))
        threading.Thread(target=worker, daemon=True, name="desktop-kernel-boot").start()
        self.root.after(100, self._poll_kernel_boot)

    def _poll_kernel_boot(self) -> None:
        try:
            status, payload = self._kernel_boot_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_kernel_boot)
            return
        if status == "error":
            exc = payload
            self.status_label.configure(text="kernel failed")
            self._append("system", f"Kernel failed to start: {exc}")
            try:
                messagebox.showerror("JAV startup error", f"Kernel failed to start:\n{exc}")
            except Exception:
                pass
            return
        self.kernel = payload  # type: ignore[assignment]
        self.api = KernelAPI(self.kernel)
        self._patch_event_tap()
        self.api.start_in_background()
        self.kernel_ready = True
        self.status_label.configure(text="running")
        self._append("system", "JAV Assistant Shell V15.2 started. Use natural language, voice process, command palette, or Settings Center.")
        self.root.after(1000, self._refresh_model_status_bg)

    def _ensure_ready(self) -> bool:
        if self.kernel_ready and self.kernel is not None and self.api is not None:
            return True
        self._append("system", "Kernel is still starting. Try again in a moment, or run python main.py --doctor if it never becomes ready.")
        return False

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.configure(bg=UI["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=UI["bg"])
        style.configure("Card.TFrame", background=UI["panel"], relief="flat")
        style.configure("SoftCard.TFrame", background=UI["panel_2"], relief="flat")
        style.configure("TLabel", background=UI["bg"], foreground=UI["text"])
        style.configure("Card.TLabel", background=UI["panel"], foreground=UI["text"])
        style.configure("SoftCard.TLabel", background=UI["panel_2"], foreground=UI["text"])
        style.configure("Muted.Card.TLabel", background=UI["panel"], foreground=UI["muted"])
        style.configure("Muted.SoftCard.TLabel", background=UI["panel_2"], foreground=UI["muted"])
        style.configure("Muted.TLabel", background=UI["bg"], foreground=UI["muted"])
        style.configure("TButton", padding=(10, 7), background=UI["panel_2"], foreground=UI["text"])
        style.map("TButton", background=[("active", UI["border"]), ("pressed", UI["border"])])
        style.configure("Accent.TButton", padding=(12, 8), background=UI["blue"], foreground="#020617")
        style.map("Accent.TButton", background=[("active", "#7dd3fc"), ("pressed", "#0ea5e9")])
        style.configure("Danger.TButton", padding=(10, 7), background=UI["red"], foreground="#020617")
        style.configure("TNotebook", background=UI["bg"], borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure("TNotebook.Tab", padding=(14, 8), background=UI["panel"], foreground=UI["muted"])
        style.map(
            "TNotebook.Tab",
            background=[("selected", UI["panel_2"]), ("active", UI["border"])],
            foreground=[("selected", UI["text"]), ("active", UI["text"])],
        )
        style.configure("Horizontal.TProgressbar", background=UI["blue"], troughcolor=UI["panel"], borderwidth=0)

        outer = ttk.Frame(self.root, padding=14)
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
        header = ttk.Frame(parent, style="SoftCard.TFrame", padding=(14, 12))
        header.pack(fill=tk.X)
        title_box = ttk.Frame(header, style="SoftCard.TFrame")
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_box, text="JAV", style="SoftCard.TLabel", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        ttk.Label(
            title_box,
            text="Personal Jarvis-like assistant — voice • memory • vision • actions • monitor",
            style="Muted.SoftCard.TLabel",
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        actions = ttk.Frame(header, style="SoftCard.TFrame")
        actions.pack(side=tk.RIGHT)
        self.status_label = ttk.Label(actions, text="starting…", style="Muted.SoftCard.TLabel")
        self.status_label.grid(row=0, column=0, columnspan=4, sticky="e", pady=(0, 6))
        ttk.Button(actions, text="⚙ Settings", command=self.open_settings).grid(row=1, column=0, padx=3)
        ttk.Button(actions, text="🧠 Models", command=self._open_model_wizard).grid(row=1, column=1, padx=3)
        ttk.Button(actions, text="🎙 Voice", command=self.toggle_voice_process).grid(row=1, column=2, padx=3)
        ttk.Button(actions, text="🔔 Test", command=lambda: self._notify("JAV", "Assistant Shell notifications are working.")).grid(row=1, column=3, padx=3)

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
        ttk.Label(row, text="Conversation", style="Card.TLabel", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        ttk.Label(row, text="natural language commands work here", style="Muted.Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(row, text="Clear", command=self._clear_chat).pack(side=tk.RIGHT)

        self.chat = scrolledtext.ScrolledText(
            chat_card, wrap=tk.WORD, state=tk.DISABLED, bg=UI["input"], fg=UI["text"],
            insertbackground=UI["text"], relief=tk.FLAT, font=("Segoe UI", 10), padx=14, pady=14,
        )
        self.chat.tag_configure("user", foreground=UI["blue"], font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("assistant", foreground=UI["green"], font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("system", foreground=UI["orange"], font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("event", foreground=UI["purple"], font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("body", foreground=UI["text"], font=("Segoe UI", 10))
        self.chat.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        input_frame = ttk.Frame(parent, style="SoftCard.TFrame", padding=(8, 8))
        input_frame.pack(fill=tk.X, pady=(8, 0))
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_var, font=("Segoe UI", 11))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_entry.bind("<Return>", lambda _e: self.send_message())
        ttk.Button(input_frame, text="Send", style="Accent.TButton", command=self.send_message).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(input_frame, text="Screen", command=lambda: self._send_text("проаналізуй екран і скажи що робити")).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(input_frame, text="Task", command=lambda: self._prefill("розберися з цією задачею: ")).pack(side=tk.RIGHT, padx=(8, 0))

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
        doctor = ttk.Frame(tabs, padding=8)
        voice_setup = ScrollableFrame(tabs)
        logs = ttk.Frame(tabs, padding=8)

        for frame, label in [
            (dashboard, "🏠 Home"), (commands, "⌘ Commands"), (tasks, "✅ Tasks"),
            (approvals, "🛡 Approvals"), (memory, "🧠 Memory"), (models, "⚙ Models"),
            (events, "📡 Events"), (doctor, "🩺 Doctor"), (voice_setup, "🎙 Voice"), (logs, "📜 Logs"),
        ]:
            tabs.add(frame, text=label)

        self._build_dashboard_tab(dashboard)
        self._build_commands_tab(commands)
        self._build_tasks_tab(tasks)
        self._build_approvals_tab(approvals)
        self._build_memory_tab(memory)
        self._build_models_tab(models)
        self._build_events_tab(events)
        self._build_doctor_tab(doctor)
        self._build_voice_setup_tab(voice_setup)
        self._build_logs_tab(logs)

    def _button(self, parent, text: str, command) -> None:
        ttk.Button(parent.body if isinstance(parent, ScrollableFrame) else parent, text=text, command=command).pack(fill=tk.X, pady=4, padx=4)

    def _chip(self, parent, text: str, command) -> None:
        ttk.Button(parent.body if isinstance(parent, ScrollableFrame) else parent, text=text, command=command).pack(fill=tk.X, pady=3, padx=4)

    def _section(self, parent, title: str, subtitle: str = "") -> ttk.Frame:
        body = parent.body if isinstance(parent, ScrollableFrame) else parent
        box = ttk.Frame(body, style="Card.TFrame", padding=10)
        box.pack(fill=tk.X, pady=(0, 10), padx=2)
        ttk.Label(box, text=title, style="Card.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        if subtitle:
            ttk.Label(box, text=subtitle, style="Muted.Card.TLabel", wraplength=360).pack(anchor="w", pady=(2, 8))
        return box

    def _label(self, parent, text: str, bold: bool = False) -> None:
        ttk.Label(parent.body if isinstance(parent, ScrollableFrame) else parent, text=text, font=("Segoe UI", 11, "bold") if bold else ("Segoe UI", 10)).pack(anchor="w", pady=(8 if bold else 2, 4), padx=4)

    def _build_dashboard_tab(self, tab: ScrollableFrame) -> None:
        top = self._section(tab, "Start here", "Ask naturally, or use the safest one-click actions below.")
        for text, cmd in [
            ("🩺 Diagnose system", self.system_diagnose),
            ("🧠 Check models", self.model_status),
            ("💾 Memory status", self.memory_status),
            ("👁 Understand screen", self.understand_gui),
            ("✅ Continue task", self.task_step),
        ]:
            ttk.Button(top, text=text, command=cmd, style="Accent.TButton" if "Diagnose" in text else "TButton").pack(fill=tk.X, pady=3)

        workspace = self._section(tab, "Workspace", "Safe file actions only operate inside this folder. Import/change it before asking JAV to read or repair a project.")
        self.workspace_label = ttk.Label(workspace, text=self._workspace_path_text(), style="Muted.Card.TLabel", wraplength=360)
        self.workspace_label.pack(anchor="w", pady=(0, 6))
        ttk.Button(workspace, text="📂 Open workspace", command=self.open_workspace).pack(fill=tk.X, pady=3)
        ttk.Button(workspace, text="🔁 Change workspace", command=self.change_workspace).pack(fill=tk.X, pady=3)
        ttk.Button(workspace, text="📥 Import project into workspace", command=self.import_project_to_workspace).pack(fill=tk.X, pady=3)

        voice = self._section(tab, "Voice companion", "Start the separate voice loop when microphone/STT/TTS are configured.")
        self.voice_status_label = ttk.Label(voice, text="Voice: stopped", style="Muted.Card.TLabel")
        self.voice_status_label.pack(anchor="w", pady=(0, 6))
        ttk.Button(voice, text="🎙 Start / stop voice mode", command=self.toggle_voice_process).pack(fill=tk.X, pady=3)
        ttk.Button(voice, text="🧪 Voice setup report", command=self.voice_setup_report).pack(fill=tk.X, pady=3)
        ttk.Button(voice, text="🔊 Test pyttsx3 fallback", command=self.voice_test_pyttsx3).pack(fill=tk.X, pady=3)

        safety = self._section(tab, "Safety level", "Use the lowest level that can complete the task.")
        for lvl, text in [(1, "L1 Read-only"), (4, "L4 File write in workspace"), (5, "L5 Allowlisted shell")]:
            ttk.Button(safety, text=text, command=lambda l=lvl: self.set_safety(l)).pack(fill=tk.X, pady=3)

        monitor = self._section(tab, "Companion status", "System monitor, runtime, proactive assistant and daily summary.")
        for text, cmd in [
            ("🖥 System status", self.system_status), ("🧬 Runtime status", self.runtime_status),
            ("🔔 Proactive status", self.proactive_status), ("📅 Daily summary", self.daily_summary),
            ("🌙 Sleep / consolidate memory", self.sleep_cycle), ("🛠 Action status", self.action_status),
        ]:
            ttk.Button(monitor, text=text, command=cmd).pack(fill=tk.X, pady=3)

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
        self.task_feed = tk.Listbox(tab.body, height=12, bg=UI["input"], fg=UI["text"], relief=tk.FLAT)
        self.task_feed.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _build_approvals_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="Pending approvals", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.approval_list = tk.Listbox(tab, height=12, bg=UI["input"], fg=UI["text"], relief=tk.FLAT)
        self.approval_list.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        row = ttk.Frame(tab)
        row.pack(fill=tk.X)
        ttk.Button(row, text="Approve selected", command=self.approve_selected).pack(side=tk.LEFT)
        ttk.Button(row, text="Deny selected", command=self.deny_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Refresh action status", command=self.action_status).pack(side=tk.RIGHT)
        self.approval_detail = scrolledtext.ScrolledText(tab, height=8, wrap=tk.WORD, bg=UI["input"], fg=UI["text"], relief=tk.FLAT)
        self.approval_detail.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self.approval_list.bind("<<ListboxSelect>>", lambda _e: self._show_selected_approval())

    def _build_memory_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Memory and skills", True)
        quick = self._section(tab, "Quick memory actions", "Search long-term memory, check storage and manage skills.")
        ttk.Button(quick, text="Memory status", command=self.memory_status).pack(fill=tk.X, pady=3)
        ttk.Button(quick, text="Skill library", command=lambda: self._send_text("покажи навички")).pack(fill=tk.X, pady=3)
        ttk.Button(quick, text="Knowledge graph", command=lambda: self._send_text("покажи граф знань")).pack(fill=tk.X, pady=3)

        browser = self._section(tab, "Memory browser", "Search SQLite/vector memory without using slash commands.")
        row = ttk.Frame(browser, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(4, 6))
        self.memory_search_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.memory_search_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self.search_memory_browser())
        ttk.Button(row, text="Search", command=self.search_memory_browser).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(row, text="Refresh recent", command=self.refresh_recent_memory).pack(side=tk.RIGHT, padx=(6, 0))
        self.memory_list = tk.Listbox(browser, height=12, bg=UI["input"], fg=UI["text"], relief=tk.FLAT)
        self.memory_list.pack(fill=tk.BOTH, expand=True, pady=(4, 6))
        self.memory_detail = scrolledtext.ScrolledText(browser, height=8, wrap=tk.WORD, bg=UI["input"], fg=UI["text"], relief=tk.FLAT)
        self.memory_detail.pack(fill=tk.BOTH, expand=True)
        self.memory_list.bind("<<ListboxSelect>>", lambda _e: self.show_selected_memory())
        self._memory_rows = []

    def _build_models_tab(self, tab: ScrollableFrame) -> None:
        from interfaces.desktop.model_status_panel import ModelStatusPanel
        self._model_panel = ModelStatusPanel(tab.body, kernel=None, padding=4)
        self._model_panel.pack(fill=tk.BOTH, expand=True)

    def _open_model_wizard(self) -> None:
        from interfaces.desktop.model_setup_wizard import ModelSetupWizard

        def on_complete(cfg: dict) -> None:
            self._settings_saved(cfg)
            if hasattr(self, "_model_panel"):
                self._model_panel.refresh(kernel=getattr(self, "kernel", None))

        ModelSetupWizard(self.root, on_complete=on_complete, on_cancel=lambda: None)

    def _build_events_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="Recent events", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.event_list = tk.Listbox(tab, height=20, bg=UI["input"], fg=UI["muted"], relief=tk.FLAT)
        self.event_list.pack(fill=tk.BOTH, expand=True)
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(row, text="Clear events", command=lambda: self.event_list.delete(0, tk.END)).pack(side=tk.LEFT)
        ttk.Button(row, text="Runtime status", command=self.runtime_status).pack(side=tk.RIGHT)

    def _build_doctor_tab(self, tab: ttk.Frame) -> None:
        from interfaces.desktop.doctor_panel import DoctorPanel
        panel = DoctorPanel(tab)
        panel.pack(fill=tk.BOTH, expand=True)

    def _build_voice_setup_tab(self, tab: ScrollableFrame) -> None:
        self._label(tab, "Voice setup", True)
        info = self._section(tab, "Setup checklist", "Check microphone/STT/TTS before starting full voice mode. Missing voice dependencies are warnings, not core failures.")
        for text, cmd in [
            ("🧪 Run voice setup report", self.voice_setup_report),
            ("🎙 List microphones", self.voice_list_microphones),
            ("🔊 Test pyttsx3 fallback TTS", self.voice_test_pyttsx3),
            ("🗣 Test Piper TTS", self.voice_test_piper),
            ("📦 Copy voice dependency install command", self.copy_voice_install_command),
            ("⚙ Open Settings", self.open_settings),
            ("▶ Start / stop voice process", self.toggle_voice_process),
        ]:
            ttk.Button(info, text=text, command=cmd).pack(fill=tk.X, pady=3)
        self.voice_setup_output = scrolledtext.ScrolledText(tab.body, height=20, wrap=tk.WORD, bg=UI["input"], fg=UI["text"], relief=tk.FLAT)
        self.voice_setup_output.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 8))
        self.voice_setup_output.insert(tk.END, "Run Voice setup report to check microphone, STT, Piper and pyttsx3.\n")
        self.voice_setup_output.configure(state=tk.DISABLED)

    def _build_logs_tab(self, tab: ttk.Frame) -> None:
        header = ttk.Frame(tab)
        header.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(header, text="Recent logs",
                  font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)

        self._log_filter_var = tk.StringVar(value="ERROR")
        ttk.Combobox(header, textvariable=self._log_filter_var,
                     values=["ALL", "WARNING", "ERROR", "CRITICAL"],
                     width=10, state="readonly").pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(header, text="Refresh",
                   command=self._refresh_logs).pack(side=tk.RIGHT)
        ttk.Button(header, text="Copy",
                   command=self._copy_logs).pack(side=tk.RIGHT, padx=(0, 6))

        self._log_text = scrolledtext.ScrolledText(
            tab, wrap=tk.WORD, state=tk.DISABLED,
            bg=UI["input"], fg=UI["text"], font=("Consolas", 9),
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)

    def _refresh_logs(self) -> None:
        level_filter = getattr(self, "_log_filter_var", None)
        filter_val = level_filter.get() if level_filter else "ALL"
        log_file = self._resolve_log_file()
        if not log_file or not log_file.exists():
            self._set_log_text("Log file not found yet. Run JAV for a moment to generate logs.")
            return
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if filter_val != "ALL":
                lines = [l for l in lines if f"[{filter_val}]" in l or f" {filter_val} " in l]
            self._set_log_text("\n".join(lines[-500:]))
        except Exception as exc:
            self._set_log_text(f"Could not read log: {exc}")

    def _set_log_text(self, text: str) -> None:
        widget = getattr(self, "_log_text", None)
        if widget is None:
            return
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state=tk.DISABLED)
        widget.see(tk.END)

    def _copy_logs(self) -> None:
        widget = getattr(self, "_log_text", None)
        if widget is None:
            return
        text = widget.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _resolve_log_file(self):
        from pathlib import Path
        try:
            cfg = getattr(self, "cfg", None)
            if cfg is None:
                return None
            data_dir = Path(cfg.persistence_dir).expanduser()
            runtime = getattr(cfg, "runtime", None)
            if runtime and hasattr(runtime, "resolve_log_dir"):
                log_dir = Path(runtime.resolve_log_dir(str(data_dir))).expanduser()
            else:
                log_dir = data_dir / "logs"
            return log_dir / "jav.log"
        except Exception:
            return None

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
        tag = role if role in {"user", "assistant", "system", "event"} else "body"
        self.chat.insert(tk.END, f"{prefix}: ", tag)
        self.chat.insert(tk.END, f"{text}\n\n", "body")
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

        processed = 0
        try:
            while processed < 25:
                event = self.events.get_nowait()
                self._consume_event_for_ui(event)
                processed += 1
        except queue.Empty:
            pass

        if self.events.qsize() > 200:
            while self.events.qsize() > 100:
                try:
                    self.events.get_nowait()
                except queue.Empty:
                    break

        self._update_cards()
        self._update_voice_status()
        self.root.after(500, self._tick_ui)

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
            self._task_event_count += 1
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
        if etype in {"kernel_started", "model_status_updated"}:
            if hasattr(self, "_model_panel"):
                self._model_panel.refresh(kernel=getattr(self, "kernel", None))
        if etype == "kernel_degraded":
            msg = str(data.get("message") or "One or more modules failed to load.")
            failed = data.get("failed_modules", [])
            names = ", ".join(str(m.get("path", "?")).split("\\")[-1].split("/")[-1]
                              for m in failed[:5])
            detail = f" ({names})" if names else ""
            self._append("system", f"⚠ Degraded mode: {msg}{detail}")
            self._notify("JAV degraded mode", msg)
            try:
                self.status_label.configure(text="degraded mode", foreground="#f0883e")
            except Exception:
                pass

    def _patch_event_tap(self) -> None:
        if self.kernel is None:
            return
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

        self.kernel.event_bus.emit = tapped_emit  # type: ignore[union-attr, method-assign]

    def _refresh_model_status_bg(self) -> None:
        """Fetch router.status() in a daemon thread; cache result for _update_cards()."""
        if self._model_status_refreshing or not self.kernel_ready or self.kernel is None:
            self.root.after(5000, self._refresh_model_status_bg)
            return
        self._model_status_refreshing = True

        def _worker() -> None:
            try:
                router = getattr(self.kernel, "llm_router", None)
                if router is not None and hasattr(router, "status"):
                    status = router.status(refresh=True)
                    self._cached_model_status = status
                    self._model_status_ts = time.time()
                    if hasattr(self, "_model_panel"):
                        self.root.after(0, self._model_panel._update_from_status, status)
            except Exception:
                pass
            finally:
                self._model_status_refreshing = False
            self.root.after(5000, self._refresh_model_status_bg)

        threading.Thread(target=_worker, daemon=True, name="model-status-bg").start()

    def _update_cards(self) -> None:
        if not self.kernel_ready or self.kernel is None or self.api is None:
            self.status_label.configure(text="booting kernel…")
            for key, card in self.cards.items():
                card.set("starting", "kernel booting")
            return
        state = self.api.get_state()
        running = state.get("running")
        safety = state.get("core_state", {}).get("safety_level", "?")
        mods = len(self.kernel.modules)
        self.status_label.configure(text=f"running={running} | modules={mods} | safety=L{safety}")
        self.cards["kernel"].set(f"{'ON' if running else 'OFF'} / {mods} mods", f"Safety L{safety}")

        status = self._cached_model_status
        if status is None:
            self.cards["models"].set("checking…", "loading")
        else:
            roles = status.get("roles") or {}
            available = sum(1 for r in roles.values() if r.get("available"))
            self.cards["models"].set(
                f"{available}/{len(roles)} roles",
                str(status.get("profile") or "profile"),
            )

        self.cards["approvals"].set(str(len(self.pending_approvals)), "pending confirmations")
        mem_dir = getattr(self.cfg.memory, "data_dir", "")
        self.cards["memory"].set("SQLite/vector", str(mem_dir)[:42])
        last_sys = self._last_event_by_type.get("system_status_report") or self._last_event_by_type.get("system_snapshot")
        if last_sys:
            data = last_sys.get("data") or {}
            self.cards["system"].set(str(data.get("status") or data.get("summary") or "OK")[:24], str(data.get("text") or "")[:42])
        else:
            self.cards["system"].set("monitoring", "use Diagnose system")
        self.cards["tasks"].set(str(self._task_event_count), "task chain events")

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
        if not self._ensure_ready():
            return
        assert self.api is not None
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
        if lower in {"/actions", "/action-status"}:
            self.action_status(); return
        if lower in {"/workspace", "/workspace-info"}:
            self._append("system", "Current workspace: " + self._workspace_path_text() + "\nSafe file actions only operate inside this folder. Use Home → Change workspace or Import project into workspace."); return
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

    def _workspace_path_text(self) -> str:
        try:
            actions = getattr(self.cfg, "actions", None)
            return str(Path(getattr(actions, "workspace_path", "~/jarvis_workspace")).expanduser())
        except Exception:
            return "~/jarvis_workspace"

    def _set_workspace_label(self) -> None:
        try:
            self.workspace_label.configure(text=self._workspace_path_text())
        except Exception:
            pass

    def open_workspace(self) -> None:
        path = Path(self._workspace_path_text()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self._append("system", f"Workspace: {path}\nCould not open file manager: {exc}")

    def change_workspace(self) -> None:
        selected = filedialog.askdirectory(title="Choose JAV workspace folder")
        if not selected:
            return
        path = Path(selected).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if getattr(self.cfg, "actions", None) is not None:
                self.cfg.actions.workspace_path = str(path)
            if self.kernel is not None and getattr(self.kernel.config, "actions", None) is not None:
                self.kernel.config.actions.workspace_path = str(path)
            os.environ["ACTION_WORKSPACE_PATH"] = str(path)
            self._set_workspace_label()
            self._append("system", f"Workspace changed to: {path}\nRestart JAV to make every subsystem use this path. Current action executor will use it live when possible.")
        except Exception as exc:
            messagebox.showerror("Workspace", str(exc))

    def import_project_to_workspace(self) -> None:
        src = filedialog.askdirectory(title="Choose project folder to copy into workspace")
        if not src:
            return
        workspace = Path(self._workspace_path_text()).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        src_path = Path(src).expanduser()
        target = workspace / src_path.name
        try:
            import shutil
            if target.exists():
                if not messagebox.askyesno("Import project", f"{target} already exists. Merge/overwrite changed files?"):
                    return
                shutil.copytree(src_path, target, dirs_exist_ok=True)
            else:
                shutil.copytree(src_path, target)
            self._append("system", f"Imported project into workspace: {target}\nNow you can ask: виправ помилки в {src_path.name}")
        except Exception as exc:
            messagebox.showerror("Import project", str(exc))

    def _memory_db_path(self) -> Path:
        try:
            return Path(getattr(self.cfg, "persistence_dir", "~/.jarvis_brain")).expanduser() / "longterm_memory.sqlite3"
        except Exception:
            return Path("~/.jarvis_brain").expanduser() / "longterm_memory.sqlite3"

    def refresh_recent_memory(self) -> None:
        self._load_memory_rows("")

    def search_memory_browser(self) -> None:
        query = self.memory_search_var.get().strip()
        self._load_memory_rows(query)
        if query:
            self.emit("memory_search_requested", {"query_text": query, "top_k": 8, "respond": True}, Priority.COGNITIVE)

    def _load_memory_rows(self, query: str = "") -> None:
        db = self._memory_db_path()
        self._memory_rows = []
        self.memory_list.delete(0, tk.END)
        self.memory_detail.delete("1.0", tk.END)
        if not db.exists():
            self.memory_detail.insert(tk.END, f"Memory database not found yet:\n{db}\nTalk to JAV or run memory status first.")
            return
        try:
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            if query:
                like = f"%{query}%"
                rows = con.execute("SELECT id, memory_type, text, payload_json, importance, timestamp, source FROM memories WHERE text LIKE ? OR source LIKE ? ORDER BY timestamp DESC LIMIT 50", (like, like)).fetchall()
            else:
                rows = con.execute("SELECT id, memory_type, text, payload_json, importance, timestamp, source FROM memories ORDER BY timestamp DESC LIMIT 50").fetchall()
            con.close()
            for row in rows:
                item = dict(row)
                self._memory_rows.append(item)
                snippet = str(item.get("text") or "").replace("\n", " ")[:96]
                self.memory_list.insert(tk.END, f"{item.get('memory_type')}  imp={item.get('importance')}  {snippet}")
            if not rows:
                self.memory_detail.insert(tk.END, "No memory rows found for this query.")
        except Exception as exc:
            self.memory_detail.insert(tk.END, f"Could not read memory DB: {exc}")

    def show_selected_memory(self) -> None:
        self.memory_detail.delete("1.0", tk.END)
        try:
            sel = self.memory_list.curselection()
            if not sel:
                return
            row = self._memory_rows[sel[0]]
            payload = row.get("payload_json") or ""
            try:
                payload = json.dumps(json.loads(payload), ensure_ascii=False, indent=2)[:4000]
            except Exception:
                payload = str(payload)[:4000]
            self.memory_detail.insert(tk.END, f"ID: {row.get('id')}\nType: {row.get('memory_type')}\nSource: {row.get('source')}\nImportance: {row.get('importance')}\nTimestamp: {row.get('timestamp')}\n\nText:\n{row.get('text')}\n\nPayload:\n{payload}")
        except Exception as exc:
            self.memory_detail.insert(tk.END, f"Could not show memory row: {exc}")

    def task_status(self) -> None:
        self.emit("task_chain_status_requested", {"respond": True}, Priority.COGNITIVE)

    def task_step(self) -> None:
        self.emit("task_chain_step_requested", {"respond": True}, Priority.COGNITIVE)

    def gui_status(self) -> None:
        self.emit("gui_task_status_requested", {"respond": True}, Priority.COGNITIVE)

    def gui_step(self) -> None:
        self.emit("gui_task_step_requested", {"respond": True}, Priority.COGNITIVE)

    def model_status(self) -> None:
        if not self._ensure_ready():
            return
        assert self.kernel is not None
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

    def _run_helper_command(self, args: list[str], timeout: int = 30) -> str:
        """Run a helper command in source or frozen mode and return combined output."""
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
            cmd = [sys.executable, *args]
        else:
            root = Path(__file__).resolve().parents[2]
            cmd = [sys.executable, str(root / "main.py"), *args] if args and args[0].startswith("--") else [sys.executable, *args]
        try:
            proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout)
            out = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0:
                out += f"\n[exit code {proc.returncode}]"
            return out.strip() or "(no output)"
        except Exception as exc:
            return f"Command failed: {exc}"

    def _set_voice_output(self, text: str) -> None:
        try:
            self.voice_setup_output.configure(state=tk.NORMAL)
            self.voice_setup_output.delete("1.0", tk.END)
            self.voice_setup_output.insert(tk.END, text)
            self.voice_setup_output.configure(state=tk.DISABLED)
        except Exception:
            self._append("system", text)

    def voice_setup_report(self) -> None:
        out = self._run_helper_command(["--voice-doctor"], timeout=35)
        self._set_voice_output(out)
        self._append("system", "Voice setup report completed. Open the Voice tab for details.")

    def voice_list_microphones(self) -> None:
        root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--voice-list-mics"]
        else:
            cmd = [sys.executable, str(root / "scripts" / "voice_setup.py"), "--list-mics"]
        try:
            proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=20)
            self._set_voice_output(((proc.stdout or "") + (proc.stderr or "")).strip() or "(no output)")
        except Exception as exc:
            self._set_voice_output(f"Could not list microphones: {exc}")

    def voice_test_pyttsx3(self) -> None:
        root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--voice-test-pyttsx3", "JAV pyttsx3 voice test."]
        else:
            cmd = [sys.executable, str(root / "scripts" / "voice_setup.py"), "--test-pyttsx3", "JAV pyttsx3 voice test."]
        try:
            subprocess.Popen(cmd, cwd=str(root))
            self._append("system", "Started pyttsx3 test in a helper process.")
        except Exception as exc:
            self._append("system", f"Could not start pyttsx3 test: {exc}")

    def voice_test_piper(self) -> None:
        root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--voice-test-piper", "JAV Piper voice test."]
        else:
            cmd = [sys.executable, str(root / "scripts" / "voice_setup.py"), "--test-piper", "JAV Piper voice test."]
        try:
            subprocess.Popen(cmd, cwd=str(root))
            self._append("system", "Started Piper test in a helper process.")
        except Exception as exc:
            self._append("system", f"Could not start Piper test: {exc}")

    def copy_voice_install_command(self) -> None:
        cmd = "python scripts/bootstrap_dependencies.py --with-voice"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
            self._append("system", "Copied voice dependency command: " + cmd)
        except Exception:
            self._append("system", cmd)

    def toggle_voice_process(self) -> None:
        if self.voice_process and self.voice_process.poll() is None:
            try:
                self.voice_process.terminate()
                self._append("system", "Voice process stopped.")
            except Exception as exc:
                self._append("system", f"Could not stop voice process: {exc}")
            return
        try:
            if getattr(sys, "frozen", False):
                root = Path(sys.executable).resolve().parent
                cmd = [sys.executable, "--voice"]
            else:
                root = Path(__file__).resolve().parents[2]
                cmd = [sys.executable, str(root / "main.py"), "--voice"]
            self.voice_process = subprocess.Popen(cmd, cwd=str(root))
            self._append("system", f"Voice process started pid={self.voice_process.pid}. It runs as a separate process.")
        except Exception as exc:
            self._append("system", f"Could not start voice process: {exc}")

    def open_settings(self) -> None:
        SettingsWindow(self.root, on_saved=self._settings_saved)

    def _settings_saved(self, updates: Dict[str, str]) -> None:
        try:
            # Make saved settings visible immediately to helpers that read os.environ.
            for key, value in (updates or {}).items():
                os.environ[str(key)] = str(value)
            if self.kernel is None:
                self._append("system", "Settings saved. Kernel is not ready yet; restart JAV or wait for startup to apply live settings.")
                return
            actions = getattr(self.kernel.config, "actions", None)
            if actions is not None:
                if "ACTION_WORKSPACE_PATH" in updates:
                    actions.workspace_path = updates["ACTION_WORKSPACE_PATH"]
                if "ACTION_ALLOW_SHELL" in updates:
                    actions.allow_shell = updates["ACTION_ALLOW_SHELL"].lower() == "true"
                if "ACTIONS_V7_ENABLED" in updates:
                    actions.enabled = updates["ACTIONS_V7_ENABLED"].lower() == "true"
            # Rebuild model router live when model/provider/API settings changed.
            if any(str(k).startswith(("MODEL_", "OLLAMA_", "OPENAI_", "GEMINI_", "ANTHROPIC_", "LLAMACPP_")) for k in updates):
                try:
                    from config import LLMRouterConfig
                    from core.llm_router import LLMRouter
                    self.kernel.config.llm = LLMRouterConfig()
                    self.kernel.llm_router = LLMRouter(self.kernel.config.llm)
                    self._cached_model_status = self.kernel.llm_router.status(refresh=True)
                    if hasattr(self, "_model_panel"):
                        self._model_panel._update_from_status(self._cached_model_status)
                    self._append("system", "Model settings saved and model router reloaded live. Run Models → Health Check to verify.")
                    return
                except Exception as exc:
                    self._append("system", f"Settings saved, but live model-router reload failed: {exc}")
            self._append("system", "Settings saved. Some action/model settings were applied live; restart JAV for path/voice/OCR/UI settings to fully reload.")
        except Exception as exc:
            self._append("system", f"Settings saved, but live apply failed: {exc}")

    def set_safety(self, level: int) -> None:
        try:
            if not self._ensure_ready():
                return
            assert self.kernel is not None
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
            if self.api is not None:
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
