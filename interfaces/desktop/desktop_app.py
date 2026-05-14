"""Native desktop interface for JAV/Jarvis Brain Core.

V8 Desktop MVP uses Tkinter, so it does not require a browser or Electron.
It starts the kernel in a background thread through KernelAPI and talks to it
through the event bus.
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


class DesktopApp:
    """Small native desktop shell for Jarvis."""

    def __init__(self, cfg: KernelConfig | None = None) -> None:
        self.cfg = cfg or KernelConfig()
        self.kernel: Kernel = build_kernel(self.cfg)
        self.api = KernelAPI(self.kernel)
        self.messages: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.events: "queue.Queue[dict]" = queue.Queue()
        self._patch_event_tap()

        self.root = tk.Tk()
        self.root.title("JAV — Jarvis Brain Core")
        self.root.geometry("1040x720")
        self.root.minsize(860, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self.api.start_in_background()
        self._append("system", "JAV desktop interface started. Type a message, command, or use the buttons.")
        self._tick_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.configure(bg="#101216")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#101216")
        style.configure("TLabel", background="#101216", foreground="#dfe7f1")
        style.configure("TButton", padding=8)
        style.configure("Accent.TButton", padding=8)

        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        header = ttk.Frame(main)
        header.pack(fill=tk.X)
        self.title_label = ttk.Label(header, text="JAV / Jarvis Brain Core", font=("Segoe UI", 16, "bold"))
        self.title_label.pack(side=tk.LEFT)
        self.status_label = ttk.Label(header, text="starting...", font=("Segoe UI", 10))
        self.status_label.pack(side=tk.RIGHT)

        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=True, pady=(10, 8))

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = ttk.Frame(body, width=260)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        self.chat = scrolledtext.ScrolledText(
            left,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#0b0d11",
            fg="#e6edf5",
            insertbackground="#e6edf5",
            relief=tk.FLAT,
            font=("Consolas", 11),
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        input_row = ttk.Frame(left)
        input_row.pack(fill=tk.X, pady=(8, 0))
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_row, textvariable=self.input_var, font=("Segoe UI", 11))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_entry.bind("<Return>", lambda _e: self.send_message())
        ttk.Button(input_row, text="Send", command=self.send_message).pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Label(right, text="Controls", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Button(right, text="Read screen (/see)", command=self.read_screen).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Sleep / consolidate", command=self.sleep_cycle).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Action status", command=self.action_status).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Memory / storage status", command=self.memory_status).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Settings Center", command=self.open_settings).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Safety L1", command=lambda: self.set_safety(1)).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Safety L4 file-write", command=lambda: self.set_safety(4)).pack(fill=tk.X, pady=3)
        ttk.Button(right, text="Safety L5 shell", command=lambda: self.set_safety(5)).pack(fill=tk.X, pady=3)

        ttk.Label(right, text="Fast commands", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(16, 6))
        examples = [
            "покажи стан пам'яті",
            "прочитай файл README.md",
            "знайди error в .",
            "покажи файли .",
            "створи папку notes",
            "запусти python --version",
            "прочитай екран",
            "запусти сон",
            "покажи налаштування",
            "виправ помилки в .",
        ]
        for text in examples:
            ttk.Button(right, text=text, command=lambda t=text: self._prefill(t)).pack(fill=tk.X, pady=2)

        ttk.Label(right, text="Recent events", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(16, 6))
        self.event_list = tk.Listbox(right, height=12, bg="#0b0d11", fg="#b8c5d6", relief=tk.FLAT)
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
                if self.event_list.size() > 60:
                    self.event_list.delete(60, tk.END)
        except queue.Empty:
            pass

        state = self.api.get_state()
        running = state.get("running")
        safety = state.get("core_state", {}).get("safety_level", "?")
        mods = len(self.kernel.modules)
        self.status_label.configure(text=f"running={running} | modules={mods} | safety=L{safety}")
        self.root.after(250, self._tick_ui)

    # ------------------------------------------------------------------
    # Event bridge
    # ------------------------------------------------------------------
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
                if event.type == "response_generated":
                    text = str(event.data.get("text", "") or "").strip()
                    if text:
                        self.messages.put_nowait(("assistant", text))
                elif event.type == "screen_parsed" and event.data.get("respond"):
                    summary = str(event.data.get("summary", "") or "").strip()
                    if summary:
                        self.messages.put_nowait(("assistant", summary))
                elif event.type == "sleep_cycle_completed":
                    summary = str(event.data.get("summary", "") or "").strip()
                    if summary:
                        self.messages.put_nowait(("assistant", "Sleep cycle completed. " + summary))
                elif event.type == "action_result" and event.data.get("respond_fallback"):
                    self.messages.put_nowait(("assistant", str(event.data)))
            except Exception:
                pass

        self.kernel.event_bus.emit = tapped_emit  # type: ignore[method-assign]

    def emit(self, type_: str, data: Dict[str, Any], priority: Priority = Priority.COGNITIVE) -> None:
        self.api.emit_event(type_, data, priority)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def send_message(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        self._append("user", text)

        lower = text.lower()
        if lower in {"/see", "/screen", "/read-screen", "/explain-screen"}:
            self.read_screen()
            return
        if lower in {"/sleep", "/dream", "/consolidate", "/memory-consolidate"}:
            self.sleep_cycle()
            return
        if lower in {"/actions", "/workspace", "/action-status"}:
            self.action_status()
            return
        if lower in {"/memory", "/memory-status", "/storage"}:
            self.memory_status()
            return
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
        self.emit(
            "screen_capture_requested",
            {"request_id": f"desktop_screen_{int(time.time())}", "reason": "desktop_button", "respond": True},
            Priority.REALTIME,
        )

    def sleep_cycle(self) -> None:
        self.emit(
            "sleep_cycle_requested",
            {"reason": "desktop_button", "force": True, "respond": True},
            Priority.COGNITIVE,
        )

    def action_status(self) -> None:
        self.emit("action_status_requested", {"respond": True}, Priority.COGNITIVE)

    def memory_status(self) -> None:
        self.emit("memory_status_requested", {"respond": True}, Priority.COGNITIVE)

    def open_settings(self) -> None:
        SettingsWindow(self.root, on_saved=self._settings_saved)

    def _settings_saved(self, updates: Dict[str, str]) -> None:
        # Apply settings that can safely change live. Deeper module settings are loaded on restart.
        try:
            actions = getattr(self.kernel.config, "actions", None)
            if actions is not None:
                if "ACTION_WORKSPACE_PATH" in updates:
                    actions.workspace_path = updates["ACTION_WORKSPACE_PATH"]
                if "ACTION_ALLOW_SHELL" in updates:
                    actions.allow_shell = updates["ACTION_ALLOW_SHELL"].lower() == "true"
                if "ACTIONS_V7_ENABLED" in updates:
                    actions.enabled = updates["ACTIONS_V7_ENABLED"].lower() == "true"
            changed_paths = []
            for key in ("JARVIS_DATA_DIR", "ACTION_WORKSPACE_PATH", "SCREENSHOT_DIR"):
                if key in updates and updates[key]:
                    changed_paths.append(f"{key}={updates[key]}")
            extra = "\n" + "\n".join(changed_paths) if changed_paths else ""
            self._append("system", "Settings saved. Restart JAV for all modules to reload memory paths, providers, voice, OCR and module options. Some action settings were applied live." + extra)
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
