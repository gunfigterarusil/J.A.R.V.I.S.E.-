"""interfaces/desktop/model_setup_wizard.py — V16 Model Setup Wizard 2.0.

A resizable, scrollable wizard for configuring JAV model roles without manually
editing .env. It supports Offline / Low RAM / Hybrid / Cloud / Code / Voice
profiles, Ollama discovery, role assignment, API-key configuration, and a final
pull-command summary.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Tuple

from scripts.model_setup import (
    DEFAULT_PROFILE_MODELS,
    ROLES,
    list_ollama_models,
    model_matches,
    ollama_pull_commands,
)

_APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]

_BG = "#0d1117"
_CARD = "#161b22"
_CARD2 = "#1c2128"
_TEXT = "#e6edf3"
_MUTED = "#8b949e"
_BLUE = "#1f6feb"
_GREEN = "#3fb950"
_RED = "#f85149"
_ORANGE = "#f0883e"
_BORDER = "#30363d"

PROVIDER_CHOICES = ["ollama", "openai", "gemini", "anthropic", "llamacpp", "null"]

PROFILE_INFO = {
    "offline": ("Offline", "All core roles use local Ollama models. Best privacy, no cloud tokens."),
    "low_ram": ("Low RAM", "Smaller Ollama models for laptops / weak PCs."),
    "hybrid": ("Hybrid", "Local fast/code/action roles + cloud reasoning/vision."),
    "cloud": ("Cloud", "Use cloud APIs for most roles. Best quality if API keys are available."),
    "code": ("Code Focus", "Coder models for repair/debugging-heavy workflows."),
    "voice_companion": ("Voice Companion", "Lower latency local profile for voice-first usage."),
    "custom": ("Custom", "Keep/edit your own role assignments manually."),
}


def _env_path() -> Path:
    return _APP_ROOT / ".env"


def _read_env() -> Dict[str, str]:
    result: Dict[str, str] = {}
    path = _env_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            result[k.strip()] = v.strip()
    for k, v in os.environ.items():
        if k.startswith("MODEL_") or k in {"OLLAMA_HOST", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "LLAMACPP_HOST"}:
            result[k] = v
    return result


def _write_env(updates: Dict[str, str]) -> None:
    path = _env_path()
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    update_keys = set(updates)
    kept: List[str] = []
    for line in existing:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.split("=", 1)[0].strip()
            if key in update_keys:
                continue
        kept.append(line)
    if kept and kept[-1] != "":
        kept.append("")
    kept.append("# === JAV V16 Model Setup Wizard ===")
    for key in sorted(updates):
        kept.append(f"{key}={updates[key]}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    for k, v in updates.items():
        os.environ[k] = v


class ScrollFrame(ttk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, bg=_BG, highlightthickness=0)
        self.body = ttk.Frame(self.canvas, style="Wiz.TFrame")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))


class ModelSetupWizard(tk.Toplevel):
    WIDTH = 980
    HEIGHT = 720

    def __init__(self, master: tk.Misc, on_complete: Callable[[Dict[str, str]], None], on_cancel: Callable[[], None]) -> None:
        super().__init__(master)
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.env = _read_env()
        self.collected: Dict[str, str] = {}
        self.step_index = 0
        self.steps = [
            ("Profile", self._build_profile_step),
            ("Roles", self._build_roles_step),
            ("Providers", self._build_provider_step),
            ("Test", self._build_test_step),
            ("Finish", self._build_finish_step),
        ]
        self.profile_var = tk.StringVar(value=self.env.get("MODEL_PROFILE", "offline") or "offline")
        self.ollama_host_var = tk.StringVar(value=self.env.get("OLLAMA_HOST", "http://localhost:11434") or "http://localhost:11434")
        self.role_provider_vars: Dict[str, tk.StringVar] = {}
        self.role_model_vars: Dict[str, tk.StringVar] = {}
        self.key_vars: Dict[str, tk.StringVar] = {
            "GEMINI_API_KEY": tk.StringVar(value=self.env.get("GEMINI_API_KEY", "")),
            "OPENAI_API_KEY": tk.StringVar(value=self.env.get("OPENAI_API_KEY", "")),
            "OPENAI_BASE_URL": tk.StringVar(value=self.env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")),
            "ANTHROPIC_API_KEY": tk.StringVar(value=self.env.get("ANTHROPIC_API_KEY", "")),
            "LLAMACPP_HOST": tk.StringVar(value=self.env.get("LLAMACPP_HOST", "http://localhost:8080")),
        }
        self.ollama_models: List[str] = []
        self.ollama_error = ""
        self.report_text: tk.Text | None = None
        self._setup_window()
        self._styles()
        self._build_shell()
        self._show_step(0)
        self.grab_set()

    def _setup_window(self) -> None:
        self.title("JAV — Model Setup Wizard 2.0")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(860, 560)
        self.resizable(True, True)
        self.configure(bg=_BG)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Wiz.TFrame", background=_BG)
        style.configure("WizCard.TFrame", background=_CARD)
        style.configure("Wiz.TLabel", background=_BG, foreground=_TEXT)
        style.configure("WizMuted.TLabel", background=_BG, foreground=_MUTED)
        style.configure("Card.TLabel", background=_CARD, foreground=_TEXT)
        style.configure("Muted.Card.TLabel", background=_CARD, foreground=_MUTED)
        style.configure("Title.TLabel", background=_BG, foreground=_TEXT, font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", background=_BG, foreground=_MUTED, font=("Segoe UI", 10))

    def _build_shell(self) -> None:
        header = ttk.Frame(self, style="Wiz.TFrame", padding=(18, 12))
        header.pack(fill=tk.X)
        self.title_lbl = ttk.Label(header, text="", style="Title.TLabel")
        self.title_lbl.pack(anchor="w")
        self.sub_lbl = ttk.Label(header, text="", style="Sub.TLabel")
        self.sub_lbl.pack(anchor="w", pady=(2, 0))
        self.progress = ttk.Progressbar(self, maximum=len(self.steps))
        self.progress.pack(fill=tk.X)
        self.content = ScrollFrame(self)
        self.content.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)
        nav = ttk.Frame(self, style="Wiz.TFrame", padding=(14, 10))
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="Cancel", command=self._cancel).pack(side=tk.LEFT)
        self.back_btn = ttk.Button(nav, text="← Back", command=self._back)
        self.back_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self.next_btn = ttk.Button(nav, text="Next →", command=self._next)
        self.next_btn.pack(side=tk.RIGHT)

    def _clear(self) -> None:
        for w in self.content.body.winfo_children():
            w.destroy()

    def _show_step(self, index: int) -> None:
        self.step_index = index
        name, builder = self.steps[index]
        self.title_lbl.configure(text=f"Step {index + 1}: {name}")
        self.sub_lbl.configure(text="Configure model roles and providers without editing .env manually.")
        self.progress.configure(value=index + 1)
        self._clear()
        builder(self.content.body)
        self.back_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(text="Finish" if index == len(self.steps) - 1 else "Next →")
        self.content.canvas.yview_moveto(0)

    def _next(self) -> None:
        if self.step_index == len(self.steps) - 1:
            self._finish()
            return
        self._show_step(self.step_index + 1)

    def _back(self) -> None:
        if self.step_index > 0:
            self._show_step(self.step_index - 1)

    def _cancel(self) -> None:
        self.on_cancel()
        self.destroy()

    def _label(self, parent, text: str, muted: bool = False, **kw):
        return ttk.Label(parent, text=text, style="WizMuted.TLabel" if muted else "Wiz.TLabel", **kw)

    def _card(self, parent, title: str, desc: str = ""):
        card = ttk.Frame(parent, style="WizCard.TFrame", padding=12)
        card.pack(fill=tk.X, pady=6)
        ttk.Label(card, text=title, style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        if desc:
            ttk.Label(card, text=desc, style="Muted.Card.TLabel", wraplength=820).pack(anchor="w", pady=(2, 8))
        return card

    def _build_profile_step(self, parent) -> None:
        self._label(parent, "Choose the profile that matches your hardware/API setup.", True).pack(anchor="w", pady=(0, 8))
        for value, (title, desc) in PROFILE_INFO.items():
            card = self._card(parent, title, desc)
            rb = tk.Radiobutton(card, variable=self.profile_var, value=value, text=value,
                                bg=_CARD, fg=_TEXT, selectcolor=_CARD2, activebackground=_CARD,
                                activeforeground=_TEXT, command=self._apply_profile_defaults)
            rb.pack(anchor="w")
        ttk.Button(parent, text="Apply profile defaults to role table", command=self._apply_profile_defaults).pack(anchor="w", pady=8)

    def _apply_profile_defaults(self) -> None:
        profile = self.profile_var.get().strip().lower()
        spec = DEFAULT_PROFILE_MODELS.get(profile, DEFAULT_PROFILE_MODELS.get("offline", {}))
        for role in ROLES:
            provider, model = spec.get(role, ("ollama", ""))
            self.role_provider_vars.setdefault(role, tk.StringVar()).set(provider)
            self.role_model_vars.setdefault(role, tk.StringVar()).set(model)

    def _ensure_role_vars(self) -> None:
        if self.role_provider_vars and self.role_model_vars:
            return
        profile = self.profile_var.get().strip().lower()
        spec = DEFAULT_PROFILE_MODELS.get(profile, DEFAULT_PROFILE_MODELS.get("offline", {}))
        for role in ROLES:
            p_env = self.env.get(f"MODEL_{role.upper()}_PROVIDER", "").strip()
            m_env = self.env.get(f"MODEL_{role.upper()}_NAME", "").strip()
            p_def, m_def = spec.get(role, ("ollama", ""))
            self.role_provider_vars[role] = tk.StringVar(value=p_env or p_def)
            self.role_model_vars[role] = tk.StringVar(value=m_env or m_def)

    def _build_roles_step(self, parent) -> None:
        self._ensure_role_vars()
        self._label(parent, "Assign a provider/model for each cognitive role. You can leave vision/embedding as Ollama defaults for now.", True).pack(anchor="w")
        card = self._card(parent, "Role assignment", "Fast = chat, Reason = deeper analysis, Code = repair, Action = task/GUI planning.")
        header = ttk.Frame(card, style="WizCard.TFrame")
        header.pack(fill=tk.X)
        for text, width in [("Role", 12), ("Provider", 16), ("Model", 34), ("Installed", 12)]:
            ttk.Label(header, text=text, style="Muted.Card.TLabel", width=width, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.installed_labels: Dict[str, ttk.Label] = {}
        for role in ROLES:
            row = ttk.Frame(card, style="WizCard.TFrame")
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=role, style="Card.TLabel", width=12).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Combobox(row, textvariable=self.role_provider_vars[role], values=PROVIDER_CHOICES, width=14, state="readonly").pack(side=tk.LEFT, padx=(0, 6))
            cb = ttk.Combobox(row, textvariable=self.role_model_vars[role], values=self.ollama_models, width=34)
            cb.pack(side=tk.LEFT, padx=(0, 6), fill=tk.X, expand=True)
            lbl = ttk.Label(row, text="—", style="Muted.Card.TLabel", width=22)
            lbl.pack(side=tk.LEFT)
            self.installed_labels[role] = lbl
        btns = ttk.Frame(parent, style="Wiz.TFrame")
        btns.pack(fill=tk.X, pady=8)
        ttk.Button(btns, text="Detect Ollama models", command=self._detect_ollama).pack(side=tk.LEFT)
        ttk.Button(btns, text="Copy missing ollama pull commands", command=self._copy_pull_commands).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="Reset to profile defaults", command=lambda: (self._apply_profile_defaults(), self._show_step(self.step_index))).pack(side=tk.LEFT)
        self._detect_ollama(update_labels=True)

    def _detect_ollama(self, update_labels: bool = True) -> None:
        ok, models, err = list_ollama_models(self.ollama_host_var.get())
        self.ollama_models = models
        self.ollama_error = err
        if update_labels and hasattr(self, "installed_labels"):
            for role in ROLES:
                provider = self.role_provider_vars[role].get().strip().lower()
                model = self.role_model_vars[role].get().strip()
                lbl = self.installed_labels[role]
                if provider != "ollama":
                    lbl.configure(text="cloud/API", foreground=_MUTED)
                elif not ok:
                    lbl.configure(text="Ollama offline", foreground=_ORANGE)
                elif model_matches(model, models):
                    lbl.configure(text="installed", foreground=_GREEN)
                else:
                    lbl.configure(text="missing", foreground=_RED)

    def _role_config(self) -> Dict[str, Tuple[str, str]]:
        self._ensure_role_vars()
        return {role: (self.role_provider_vars[role].get().strip().lower(), self.role_model_vars[role].get().strip()) for role in ROLES}

    def _copy_pull_commands(self) -> None:
        self._detect_ollama(update_labels=True)
        cmds = ollama_pull_commands(self._role_config(), self.ollama_models)
        text = "\n".join(cmds) if cmds else "# All configured Ollama models appear to be installed."
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Missing model commands copied to clipboard.", parent=self)

    def _build_provider_step(self, parent) -> None:
        self._label(parent, "Configure provider endpoints and API keys. Keys are saved in .env next to the app.", True).pack(anchor="w")
        card = self._card(parent, "Local Ollama", "Used for offline/local profiles. Install Ollama separately; JAV only configures the connection.")
        self._entry(card, "OLLAMA_HOST", self.ollama_host_var, secret=False)
        cloud = self._card(parent, "Cloud/API providers", "Only fill providers you want to use. Live API tests are skipped here to avoid token costs.")
        self._entry(cloud, "GEMINI_API_KEY", self.key_vars["GEMINI_API_KEY"], secret=True)
        self._entry(cloud, "OPENAI_API_KEY", self.key_vars["OPENAI_API_KEY"], secret=True)
        self._entry(cloud, "OPENAI_BASE_URL", self.key_vars["OPENAI_BASE_URL"], secret=False)
        self._entry(cloud, "ANTHROPIC_API_KEY", self.key_vars["ANTHROPIC_API_KEY"], secret=True)
        local = self._card(parent, "llama.cpp server", "Optional local HTTP server compatible with llama.cpp.")
        self._entry(local, "LLAMACPP_HOST", self.key_vars["LLAMACPP_HOST"], secret=False)

    def _entry(self, parent, label: str, var: tk.StringVar, secret: bool = False) -> None:
        ttk.Label(parent, text=label, style="Muted.Card.TLabel").pack(anchor="w", pady=(6, 0))
        e = tk.Entry(parent, textvariable=var, bg=_CARD2, fg=_TEXT, insertbackground=_TEXT, relief=tk.FLAT, bd=7, show="*" if secret else "")
        e.pack(fill=tk.X)

    def _build_test_step(self, parent) -> None:
        self._label(parent, "This checks local Ollama availability and whether configured local models are pulled. Cloud keys are checked only for presence.", True).pack(anchor="w", pady=(0, 8))
        ttk.Button(parent, text="Run model setup check", command=self._run_report).pack(anchor="w")
        self.report_text = tk.Text(parent, height=26, bg=_CARD, fg=_TEXT, insertbackground=_TEXT, relief=tk.FLAT, wrap=tk.WORD)
        self.report_text.pack(fill=tk.BOTH, expand=True, pady=8)
        self._run_report()

    def _run_report(self) -> None:
        self._detect_ollama(update_labels=False)
        env = self._collect_updates()
        roles = self._role_config()
        lines = ["Model Setup Check", "=" * 22, f"Profile: {env.get('MODEL_PROFILE')}", f"Ollama host: {env.get('OLLAMA_HOST')}"]
        if self.ollama_error:
            lines.append(f"Ollama: WARN — {self.ollama_error}")
        else:
            lines.append(f"Ollama: OK — {len(self.ollama_models)} installed model(s)")
        lines.append("")
        for role, (provider, model) in roles.items():
            if provider == "ollama":
                ok = model_matches(model, self.ollama_models)
                lines.append(f"{role:<9} {provider}/{model:<28} {'OK' if ok else 'MISSING'}")
            elif provider in {"gemini", "openai", "anthropic"}:
                key_map = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
                present = bool(env.get(key_map[provider], "").strip())
                lines.append(f"{role:<9} {provider}/{model:<28} {'KEY OK' if present else 'MISSING KEY'}")
            else:
                lines.append(f"{role:<9} {provider}/{model:<28} configured")
        cmds = ollama_pull_commands(roles, self.ollama_models)
        if cmds:
            lines += ["", "Missing Ollama models — run:"] + [f"  {c}" for c in cmds]
        if self.report_text:
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert("1.0", "\n".join(lines))

    def _build_finish_step(self, parent) -> None:
        env = self._collect_updates()
        self._label(parent, "Review settings. Click Finish to save to .env.", True).pack(anchor="w", pady=(0, 8))
        box = tk.Text(parent, height=28, bg=_CARD, fg=_TEXT, relief=tk.FLAT, wrap=tk.NONE)
        box.pack(fill=tk.BOTH, expand=True)
        secret_keys = {"GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        for key in sorted(env):
            value = env[key]
            shown = (value[:4] + "******") if key in secret_keys and len(value) > 4 else value
            box.insert(tk.END, f"{key}={shown}\n")
        box.configure(state="disabled")
        self._label(parent, f"Will write to: {_env_path()}", True).pack(anchor="w", pady=8)

    def _collect_updates(self) -> Dict[str, str]:
        self._ensure_role_vars()
        result: Dict[str, str] = {"MODEL_PROFILE": self.profile_var.get().strip().lower() or "offline", "OLLAMA_HOST": self.ollama_host_var.get().strip() or "http://localhost:11434"}
        for role in ROLES:
            result[f"MODEL_{role.upper()}_PROVIDER"] = self.role_provider_vars[role].get().strip().lower() or "null"
            result[f"MODEL_{role.upper()}_NAME"] = self.role_model_vars[role].get().strip()
        for key, var in self.key_vars.items():
            val = var.get().strip()
            if val:
                result[key] = val
        return result

    def _finish(self) -> None:
        updates = self._collect_updates()
        _write_env(updates)
        self.on_complete(updates)
        messagebox.showinfo("Saved", "Model profile saved. Refresh model status or restart JAV if needed.", parent=self)
        self.destroy()
