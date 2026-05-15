"""interfaces/desktop/model_setup_wizard.py — Model Setup Wizard (V16).

4-step modal wizard for configuring models without editing .env manually:
  1. ProfileStep    — choose a preset profile (offline / balanced / power / code / voice)
  2. CredentialsStep — enter API keys dynamically based on the chosen profile
  3. TestStep        — lightweight provider connectivity check (background thread)
  4. SummaryStep     — review env keys that will be written, then Finish

Usage:
    from interfaces.desktop.model_setup_wizard import ModelSetupWizard
    ModelSetupWizard(root, on_complete=lambda cfg: ..., on_cancel=lambda: ...)
"""
from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

_APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[2]
)

# ── Color palette (GitHub Dark) ──────────────────────────────────────
_BG = "#0d1117"
_BG_CARD = "#161b22"
_BG_HEADER = "#161b22"
_FG = "#e6edf3"
_FG_MUTED = "#8b949e"
_GREEN = "#3fb950"
_RED = "#f85149"
_ORANGE = "#f0883e"
_BLUE = "#1f6feb"
_BORDER = "#30363d"


# ────────────────────────────────────────────────────────────────────
# .env writer (standalone, same logic as FirstLaunchWizard._write_env)
# ────────────────────────────────────────────────────────────────────

def _write_env(env_path: Path, config: Dict[str, str]) -> None:
    existing_lines: List[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    wizard_keys = set(config.keys())
    new_lines: List[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key not in wizard_keys:
            new_lines.append(line)

    if new_lines and new_lines[-1] != "":
        new_lines.append("")
    new_lines.append("# === JAV Model Wizard ===")
    for key, value in sorted(config.items()):
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ────────────────────────────────────────────────────────────────────
# Profile definitions
# ────────────────────────────────────────────────────────────────────

_PROFILES: List[Dict] = [
    {
        "value": "offline",
        "label": "Offline / Local",
        "description": "All models run locally via Ollama. No internet required.",
        "requirements": "Requires Ollama installed and running.",
        "needs_ollama": True,
        "needs_gemini": False,
        "needs_openai": False,
        "needs_anthropic": False,
    },
    {
        "value": "balanced",
        "label": "Balanced",
        "description": "Local Ollama models for most tasks, Gemini for complex reasoning.",
        "requirements": "Requires Ollama + Gemini API key.",
        "needs_ollama": True,
        "needs_gemini": True,
        "needs_openai": False,
        "needs_anthropic": False,
    },
    {
        "value": "power",
        "label": "Cloud Power",
        "description": "Best quality — all roles use cloud APIs (OpenAI, Anthropic).",
        "requirements": "Requires at least one API key (OpenAI or Anthropic).",
        "needs_ollama": False,
        "needs_gemini": False,
        "needs_openai": True,
        "needs_anthropic": True,
    },
    {
        "value": "code",
        "label": "Code Focus",
        "description": "Local Ollama optimised for coding tasks (qwen2.5-coder).",
        "requirements": "Requires Ollama installed and running.",
        "needs_ollama": True,
        "needs_gemini": False,
        "needs_openai": False,
        "needs_anthropic": False,
    },
    {
        "value": "voice_companion",
        "label": "Voice Companion",
        "description": "Fast local models tuned for low-latency voice responses.",
        "requirements": "Requires Ollama installed and running.",
        "needs_ollama": True,
        "needs_gemini": False,
        "needs_openai": False,
        "needs_anthropic": False,
    },
]


# ────────────────────────────────────────────────────────────────────
# Wizard
# ────────────────────────────────────────────────────────────────────

class ModelSetupWizard(tk.Toplevel):
    """Modal 4-step wizard for model configuration."""

    WIDTH = 760
    HEIGHT = 540

    def __init__(
        self,
        master: tk.Misc,
        on_complete: Callable[[Dict[str, str]], None],
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.on_complete = on_complete
        self.on_cancel = on_cancel

        self._collected: Dict[str, str] = {}
        self._current_step = 0
        self._step_widgets: List[tk.Widget] = []

        self._steps = [
            ProfileStep(self),
            CredentialsStep(self),
            TestStep(self),
            SummaryStep(self),
        ]

        self._setup_window()
        self._apply_styles()
        self._build_shell()
        self._show_step(0)
        self.grab_set()

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------
    def _setup_window(self) -> None:
        self.title("JAV — Model Setup Wizard")
        self.resizable(False, False)
        self.configure(bg=_BG)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # Center on master
        self.update_idletasks()
        master = self.master
        if master:
            mx = master.winfo_rootx() + (master.winfo_width() - self.WIDTH) // 2
            my = master.winfo_rooty() + (master.winfo_height() - self.HEIGHT) // 2
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{mx}+{my}")
        else:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{(sw - self.WIDTH)//2}+{(sh - self.HEIGHT)//2}")

    def _apply_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Wiz.TFrame", background=_BG)
        style.configure("WizHeader.TFrame", background=_BG_HEADER)
        style.configure("WizCard.TFrame", background=_BG_CARD)
        style.configure("WizCard.TLabel", background=_BG_CARD, foreground=_FG)
        style.configure("WizCardMuted.TLabel", background=_BG_CARD, foreground=_FG_MUTED)
        style.configure("WizCardSel.TFrame", background="#0d419d")
        style.configure("Wiz.TLabel", background=_BG, foreground=_FG)
        style.configure("WizMuted.TLabel", background=_BG, foreground=_FG_MUTED)
        style.configure("WizTitle.TLabel", background=_BG_HEADER, foreground=_FG,
                        font=("Segoe UI", 14, "bold"))
        style.configure("WizSub.TLabel", background=_BG_HEADER, foreground=_FG_MUTED,
                        font=("Segoe UI", 10))
        style.configure("WizStep.TLabel", background=_BG_HEADER, foreground=_FG_MUTED,
                        font=("Segoe UI", 9))

    # ------------------------------------------------------------------
    # Shell layout
    # ------------------------------------------------------------------
    def _build_shell(self) -> None:
        # Header
        self._header = ttk.Frame(self, style="WizHeader.TFrame", padding=(20, 14))
        self._header.pack(fill=tk.X)
        self._title_lbl = ttk.Label(self._header, text="", style="WizTitle.TLabel")
        self._title_lbl.pack(anchor="w")
        self._sub_lbl = ttk.Label(self._header, text="", style="WizSub.TLabel")
        self._sub_lbl.pack(anchor="w", pady=(2, 0))
        self._step_lbl = ttk.Label(self._header, text="", style="WizStep.TLabel")
        self._step_lbl.pack(anchor="e")

        # Progress bar
        self._progress = ttk.Progressbar(self, orient="horizontal",
                                         maximum=len(self._steps), value=0)
        self._progress.pack(fill=tk.X)

        # Content area
        self._content = ttk.Frame(self, style="Wiz.TFrame", padding=(20, 16))
        self._content.pack(fill=tk.BOTH, expand=True)

        # Navigation buttons
        nav = ttk.Frame(self, style="Wiz.TFrame", padding=(16, 10))
        nav.pack(fill=tk.X, side=tk.BOTTOM)
        self._cancel_btn = ttk.Button(nav, text="Cancel", command=self._cancel)
        self._cancel_btn.pack(side=tk.LEFT)
        self._next_btn = ttk.Button(nav, text="Next →", command=self._next,
                                    style="Accent.TButton")
        self._next_btn.pack(side=tk.RIGHT)
        self._back_btn = ttk.Button(nav, text="← Back", command=self._back)
        self._back_btn.pack(side=tk.RIGHT, padx=(0, 4))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _show_step(self, index: int) -> None:
        step = self._steps[index]
        self._current_step = index

        # Update header
        self._title_lbl.configure(text=step.title)
        self._sub_lbl.configure(text=step.subtitle)
        self._step_lbl.configure(text=f"Step {index + 1} of {len(self._steps)}")
        self._progress.configure(value=index + 1)

        # Rebuild content area
        for w in self._content.winfo_children():
            w.destroy()
        step.build(self._content, self._collected)

        # Button state
        self._back_btn.configure(state="normal" if index > 0 else "disabled")
        is_last = index == len(self._steps) - 1
        self._next_btn.configure(text="Finish" if is_last else "Next →")

    def _next(self) -> None:
        step = self._steps[self._current_step]
        ok, msg = step.is_valid()
        if not ok:
            tk.messagebox.showwarning("Cannot continue", msg, parent=self)
            return
        self._collected.update(step.get_config())

        if self._current_step == len(self._steps) - 1:
            self._finish()
        else:
            self._show_step(self._current_step + 1)

    def _back(self) -> None:
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _cancel(self) -> None:
        self.on_cancel()
        self.destroy()

    def _finish(self) -> None:
        _write_env(_APP_ROOT / ".env", self._collected)
        # Sync env vars into the running process so a refresh() call reflects them
        for k, v in self._collected.items():
            import os
            os.environ[k] = v
        self.on_complete(self._collected)
        self.destroy()


# ────────────────────────────────────────────────────────────────────
# Base step
# ────────────────────────────────────────────────────────────────────

class _WizardStep:
    title: str = ""
    subtitle: str = ""

    def build(self, parent: ttk.Frame, collected: Dict[str, str]) -> None:
        raise NotImplementedError

    def get_config(self) -> Dict[str, str]:
        return {}

    def is_valid(self) -> Tuple[bool, str]:
        return True, ""


# ────────────────────────────────────────────────────────────────────
# Step 1 — Profile
# ────────────────────────────────────────────────────────────────────

class ProfileStep(_WizardStep):
    title = "Choose a Model Profile"
    subtitle = "Select how JAV should connect to AI models."

    def __init__(self, wizard: ModelSetupWizard) -> None:
        self._var: Optional[tk.StringVar] = None
        self._wizard = wizard

    def build(self, parent: ttk.Frame, collected: Dict) -> None:
        self._var = tk.StringVar(value=collected.get("MODEL_PROFILE", "offline"))

        canvas = tk.Canvas(parent, bg=_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, style="Wiz.TFrame")
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        body.bind("<Configure>", lambda _e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        for p in _PROFILES:
            self._make_card(body, p)

    def _make_card(self, parent: ttk.Frame, profile: Dict) -> None:
        value = profile["value"]
        is_sel = self._var.get() == value

        outer = tk.Frame(parent, bg=_BLUE if is_sel else _BG_CARD,
                         padx=1, pady=1)
        outer.pack(fill=tk.X, pady=4)

        card = tk.Frame(outer, bg=_BG_CARD, padx=12, pady=8)
        card.pack(fill=tk.X)

        rb = tk.Radiobutton(
            card, variable=self._var, value=value,
            text=profile["label"],
            bg=_BG_CARD, fg=_FG, selectcolor=_BG_CARD,
            activebackground=_BG_CARD, activeforeground=_FG,
            font=("Segoe UI", 11, "bold"),
            command=lambda p=parent: self._refresh_cards(p),
        )
        rb.pack(anchor="w")

        tk.Label(card, text=profile["description"], bg=_BG_CARD, fg=_FG,
                 font=("Segoe UI", 9), wraplength=580, justify=tk.LEFT).pack(anchor="w")
        tk.Label(card, text=profile["requirements"], bg=_BG_CARD, fg=_FG_MUTED,
                 font=("Segoe UI", 8), wraplength=580).pack(anchor="w")

    def _refresh_cards(self, scroll_parent) -> None:
        # Rebuild cards to reflect selection highlight
        for w in scroll_parent.winfo_children():
            w.destroy()
        for p in _PROFILES:
            self._make_card(scroll_parent, p)

    def get_config(self) -> Dict[str, str]:
        return {"MODEL_PROFILE": self._var.get() if self._var else "offline"}


# ────────────────────────────────────────────────────────────────────
# Step 2 — Credentials
# ────────────────────────────────────────────────────────────────────

class CredentialsStep(_WizardStep):
    title = "Provider Credentials"
    subtitle = "Enter API keys required by your selected profile."

    def __init__(self, wizard: ModelSetupWizard) -> None:
        self._entries: Dict[str, tk.StringVar] = {}
        self._profile: str = "offline"
        self._wizard = wizard

    def build(self, parent: ttk.Frame, collected: Dict) -> None:
        import os
        self._entries.clear()
        self._profile = collected.get("MODEL_PROFILE", "offline")

        profile_def = next((p for p in _PROFILES if p["value"] == self._profile), _PROFILES[0])

        # Ollama host — always shown
        self._add_field(
            parent,
            key="OLLAMA_HOST",
            label="Ollama Host",
            placeholder=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            help_text="URL where Ollama is running (default: http://localhost:11434)",
            secret=False,
        )

        if not (profile_def["needs_gemini"] or profile_def["needs_openai"]
                or profile_def["needs_anthropic"]):
            tk.Label(parent, text="No API keys required for this profile.",
                     bg=_BG, fg=_GREEN, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
            return

        if profile_def["needs_gemini"]:
            self._add_field(
                parent,
                key="GEMINI_API_KEY",
                label="Gemini API Key",
                placeholder=os.environ.get("GEMINI_API_KEY", ""),
                help_text="Get your key at console.cloud.google.com or aistudio.google.com",
                secret=True,
            )

        if profile_def["needs_openai"]:
            self._add_field(
                parent,
                key="OPENAI_API_KEY",
                label="OpenAI API Key",
                placeholder=os.environ.get("OPENAI_API_KEY", ""),
                help_text="Get your key at platform.openai.com/api-keys",
                secret=True,
            )
            self._add_field(
                parent,
                key="OPENAI_BASE_URL",
                label="OpenAI Base URL (optional)",
                placeholder=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                help_text="Leave default unless using LM Studio / vLLM proxy",
                secret=False,
            )

        if profile_def["needs_anthropic"]:
            self._add_field(
                parent,
                key="ANTHROPIC_API_KEY",
                label="Anthropic API Key",
                placeholder=os.environ.get("ANTHROPIC_API_KEY", ""),
                help_text="Get your key at console.anthropic.com",
                secret=True,
            )

        if profile_def["needs_openai"] or profile_def["needs_anthropic"]:
            tk.Label(parent,
                     text="Fill in at least one cloud provider key.",
                     bg=_BG, fg=_FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

    def _add_field(self, parent: ttk.Frame, key: str, label: str,
                   placeholder: str, help_text: str, secret: bool) -> None:
        box = tk.Frame(parent, bg=_BG)
        box.pack(fill=tk.X, pady=(0, 10))

        tk.Label(box, text=label, bg=_BG, fg=_FG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(box, text=help_text, bg=_BG, fg=_FG_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")

        var = tk.StringVar(value=placeholder)
        self._entries[key] = var
        entry = tk.Entry(box, textvariable=var,
                         bg=_BG_CARD, fg=_FG, insertbackground=_FG,
                         relief="flat", font=("Segoe UI", 10), bd=6,
                         show="*" if secret else "")
        entry.pack(fill=tk.X, pady=(2, 0))

    def get_config(self) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for key, var in self._entries.items():
            val = var.get().strip()
            if val:
                result[key] = val
        return result

    def is_valid(self) -> Tuple[bool, str]:
        profile_def = next((p for p in _PROFILES if p["value"] == self._profile), None)
        if profile_def and profile_def.get("needs_openai") and profile_def.get("needs_anthropic"):
            oa = (self._entries.get("OPENAI_API_KEY") or tk.StringVar()).get().strip()
            ant = (self._entries.get("ANTHROPIC_API_KEY") or tk.StringVar()).get().strip()
            if not oa and not ant:
                return False, "The 'power' profile requires at least one API key (OpenAI or Anthropic)."
        return True, ""


# ────────────────────────────────────────────────────────────────────
# Step 3 — Test connectivity
# ────────────────────────────────────────────────────────────────────

class TestStep(_WizardStep):
    title = "Test Connectivity"
    subtitle = "Verifying configured providers before saving."

    def __init__(self, wizard: ModelSetupWizard) -> None:
        self._wizard = wizard
        self._result_frame: Optional[ttk.Frame] = None
        self._retry_btn: Optional[tk.Widget] = None

    def build(self, parent: ttk.Frame, collected: Dict) -> None:
        self._collected = collected
        self._parent = parent

        tk.Label(parent, text="Checking providers…", bg=_BG, fg=_FG_MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))

        self._result_frame = tk.Frame(parent, bg=_BG)
        self._result_frame.pack(fill=tk.X)

        threading.Thread(target=self._run_tests, daemon=True).start()

    def _run_tests(self) -> None:
        results: List[Tuple[str, str, str]] = []  # (name, state, detail)
        collected = self._collected

        ollama_host = collected.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        try:
            import urllib.request
            req = urllib.request.urlopen(f"{ollama_host}/api/tags", timeout=5)
            import json
            data = json.loads(req.read().decode())
            n = len(data.get("models", []))
            results.append(("Ollama", "ok", f"connected — {n} model(s) available"))
        except Exception as exc:
            results.append(("Ollama", "fail", str(exc)[:80]))

        for name, env_key in [
            ("Gemini", "GEMINI_API_KEY"),
            ("OpenAI", "OPENAI_API_KEY"),
            ("Anthropic", "ANTHROPIC_API_KEY"),
        ]:
            val = collected.get(env_key, "").strip()
            if val:
                results.append((name, "key", "API key present (live test skipped — would cost tokens)"))
            else:
                results.append((name, "none", "no key configured"))

        self._parent.after(0, self._show_results, results)

    def _show_results(self, results: List[Tuple[str, str, str]]) -> None:
        for w in self._result_frame.winfo_children():
            w.destroy()

        for name, state, detail in results:
            row = tk.Frame(self._result_frame, bg=_BG)
            row.pack(fill=tk.X, pady=3)

            if state == "ok":
                icon, color = "[OK] ", _GREEN
            elif state == "key":
                icon, color = "[KEY]", _ORANGE
            elif state == "fail":
                icon, color = "[ ✗ ]", _RED
            else:
                icon, color = "[ — ]", _FG_MUTED

            tk.Label(row, text=icon, bg=_BG, fg=color,
                     font=("Consolas", 10, "bold"), width=6, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=f"{name:<10} {detail}", bg=_BG, fg=_FG,
                     font=("Segoe UI", 9), anchor="w").pack(side=tk.LEFT)

    def get_config(self) -> Dict[str, str]:
        return {}


# ────────────────────────────────────────────────────────────────────
# Step 4 — Summary
# ────────────────────────────────────────────────────────────────────

class SummaryStep(_WizardStep):
    title = "Review & Finish"
    subtitle = "The following settings will be written to your .env file."

    def __init__(self, wizard: ModelSetupWizard) -> None:
        self._wizard = wizard

    def build(self, parent: ttk.Frame, collected: Dict) -> None:
        tk.Label(parent,
                 text="Review the settings below, then click Finish to save.",
                 bg=_BG, fg=_FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 10))

        box = tk.Frame(parent, bg=_BG_CARD, padx=12, pady=10)
        box.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(box, bg=_BG_CARD, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=_BG_CARD)
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        body.bind("<Configure>", lambda _e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        secret_keys = {"GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                       "OPENAI_SECRET", "LLAMACPP_API_KEY"}

        for key in sorted(collected.keys()):
            value = collected[key]
            display = (value[:4] + "●" * 6) if key in secret_keys and len(value) > 4 else value

            row = tk.Frame(body, bg=_BG_CARD)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=f"{key:<30}", bg=_BG_CARD, fg=_FG_MUTED,
                     font=("Consolas", 9), anchor="w", width=32).pack(side=tk.LEFT)
            tk.Label(row, text=f"= {display}", bg=_BG_CARD, fg=_FG,
                     font=("Consolas", 9), anchor="w").pack(side=tk.LEFT)

        if not collected:
            tk.Label(body, text="(no settings collected — nothing to write)",
                     bg=_BG_CARD, fg=_FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w")

        tk.Label(parent,
                 text=f"Will write to: {_APP_ROOT / '.env'}",
                 bg=_BG, fg=_FG_MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))
