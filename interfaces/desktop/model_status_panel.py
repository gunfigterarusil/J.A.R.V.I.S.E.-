"""interfaces/desktop/model_status_panel.py — Model status panel for the Models tab.

ModelStatusPanel shows the current profile, per-role provider/model assignments,
and availability status.  It can run a background health check and open the
ModelSetupWizard for guided reconfiguration.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Dict, Optional

if TYPE_CHECKING:
    pass

_BG = "#0d1117"
_BG_CARD = "#161b22"
_FG = "#e6edf3"
_FG_MUTED = "#8b949e"
_GREEN = "#3fb950"
_RED = "#f85149"
_ORANGE = "#f0883e"

_ROLES = ["fast", "reason", "code", "critic", "vision", "embedding", "action"]


def _read_env_model_config() -> Dict[str, str]:
    """Read model-related env vars from the running process environment."""
    keys = [
        "MODEL_PROFILE",
        "OLLAMA_HOST",
        "MODEL_FAST_PROVIDER", "MODEL_FAST_NAME",
        "MODEL_REASON_PROVIDER", "MODEL_REASON_NAME",
        "MODEL_CODE_PROVIDER", "MODEL_CODE_NAME",
        "MODEL_CRITIC_PROVIDER", "MODEL_CRITIC_NAME",
        "MODEL_VISION_PROVIDER", "MODEL_VISION_NAME",
        "MODEL_EMBEDDING_PROVIDER", "MODEL_EMBEDDING_NAME",
        "MODEL_ACTION_PROVIDER", "MODEL_ACTION_NAME",
    ]
    return {k: os.environ.get(k, "") for k in keys}


class ModelStatusPanel(ttk.Frame):
    """Scrollable model status panel — profile info + per-role table + health check."""

    def __init__(self, master: tk.Widget, kernel=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._kernel = kernel
        self._checking = False
        self._row_widgets: list = []
        self._last_status: Optional[Dict] = None
        self._build()
        self.refresh(kernel=kernel)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.configure(style="TFrame")

        # ── Header row ─────────────────────────────────────────────────
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill=tk.X, pady=(0, 8))

        profile_box = ttk.Frame(header, style="Card.TFrame", padding=(10, 6))
        profile_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(profile_box, text="Current Profile", style="Muted.Card.TLabel",
                  font=("Segoe UI", 9)).pack(anchor="w")
        self._profile_lbl = ttk.Label(profile_box, text="—", style="Card.TLabel",
                                      font=("Segoe UI", 13, "bold"))
        self._profile_lbl.pack(anchor="w")

        btn_box = ttk.Frame(header, style="TFrame")
        btn_box.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btn_box, text="Setup Wizard", command=self._open_wizard,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_box, text="Refresh", command=lambda: self.refresh()).pack(side=tk.LEFT)

        # ── Roles table ─────────────────────────────────────────────────
        table_frame = ttk.Frame(self, style="Card.TFrame", padding=10)
        table_frame.pack(fill=tk.X, pady=(0, 8))

        headers = ["Role", "Provider", "Model", "Status"]
        widths = [90, 100, 220, 60]
        for col, (h, w) in enumerate(zip(headers, widths)):
            ttk.Label(table_frame, text=h, style="Muted.Card.TLabel",
                      font=("Segoe UI", 9, "bold"), width=w // 9).grid(
                row=0, column=col, sticky="w", padx=(0, 8), pady=(0, 4))

        self._table_frame = table_frame

        # ── Footer ─────────────────────────────────────────────────────
        footer = ttk.Frame(self, style="TFrame")
        footer.pack(fill=tk.X, pady=(0, 4))
        self._avail_lbl = ttk.Label(footer, text="Available providers: —",
                                    style="Muted.TLabel", font=("Segoe UI", 9))
        self._avail_lbl.pack(side=tk.LEFT)
        self._check_btn = ttk.Button(footer, text="Run Health Check",
                                     command=self._run_health_check)
        self._check_btn.pack(side=tk.RIGHT)
        self._status_lbl = ttk.Label(footer, text="", style="Muted.TLabel",
                                     font=("Segoe UI", 9))
        self._status_lbl.pack(side=tk.RIGHT, padx=(0, 8))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self, kernel=None) -> None:
        """Update display without blocking. Uses cached status if available, else reads env vars."""
        if kernel is not None:
            self._kernel = kernel
        if self._last_status is not None:
            self._update_from_status(self._last_status)
        else:
            self._update_from_env()

    # ------------------------------------------------------------------
    # Internal update helpers
    # ------------------------------------------------------------------
    def _update_from_status(self, status: Dict) -> None:
        self._last_status = status
        profile = status.get("profile", "—").upper()
        self._profile_lbl.configure(text=profile)

        roles_data = status.get("roles") or {}
        rows = []
        for role in _ROLES:
            info = roles_data.get(role) or {}
            rows.append({
                "role": role,
                "provider": info.get("provider", "—"),
                "model": info.get("model", "—"),
                "available": bool(info.get("available", False)),
            })

        available_list = status.get("available") or []
        self._avail_lbl.configure(
            text=f"Available providers: {', '.join(available_list) or 'none'}"
        )
        self._render_rows(rows)

    def _update_from_env(self) -> None:
        env = _read_env_model_config()
        profile = (env.get("MODEL_PROFILE") or "offline").upper()
        self._profile_lbl.configure(text=profile)

        rows = []
        for role in _ROLES:
            provider = env.get(f"MODEL_{role.upper()}_PROVIDER") or "ollama"
            model = env.get(f"MODEL_{role.upper()}_NAME") or "—"
            rows.append({"role": role, "provider": provider, "model": model, "available": None})

        self._avail_lbl.configure(text="Available providers: (run health check to test)")
        self._render_rows(rows)

    def _render_rows(self, rows: list) -> None:
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets.clear()

        for i, row in enumerate(rows, start=1):
            r_row = i
            avail = row.get("available")
            if avail is True:
                dot = "●"
                fg = _GREEN
            elif avail is False:
                dot = "✗"
                fg = _RED
            else:
                dot = "○"
                fg = _FG_MUTED

            cells = [
                ttk.Label(self._table_frame, text=row["role"],
                          style="Card.TLabel", font=("Segoe UI", 9)),
                ttk.Label(self._table_frame, text=row["provider"],
                          style="Muted.Card.TLabel", font=("Segoe UI", 9)),
                ttk.Label(self._table_frame, text=row["model"],
                          style="Card.TLabel", font=("Segoe UI", 9)),
                tk.Label(self._table_frame, text=dot, fg=fg,
                         bg=_BG_CARD, font=("Segoe UI", 11)),
            ]
            for col, cell in enumerate(cells):
                cell.grid(row=r_row, column=col, sticky="w", padx=(0, 8), pady=1)
                self._row_widgets.append(cell)

    # ------------------------------------------------------------------
    # Health check (background thread)
    # ------------------------------------------------------------------
    def _run_health_check(self) -> None:
        if self._checking:
            return
        self._checking = True
        self._check_btn.configure(state="disabled")
        self._status_lbl.configure(text="Checking…")
        threading.Thread(target=self._health_worker, daemon=True).start()

    def _health_worker(self) -> None:
        status = None
        try:
            if self._kernel is not None:
                router = getattr(self._kernel, "llm_router", None)
                if router is not None and hasattr(router, "status"):
                    status = router.status(refresh=True)
        except Exception as exc:
            self.after(0, self._status_lbl.configure,
                       {"text": f"Error: {exc}", "foreground": _RED})
        finally:
            if status is not None:
                self.after(0, self._finish_health_check, status)
            else:
                self.after(0, self._finish_health_check_no_kernel)

    def _finish_health_check(self, status: Dict) -> None:
        self._last_status = status
        self._update_from_status(status)
        available = status.get("available") or []
        n = len(available)
        self._status_lbl.configure(
            text=f"{n} provider(s) available",
            foreground=_GREEN if n > 0 else _RED,
        )
        self._check_btn.configure(state="normal")
        self._checking = False

    def _finish_health_check_no_kernel(self) -> None:
        self._status_lbl.configure(
            text="No kernel running — start JAV to test live", foreground=_FG_MUTED
        )
        self._check_btn.configure(state="normal")
        self._checking = False

    # ------------------------------------------------------------------
    # Wizard
    # ------------------------------------------------------------------
    def _open_wizard(self) -> None:
        from interfaces.desktop.model_setup_wizard import ModelSetupWizard

        def on_complete(cfg: dict) -> None:
            self.refresh()

        ModelSetupWizard(
            self.winfo_toplevel(),
            on_complete=on_complete,
            on_cancel=lambda: None,
        )
