"""interfaces/desktop/doctor_panel.py — Embeddable GUI doctor panel.

V15.5: Used in the desktop app's Doctor tab to run diagnostic checks,
show pass/fail results, and offer one-click repair for fixable issues.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.doctor import DoctorCheck


class DoctorPanel(ttk.Frame):
    """Scrollable doctor check results panel with Run and Repair buttons."""

    def __init__(self, master: tk.Widget, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._running = False
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(header, text="System Doctor",
                  font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)

        self._status_lbl = ttk.Label(header, text="Not run yet", foreground="#8b949e")
        self._status_lbl.pack(side=tk.LEFT, padx=(10, 0))

        self._run_btn = ttk.Button(header, text="Run Doctor", command=self.run)
        self._run_btn.pack(side=tk.RIGHT)

        self._results_frame = ttk.Frame(self)
        self._results_frame.pack(fill=tk.BOTH, expand=True)

        self._placeholder = ttk.Label(
            self._results_frame,
            text="Click 'Run Doctor' to check your JAV installation.",
            foreground="#8b949e",
        )
        self._placeholder.pack(pady=20)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self) -> None:
        if self._running:
            return
        self._running = True
        self._run_btn.configure(state="disabled")
        self._status_lbl.configure(text="Running checks…")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            from scripts.doctor import run_checks
            checks = run_checks()
        except Exception as exc:
            checks = []
            self.after(0, self._status_lbl.configure,
                       {"text": f"Doctor error: {exc}", "foreground": "#f85149"})
        self.after(0, self._show_results, checks)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def _show_results(self, checks: "List[DoctorCheck]") -> None:
        for widget in self._results_frame.winfo_children():
            widget.destroy()

        if not checks:
            ttk.Label(self._results_frame, text="No checks returned.",
                      foreground="#8b949e").pack(pady=20)
            self._running = False
            self._run_btn.configure(state="normal")
            return

        required = [c for c in checks if getattr(c, "category", "required") == "required"]
        required_failed = [c for c in required if not c.passed]
        warnings = [c for c in checks if getattr(c, "category", "required") != "required" and not c.passed]
        if required_failed:
            color = "#f85149"
            text = f"{len(required_failed)} required problem(s), {len(warnings)} optional warning(s)"
        elif warnings:
            color = "#f0883e"
            text = f"Core OK, {len(warnings)} optional warning(s)"
        else:
            color = "#3fb950"
            text = "All checks passed"
        self._status_lbl.configure(text=text, foreground=color)

        # Scrollable container
        canvas = tk.Canvas(self._results_frame, highlightthickness=0,
                           bg=self._results_frame.cget("background"))
        scrollbar = ttk.Scrollbar(self._results_frame, orient="vertical",
                                  command=canvas.yview)
        body = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_configure(event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_configure)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mousewheel
        def _on_wheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_wheel)

        # Category separators
        last_cat: str = ""
        for chk in sorted(checks, key=lambda c: (c.category, c.name)):
            if chk.category != last_cat:
                last_cat = chk.category
                sep_lbl = ttk.Label(body,
                                    text=f"─── {chk.category.upper()} ───",
                                    foreground="#8b949e",
                                    font=("Segoe UI", 8))
                sep_lbl.pack(fill=tk.X, padx=4, pady=(6, 2))

            row = ttk.Frame(body)
            row.pack(fill=tk.X, padx=4, pady=1)

            is_required = getattr(chk, "category", "required") == "required"
            if chk.passed:
                icon_text, icon_color = "✓", "#3fb950"
            elif is_required:
                icon_text, icon_color = "✗", "#f85149"
            else:
                icon_text, icon_color = "!", "#f0883e"
            ttk.Label(row, text=icon_text, foreground=icon_color,
                      width=3, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

            ttk.Label(row, text=chk.name, width=32,
                      anchor="w").pack(side=tk.LEFT)

            if chk.detail:
                ttk.Label(row, text=chk.detail, foreground="#8b949e",
                          anchor="w").pack(side=tk.LEFT, padx=(4, 0))

            if chk.fixable and chk.fix_cmd and not chk.passed:
                ttk.Button(
                    row, text="Repair",
                    command=lambda cmd=chk.fix_cmd: self._repair(cmd),
                ).pack(side=tk.RIGHT, padx=(4, 0))

        self._running = False
        self._run_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------
    def _repair(self, cmd: str) -> None:
        import shlex
        parts = shlex.split(cmd)
        if parts and parts[0] == "pip":
            parts = [sys.executable, "-m"] + parts
        try:
            subprocess.Popen(parts)
            messagebox.showinfo(
                "Repair",
                f"Running: {' '.join(parts)}\n\n"
                "Check the console window for output.\n"
                "Restart JAV after installation completes.",
            )
        except Exception as exc:
            messagebox.showerror("Repair failed", str(exc))
