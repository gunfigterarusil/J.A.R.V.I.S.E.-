"""Minimal modern desktop shell for JAV.

This is intentionally dependency-light (Tkinter only) so the repaired build can
start reliably before a future PySide/Tauri rewrite.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from config import KernelConfig
from core.kernel import KernelAPI
from core.event_bus import Priority
from main import build_kernel


class DesktopApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("JAV Assistant")
        self.root.geometry("1120x720")
        self.root.minsize(900, 560)
        self.queue: queue.Queue[str] = queue.Queue()
        self.kernel_api: KernelAPI | None = None
        self.kernel_ready = False
        self._last_event_count = 0
        self._build_ui()
        self._boot_kernel_background()
        self.root.after(250, self._poll_events)

    def _build_ui(self) -> None:
        self.root.configure(bg="#0f172a")
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#0f172a")
        style.configure("Card.TFrame", background="#111827")
        style.configure("TLabel", background="#0f172a", foreground="#e5e7eb")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#f8fafc", background="#0f172a")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#94a3b8", background="#0f172a")
        style.configure("TButton", font=("Segoe UI", 10))

        header = ttk.Frame(self.root, padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="JAV Assistant", style="Title.TLabel").pack(anchor="w")
        self.status_var = tk.StringVar(value="Booting kernel…")
        ttk.Label(header, textvariable=self.status_var, style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(self.root, padding=(18, 0, 18, 18))
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(body, width=300)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        self.chat = tk.Text(left, wrap="word", bg="#020617", fg="#e5e7eb", insertbackground="#f8fafc", relief="flat", padx=14, pady=14, font=("Segoe UI", 11))
        self.chat.pack(fill="both", expand=True)
        self.chat.insert("end", "JAV: Starting cognitive kernel…\n")
        self.chat.configure(state="disabled")

        input_row = ttk.Frame(left, padding=(0, 10, 0, 0))
        input_row.pack(fill="x")
        self.input_var = tk.StringVar()
        entry = ttk.Entry(input_row, textvariable=self.input_var, font=("Segoe UI", 11))
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self._send())
        ttk.Button(input_row, text="Send", command=self._send).pack(side="left", padx=(8, 0))

        ttk.Label(right, text="Quick actions", style="Title.TLabel").pack(anchor="w", pady=(0, 10))
        actions = [
            ("Doctor", self._doctor_hint),
            ("Status", lambda: self._send_text("/status")),
            ("Modules", lambda: self._send_text("/modules")),
            ("Memory", lambda: self._send_text("/memory")),
            ("Help", lambda: self._send_text("/help")),
        ]
        for text, cmd in actions:
            ttk.Button(right, text=text, command=cmd).pack(fill="x", pady=4)

        ttk.Separator(right).pack(fill="x", pady=12)
        ttk.Label(right, text="Events", style="Sub.TLabel").pack(anchor="w")
        self.events = tk.Text(right, height=16, wrap="word", bg="#111827", fg="#cbd5e1", relief="flat", padx=10, pady=10, font=("Consolas", 9))
        self.events.pack(fill="both", expand=True, pady=(6, 0))

    def _append_chat(self, line: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", line + "\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append_event(self, line: str) -> None:
        self.events.insert("end", line + "\n")
        self.events.see("end")

    def _boot_kernel_background(self) -> None:
        def boot() -> None:
            try:
                cfg = KernelConfig()
                kernel = build_kernel(cfg)
                self.kernel_api = KernelAPI(kernel)
                self.kernel_api.start_in_background()
                time.sleep(0.4)
                self.kernel_ready = True
                self.queue.put("__READY__")
            except Exception as exc:
                log_dir = Path(KernelConfig().persistence_dir).expanduser() / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / "desktop_crash.log").write_text(str(exc), encoding="utf-8")
                self.queue.put(f"__ERROR__{exc}")
        threading.Thread(target=boot, daemon=True).start()

    def _send_text(self, text: str) -> None:
        self.input_var.set(text)
        self._send()

    def _send(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        self._append_chat(f"You: {text}")
        if not self.kernel_api or not self.kernel_ready:
            self._append_chat("JAV: Kernel is still starting.")
            return
        if text.startswith("/"):
            self._handle_local_command(text)
            return
        self.kernel_api.emit_event("user_utterance", {"text": text, "input_mode": "desktop"}, Priority.REALTIME)

    def _handle_local_command(self, text: str) -> None:
        if not self.kernel_api:
            return
        cmd = text.lower().strip()
        if cmd in {"/help", "help"}:
            self._append_chat("JAV: Commands: /help /status /modules /memory. Natural chat is sent to the cognitive loop.")
        elif cmd == "/status":
            state = self.kernel_api.get_state()
            self._append_chat(f"JAV: running={state.get('running')} uptime={state.get('core_state', {}).get('uptime', 0):.1f}s")
        elif cmd == "/modules":
            mods = self.kernel_api.get_modules()
            self._append_chat("JAV: Modules: " + ", ".join(m.get("module_id", "?") for m in mods))
        elif cmd == "/memory":
            self._append_chat("JAV: Memory module is active if loaded. Full SQLite/vector memory is planned for the next upgrade.")
        else:
            self.kernel_api.emit_event("user_utterance", {"text": text, "input_mode": "desktop"}, Priority.REALTIME)

    def _doctor_hint(self) -> None:
        messagebox.showinfo("JAV Doctor", "Run this in a terminal:\n\npython main.py --doctor")

    def _poll_events(self) -> None:
        while True:
            try:
                msg = self.queue.get_nowait()
            except queue.Empty:
                break
            if msg == "__READY__":
                self.status_var.set("Kernel ready. You can chat now.")
                self._append_chat("JAV: Kernel ready.")
            elif msg.startswith("__ERROR__"):
                self.status_var.set("Startup failed. See desktop_crash.log.")
                self._append_chat("JAV: Startup failed: " + msg.replace("__ERROR__", ""))

        if self.kernel_api:
            events = list(reversed(self.kernel_api.get_events()))
            new_events = events[self._last_event_count:]
            self._last_event_count = len(events)
            for e in new_events[-30:]:
                et = e.get("type", "?")
                self._append_event(et)
                if et == "response_generated":
                    text = e.get("data", {}).get("text", "")
                    if text:
                        self._append_chat("JAV: " + text)
        self.root.after(300, self._poll_events)

    def run(self) -> None:
        self.root.mainloop()
        if self.kernel_api:
            self.kernel_api.shutdown()


def run_desktop() -> None:
    DesktopApp().run()
