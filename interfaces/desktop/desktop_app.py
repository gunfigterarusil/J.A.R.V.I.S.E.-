"""Native desktop interface for JAV/Jarvis Brain Core.

V9.3 UI refresh:
- resizable paned layout
- right panel split into tabs instead of one tall column
- quick actions are scrollable and stay inside the window
- larger input area and cleaner event/status panels
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from interfaces.desktop.settings_window import SettingsWindow
from pathlib import Path
from typing import Any, Dict

from config import KernelConfig
from core.kernel import Kernel, KernelAPI
from core.event_bus import CognitiveEvent, Priority
from core.safety.permission_manager import PermissionLevel
from main import build_kernel


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#111722")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))


class DesktopApp:
    """Native desktop shell for Jarvis."""

    def __init__(self, cfg: KernelConfig | None = None) -> None:
        self.cfg = cfg or KernelConfig()
        self.kernel: Kernel = build_kernel(self.cfg)
        self.api = KernelAPI(self.kernel)
        self.messages: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.events: "queue.Queue[dict]" = queue.Queue()
        self._patch_event_tap()

        self.root = tk.Tk()
        self.root.title("JAV — Jarvis Brain Core")
        self.root.geometry("1180x760")
        self.root.minsize(920, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self.api.start_in_background()
        self._append("system", "JAV desktop interface started. You can type normal requests, use voice/chat commands, or open Settings Center.")
        self._tick_ui()

    def _build_ui(self) -> None:
        self.root.configure(bg="#0e1117")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#0e1117")
        style.configure("Card.TFrame", background="#111722")
        style.configure("TLabel", background="#0e1117", foreground="#dce6f2")
        style.configure("Card.TLabel", background="#111722", foreground="#dce6f2")
        style.configure("TButton", padding=7)
        style.configure("Accent.TButton", padding=8)
        style.configure("TNotebook", background="#0e1117", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(10, 5))

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X)
        ttk.Label(header, text="JAV / Jarvis Brain Core", font=("Segoe UI", 17, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Settings Center", command=self.open_settings).pack(side=tk.RIGHT, padx=(8, 0))
        self.status_label = ttk.Label(header, text="starting...", font=("Segoe UI", 10))
        self.status_label.pack(side=tk.RIGHT)

        paned = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        left = ttk.Frame(paned)
        right = ttk.Frame(paned, width=330)
        paned.add(left, weight=4)
        paned.add(right, weight=1)

        chat_card = ttk.Frame(left, style="Card.TFrame", padding=8)
        chat_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(chat_card, text="Conversation", style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.chat = scrolledtext.ScrolledText(
            chat_card,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#080b10",
            fg="#e6edf5",
            insertbackground="#e6edf5",
            relief=tk.FLAT,
            font=("Consolas", 11),
            padx=10,
            pady=10,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        input_row = ttk.Frame(left)
        input_row.pack(fill=tk.X, pady=(8, 0))
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_row, textvariable=self.input_var, font=("Segoe UI", 11))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_entry.bind("<Return>", lambda _e: self.send_message())
        ttk.Button(input_row, text="Send", command=self.send_message).pack(side=tk.RIGHT, padx=(8, 0))

        self._build_right_tabs(right)

    def _build_right_tabs(self, parent: ttk.Frame) -> None:
        tabs = ttk.Notebook(parent)
        tabs.pack(fill=tk.BOTH, expand=True)

        controls = ScrollableFrame(tabs)
        commands = ScrollableFrame(tabs)
        events_tab = ttk.Frame(tabs, padding=6)
        tabs.add(controls, text="Controls")
        tabs.add(commands, text="Commands")
        tabs.add(events_tab, text="Events")

        def add_button(container, text, command):
            ttk.Button(container.body, text=text, command=command).pack(fill=tk.X, pady=3, padx=4)

        ttk.Label(controls.body, text="Main controls", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 6), padx=4)
        add_button(controls, "Read screen", self.read_screen)
        add_button(controls, "Sleep / consolidate", self.sleep_cycle)
        add_button(controls, "Memory / storage status", self.memory_status)
        add_button(controls, "Action status", self.action_status)
        add_button(controls, "Web search help", lambda: self._prefill("пошукай в інтернеті "))
        add_button(controls, "Web learn help", lambda: self._prefill("вивчи "))
        add_button(controls, "Settings Center", self.open_settings)
        ttk.Separator(controls.body).pack(fill=tk.X, pady=8, padx=4)
        ttk.Label(controls.body, text="Safety", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 6), padx=4)
        add_button(controls, "Safety L1 read-only", lambda: self.set_safety(1))
        add_button(controls, "Safety L4 file-write", lambda: self.set_safety(4))
        add_button(controls, "Safety L5 shell", lambda: self.set_safety(5))

        ttk.Label(commands.body, text="Click to fill input", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 6), padx=4)
        examples = [
            "покажи стан пам'яті",
            "згадай переносний диск",
            "прочитай файл README.md",
            "знайди error в .",
            "покажи файли .",
            "створи папку notes",
            "запиши в notes/test.txt :: hello",
            "запусти python --version",
            "прочитай екран",
            "запусти сон",
            "покажи налаштування",
            "виправ помилки в .",
            "пошукай в інтернеті latest Python release",
            "вивчи як працює vector memory",
        ]
        for text in examples:
            add_button(commands, text, lambda t=text: self._prefill(t))

        ttk.Label(events_tab, text="Recent events", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.event_list = tk.Listbox(events_tab, height=20, bg="#080b10", fg="#b8c5d6", relief=tk.FLAT)
        self.event_list.pack(fill=tk.BOTH, expand=True)

    def _prefill(self, text: str) -> None:
        self.input_var.set(text)
        self.input_entry.focus_set()
        self.input_entry.icursor(tk.END)

    def _append(self, role: str, text: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        prefix = {"user": "You", "assistant": "Jarvis", "system": "System", "event": "Event"}.get(role, role)
        self.chat.insert(tk.END, f"{prefix}: {text}\n\n")
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

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
                label = f"{event.get('type')} ← {event.get('source_module')}"
                self.event_list.insert(0, label)
                if self.event_list.size() > 120:
                    self.event_list.delete(120, tk.END)
        except queue.Empty:
            pass

        state = self.api.get_state()
        running = state.get("running")
        safety = state.get("core_state", {}).get("safety_level", "?")
        mods = len(self.kernel.modules)
        self.status_label.configure(text=f"running={running} | modules={mods} | safety=L{safety}")
        self.root.after(250, self._tick_ui)

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
                if text:
                    self.messages.put_nowait(("assistant", text))
            except Exception:
                pass

        self.kernel.event_bus.emit = tapped_emit  # type: ignore[method-assign]

    def emit(self, type_: str, data: Dict[str, Any], priority: Priority = Priority.COGNITIVE) -> None:
        self.api.emit_event(type_, data, priority)

    def send_message(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        self._append("user", text)

        lower = text.lower()
        if lower in {"/see", "/screen", "/read-screen", "/explain-screen"}:
            self.read_screen(); return
        if lower in {"/sleep", "/dream", "/consolidate", "/memory-consolidate"}:
            self.sleep_cycle(); return
        if lower in {"/actions", "/workspace", "/action-status"}:
            self.action_status(); return
        if lower in {"/memory", "/memory-status", "/storage"}:
            self.memory_status(); return
        if lower.startswith("/web-search "):
            self.emit("web_search_requested", {"query": text.split(maxsplit=1)[1], "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/web-learn "):
            self.emit("web_learn_requested", {"topic": text.split(maxsplit=1)[1], "respond": True}, Priority.COGNITIVE); return
        if lower.startswith("/approve"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                self.emit("v7_user_approval", {"pending_id": parts[1].strip()}, Priority.REALTIME)
            else:
                self._append("system", "Usage: /approve <pending_id>")
            return
        if lower.startswith("/deny"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                self.emit("v7_user_deny", {"pending_id": parts[1].strip()}, Priority.REALTIME)
            else:
                self._append("system", "Usage: /deny <pending_id>")
            return

        self.emit("user_utterance", {"text": text, "input_mode": "desktop"}, Priority.REALTIME)

    def read_screen(self) -> None:
        self.emit("screen_capture_requested", {"request_id": f"desktop_screen_{int(time.time())}", "reason": "desktop_button", "respond": True}, Priority.REALTIME)

    def sleep_cycle(self) -> None:
        self.emit("sleep_cycle_requested", {"reason": "desktop_button", "force": True, "respond": True}, Priority.COGNITIVE)

    def action_status(self) -> None:
        self.emit("action_status_requested", {"respond": True}, Priority.COGNITIVE)

    def memory_status(self) -> None:
        self.emit("memory_status_requested", {"respond": True}, Priority.COGNITIVE)

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
            self._append("system", "Settings saved. Restart JAV for provider/path/voice/OCR/web-learning settings to fully reload. Some action settings were applied live.")
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
            self._append("system", "Shutting down...")
            self.api.shutdown()
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.input_entry.focus_set()
        self.root.mainloop()


def run_desktop_app(cfg: KernelConfig | None = None) -> None:
    app = DesktopApp(cfg)
    app.run()
