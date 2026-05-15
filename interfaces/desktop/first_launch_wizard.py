"""interfaces/desktop/first_launch_wizard.py — First-launch setup wizard.

V15.5: Shown on first run (before the main desktop UI) to guide the user
through storage mode, workspace, model selection, dependency checks,
and an optional voice test.

Writes collected settings to .env via settings_window.save_env() and
creates a .jav_setup_complete sentinel file on finish.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from abc import ABC, abstractmethod
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

# Locate app root (same logic as config.py)
_APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[2]
)


def _as_portable_path(path: str | Path) -> str:
    """Return a stable portable-relative path when the folder is inside app root."""
    try:
        resolved = Path(path).expanduser().resolve()
        rel = resolved.relative_to(_APP_ROOT.resolve())
        return rel.as_posix()
    except Exception:
        return str(path)


def _ensure_setup_folders(config: Dict[str, str]) -> None:
    """Create folders selected by the wizard so the first desktop boot is clean."""
    for key in ("JARVIS_DATA_DIR", "ACTION_WORKSPACE_PATH", "SCREENSHOT_DIR"):
        value = (config.get(key) or "").strip()
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = _APP_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
    data_dir = (config.get("JARVIS_DATA_DIR") or "data/brain").strip()
    data_path = Path(data_dir).expanduser()
    if not data_path.is_absolute():
        data_path = _APP_ROOT / data_path
    (data_path / "logs").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Base step
# ---------------------------------------------------------------------------

class WizardStep(ABC):
    title: str = "Step"
    subtitle: str = ""
    skippable: bool = False

    @abstractmethod
    def build(self, parent: ttk.Frame) -> None:
        """Build the step's widgets inside parent."""

    def get_config(self) -> Dict[str, str]:
        """Return {ENV_KEY: value} dict of settings collected by this step."""
        return {}

    def is_valid(self) -> tuple[bool, str]:
        """Return (ok, error_message). Called before advancing."""
        return True, ""


# ---------------------------------------------------------------------------
# Step 1 — Welcome
# ---------------------------------------------------------------------------

class WelcomeStep(WizardStep):
    title = "Welcome to JAV"
    subtitle = "Your personal AI assistant"

    def build(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="JAV — Just Another Virtual assistant",
                  font=("Segoe UI", 14, "bold")).pack(pady=(20, 8))
        ttk.Label(
            parent,
            text=(
                "This wizard will help you set up JAV for the first time.\n\n"
                "We will:\n"
                "  1.  Choose where to store your memory\n"
                "  2.  Choose your workspace folder\n"
                "  3.  Select a model mode\n"
                "  4.  Check your dependencies\n"
                "  5.  Test voice (optional)\n\n"
                "You can change any setting later in Settings Center."
            ),
            justify=tk.LEFT,
            wraplength=600,
        ).pack(padx=20)


# ---------------------------------------------------------------------------
# Step 2 — Storage mode
# ---------------------------------------------------------------------------

class StorageModeStep(WizardStep):
    title = "Memory Storage"
    subtitle = "Choose where JAV keeps its memory"

    def __init__(self) -> None:
        self._mode_var: Optional[tk.StringVar] = None
        self._custom_path_var: Optional[tk.StringVar] = None
        self._preview_lbl: Optional[ttk.Label] = None

    def build(self, parent: ttk.Frame) -> None:
        self._mode_var = tk.StringVar(value="portable")
        self._custom_path_var = tk.StringVar(value="")

        ttk.Label(parent, text="Where should JAV store its memory?",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(16, 8))

        modes = [
            ("portable", "Portable mode  (data/brain  — next to this app)",
             "Perfect for USB drives. The whole folder can be moved."),
            ("installed", "Installed mode  (~/.jarvis_brain)",
             "Stored in your home directory. Better for a fixed PC."),
            ("custom", "Custom folder…", "Pick any folder on your computer."),
        ]
        for value, label, hint in modes:
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=20, pady=2)
            rb = ttk.Radiobutton(frame, text=label, variable=self._mode_var,
                                 value=value, command=self._on_mode_change)
            rb.pack(anchor="w")
            ttk.Label(frame, text=f"    {hint}", foreground="#8b949e").pack(anchor="w")

        self._custom_frame = ttk.Frame(parent)
        self._custom_frame.pack(fill=tk.X, padx=20, pady=(4, 0))
        ttk.Label(self._custom_frame, text="Folder:").pack(side=tk.LEFT)
        self._path_entry = ttk.Entry(self._custom_frame, textvariable=self._custom_path_var,
                                     width=40)
        self._path_entry.pack(side=tk.LEFT, padx=(6, 4))
        ttk.Button(self._custom_frame, text="Browse…",
                   command=self._browse).pack(side=tk.LEFT)
        self._custom_frame.pack_forget()

        self._preview_lbl = ttk.Label(parent, text="", foreground="#8b949e",
                                      font=("Segoe UI", 9))
        self._preview_lbl.pack(anchor="w", padx=20, pady=(8, 0))
        self._on_mode_change()

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get() if self._mode_var else "portable"
        if mode == "custom":
            self._custom_frame.pack(fill=tk.X, padx=20, pady=(4, 0))
        else:
            self._custom_frame.pack_forget()
        self._update_preview()

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Choose memory folder")
        if folder and self._custom_path_var:
            self._custom_path_var.set(folder)
            self._update_preview()

    def _update_preview(self) -> None:
        if not self._preview_lbl or not self._mode_var:
            return
        path = self._resolved_path()
        self._preview_lbl.configure(text=f"Memory will be stored at:\n  {path}")

    def _resolved_path(self) -> str:
        mode = self._mode_var.get() if self._mode_var else "portable"
        if mode == "portable":
            return str((_APP_ROOT / "data" / "brain").resolve())
        if mode == "installed":
            return str(Path("~/.jarvis_brain").expanduser())
        custom = (self._custom_path_var.get() or "").strip()
        return custom or str((_APP_ROOT / "data" / "brain").resolve())

    def get_config(self) -> Dict[str, str]:
        mode = self._mode_var.get() if self._mode_var else "portable"
        cfg: Dict[str, str] = {}
        if mode == "portable":
            cfg["JAV_PORTABLE"] = "true"
            cfg["JARVIS_DATA_DIR"] = "data/brain"
            cfg["SCREENSHOT_DIR"] = "data/screenshots"
        elif mode == "installed":
            cfg["JAV_PORTABLE"] = "false"
            cfg["JARVIS_DATA_DIR"] = "~/.jarvis_brain"
            cfg["SCREENSHOT_DIR"] = "~/.jarvis_brain/screenshots"
        else:
            cfg["JAV_PORTABLE"] = "false"
            cfg["JARVIS_DATA_DIR"] = self._resolved_path()
            cfg["SCREENSHOT_DIR"] = str(Path(self._resolved_path()).expanduser() / "screenshots")
        cfg["JAV_SETUP_COMPLETE"] = "true"
        return cfg

    def is_valid(self) -> tuple[bool, str]:
        mode = self._mode_var.get() if self._mode_var else "portable"
        if mode == "custom":
            custom = (self._custom_path_var.get() or "").strip()
            if not custom:
                return False, "Please select or enter a memory folder path."
        return True, ""


# ---------------------------------------------------------------------------
# Step 3 — Workspace
# ---------------------------------------------------------------------------

class WorkspaceStep(WizardStep):
    title = "Workspace"
    subtitle = "Where JAV will read and write your project files"

    def __init__(self) -> None:
        self._path_var: Optional[tk.StringVar] = None

    def build(self, parent: ttk.Frame) -> None:
        default_ws = str((_APP_ROOT / "data" / "workspace").resolve())
        self._path_var = tk.StringVar(value=default_ws)

        ttk.Label(parent, text="Workspace folder:",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(16, 8))
        ttk.Label(
            parent,
            text=(
                "JAV will read and write files here when you ask it to work on projects.\n"
                "Choose a folder you have write access to."
            ),
            foreground="#8b949e",
            wraplength=600,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=20, pady=(0, 10))

        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=20)
        self._entry = ttk.Entry(row, textvariable=self._path_var, width=52)
        self._entry.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="Browse…", command=self._browse).pack(side=tk.LEFT)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Choose workspace folder")
        if folder and self._path_var:
            self._path_var.set(folder)

    def get_config(self) -> Dict[str, str]:
        path = (self._path_var.get() or "").strip()
        path = path or str((_APP_ROOT / "data" / "workspace").resolve())
        return {"ACTION_WORKSPACE_PATH": _as_portable_path(path)}


# ---------------------------------------------------------------------------
# Step 4 — Model mode
# ---------------------------------------------------------------------------

class ModelModeStep(WizardStep):
    title = "Model Mode"
    subtitle = "How should JAV connect to AI models?"

    def __init__(self) -> None:
        self._mode_var: Optional[tk.StringVar] = None

    def build(self, parent: ttk.Frame) -> None:
        self._mode_var = tk.StringVar(value="offline")

        ttk.Label(parent, text="Select a model mode:",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(16, 8))

        profiles = [
            ("offline", "Offline  (Ollama + local models)",
             "No internet needed. Requires Ollama installed locally."),
            ("balanced", "Balanced  (Ollama primary, cloud fallback)",
             "Uses local models first, falls back to cloud if needed."),
            ("power", "Cloud  (OpenAI / Gemini / Anthropic)",
             "Best quality. Requires API keys in .env."),
            ("voice_companion", "Voice Companion",
             "Optimised for fast responses in voice mode."),
        ]
        for value, label, hint in profiles:
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=20, pady=3)
            ttk.Radiobutton(frame, text=label, variable=self._mode_var,
                            value=value).pack(anchor="w")
            ttk.Label(frame, text=f"    {hint}", foreground="#8b949e").pack(anchor="w")

        ttk.Label(
            parent,
            text="You can change this and assign models to roles in Settings → Model Profiles.",
            foreground="#8b949e",
            wraplength=600,
        ).pack(anchor="w", padx=20, pady=(12, 0))

    def get_config(self) -> Dict[str, str]:
        return {"MODEL_PROFILE": self._mode_var.get() if self._mode_var else "offline"}


# ---------------------------------------------------------------------------
# Step 5 — Dependency check
# ---------------------------------------------------------------------------

class DependencyCheckStep(WizardStep):
    title = "Dependency Check"
    subtitle = "Verifying your installation"
    skippable = True

    def __init__(self) -> None:
        self._checks: List = []
        self._canvas: Optional[tk.Canvas] = None
        self._status_lbl: Optional[ttk.Label] = None

    def build(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=20, pady=(12, 8))
        ttk.Label(header, text="Checking your installation…",
                  font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self._status_lbl = ttk.Label(header, text="", foreground="#8b949e")
        self._status_lbl.pack(side=tk.LEFT, padx=(10, 0))

        self._results_frame = ttk.Frame(parent)
        self._results_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        self._placeholder = ttk.Label(self._results_frame,
                                      text="Checking…", foreground="#8b949e")
        self._placeholder.pack(pady=10)

        # Start checks after a short delay so UI renders first
        parent.after(300, self._start)

    def _start(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            from scripts.doctor import run_checks
            checks = run_checks()
        except Exception as exc:
            checks = []
        self._checks = checks
        # Use winfo_exists to avoid errors if wizard was closed
        try:
            self._results_frame.after(0, self._show_results, checks)
        except Exception:
            pass

    def _show_results(self, checks: list) -> None:
        for w in self._results_frame.winfo_children():
            w.destroy()

        if not checks:
            ttk.Label(self._results_frame, text="Could not run checks.",
                      foreground="#f85149").pack()
            return

        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        color = "#3fb950" if passed == total else "#f0883e"
        if self._status_lbl:
            self._status_lbl.configure(text=f"{passed}/{total} passed", foreground=color)

        canvas = tk.Canvas(self._results_frame, highlightthickness=0,
                           bg=self._results_frame.cget("background"), height=260)
        sb = ttk.Scrollbar(self._results_frame, orient="vertical",
                           command=canvas.yview)
        body = ttk.Frame(canvas)
        cw = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)

        def _on_cfg(e: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(cw, width=e.width)

        canvas.bind("<Configure>", _on_cfg)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for chk in checks:
            row = ttk.Frame(body)
            row.pack(fill=tk.X, pady=1)
            icon = "✓" if chk.passed else "✗"
            clr = "#3fb950" if chk.passed else "#f85149"
            ttk.Label(row, text=icon, foreground=clr, width=3,
                      font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
            ttk.Label(row, text=chk.name, width=30, anchor="w").pack(side=tk.LEFT)
            if chk.detail and not chk.passed:
                ttk.Label(row, text=chk.detail[:60], foreground="#8b949e",
                          anchor="w").pack(side=tk.LEFT, padx=(4, 0))
            if chk.fixable and chk.fix_cmd and not chk.passed:
                ttk.Button(
                    row, text="Fix",
                    command=lambda cmd=chk.fix_cmd: self._repair(cmd),
                ).pack(side=tk.RIGHT, padx=4)

    def _repair(self, cmd: str) -> None:
        import shlex
        parts = shlex.split(cmd)
        if parts and parts[0] == "pip":
            parts = [sys.executable, "-m"] + parts
        try:
            subprocess.Popen(parts)
            messagebox.showinfo("Repair",
                f"Running: {' '.join(parts)}\n"
                "Restart JAV after installation completes.")
        except Exception as exc:
            messagebox.showerror("Repair failed", str(exc))


# ---------------------------------------------------------------------------
# Step 6 — Voice test (optional)
# ---------------------------------------------------------------------------

class VoiceTestStep(WizardStep):
    title = "Voice Test"
    subtitle = "Test your microphone and text-to-speech (optional)"
    skippable = True

    def build(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Test your voice setup:",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(16, 8))
        ttk.Label(
            parent,
            text="This step is optional. You can set up voice later in Settings → Voice.",
            foreground="#8b949e",
            wraplength=600,
        ).pack(anchor="w", padx=20, pady=(0, 14))

        mic_frame = ttk.LabelFrame(parent, text="Microphone", padding=10)
        mic_frame.pack(fill=tk.X, padx=20, pady=4)
        self._mic_lbl = ttk.Label(mic_frame, text="Not tested yet")
        self._mic_lbl.pack(side=tk.LEFT)
        ttk.Button(mic_frame, text="Test mic (2 s)",
                   command=self._test_mic).pack(side=tk.RIGHT)

        tts_frame = ttk.LabelFrame(parent, text="Text-to-Speech", padding=10)
        tts_frame.pack(fill=tk.X, padx=20, pady=4)
        self._tts_lbl = ttk.Label(tts_frame, text="Not tested yet")
        self._tts_lbl.pack(side=tk.LEFT)
        ttk.Button(tts_frame, text="Test TTS",
                   command=self._test_tts).pack(side=tk.RIGHT)

    def _test_mic(self) -> None:
        self._mic_lbl.configure(text="Recording 2 seconds…")
        threading.Thread(target=self._mic_worker, daemon=True).start()

    def _mic_worker(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
            data = sd.rec(int(2 * 16000), samplerate=16000, channels=1,
                          dtype="float32", blocking=True)
            level = float(np.abs(data).mean())
            result = f"OK — level={level:.4f}" if level > 0.001 else "Recorded but very quiet"
        except Exception as exc:
            result = f"Error: {exc}"
        self._mic_lbl.after(0, self._mic_lbl.configure, {"text": result})

    def _test_tts(self) -> None:
        self._tts_lbl.configure(text="Speaking…")
        threading.Thread(target=self._tts_worker, daemon=True).start()

    def _tts_worker(self) -> None:
        result = "OK"
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say("JAV is ready")
            engine.runAndWait()
        except Exception as exc:
            result = f"pyttsx3 error: {exc}"
        self._tts_lbl.after(0, self._tts_lbl.configure, {"text": result})


# ---------------------------------------------------------------------------
# Step 7 — Summary
# ---------------------------------------------------------------------------

class SummaryStep(WizardStep):
    title = "All Set!"
    subtitle = "Review your configuration"

    def __init__(self) -> None:
        self._collected: Dict[str, str] = {}

    def set_collected(self, config: Dict[str, str]) -> None:
        self._collected = config

    def build(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="JAV is ready to start.",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(16, 4))
        ttk.Label(
            parent,
            text="Here is what will be written to your .env file:",
            foreground="#8b949e",
        ).pack(anchor="w", padx=20, pady=(0, 10))

        text = tk.Text(parent, height=12, state=tk.DISABLED,
                       font=("Consolas", 9),
                       bg="#0d1117", fg="#e6edf3",
                       relief=tk.FLAT, padx=8, pady=8)
        text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        text.configure(state=tk.NORMAL)
        for key, value in sorted(self._collected.items()):
            text.insert(tk.END, f"{key}={value}\n")
        text.configure(state=tk.DISABLED)

        ttk.Label(
            parent,
            text="Click Finish to save settings and launch JAV.",
            foreground="#3fb950",
        ).pack(anchor="w", padx=20)


# ---------------------------------------------------------------------------
# Wizard shell
# ---------------------------------------------------------------------------

class FirstLaunchWizard(tk.Toplevel):
    """Modal multi-step setup wizard shown on first launch.

    Calls on_complete(collected_config) when the user clicks Finish,
    or on_cancel() if they close the window.
    """

    STEPS: List[type] = [
        WelcomeStep,
        StorageModeStep,
        WorkspaceStep,
        ModelModeStep,
        DependencyCheckStep,
        VoiceTestStep,
        SummaryStep,
    ]

    def __init__(
        self,
        master: tk.Misc,
        on_complete: Callable[[Dict[str, str]], None],
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.title("JAV First Launch Setup")
        self.geometry("820x640")
        self.minsize(720, 520)
        self.resizable(True, True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._on_complete = on_complete
        self._on_cancel = on_cancel
        self._step_index: int = 0
        self._steps: List[WizardStep] = [cls() for cls in self.STEPS]
        self._collected: Dict[str, str] = {}
        self._content_frame: Optional[ttk.Frame] = None

        self._build_shell()
        self._show_step(0)

    # ------------------------------------------------------------------
    # Shell construction
    # ------------------------------------------------------------------
    def _build_shell(self) -> None:
        # Top header bar
        header = tk.Frame(self, bg="#161b22", height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        self._title_lbl = tk.Label(header, text="", bg="#161b22", fg="#e6edf3",
                                   font=("Segoe UI", 13, "bold"))
        self._title_lbl.pack(side=tk.LEFT, padx=20, pady=12)

        self._step_counter = tk.Label(header, text="", bg="#161b22", fg="#8b949e",
                                      font=("Segoe UI", 9))
        self._step_counter.pack(side=tk.RIGHT, padx=20)

        # Progress bar
        self._progress = ttk.Progressbar(self, mode="determinate",
                                         maximum=len(self.STEPS) - 1)
        self._progress.pack(fill=tk.X, padx=0, pady=0)

        # Content area (swapped per step)
        self._content_area = ttk.Frame(self, padding=0)
        self._content_area.pack(fill=tk.BOTH, expand=True)

        # Bottom navigation
        nav = ttk.Frame(self, padding=(16, 8))
        nav.pack(fill=tk.X, side=tk.BOTTOM)

        self._back_btn = ttk.Button(nav, text="← Back", command=self._back)
        self._back_btn.pack(side=tk.LEFT)

        self._skip_btn = ttk.Button(nav, text="Skip", command=self._skip)
        self._skip_btn.pack(side=tk.LEFT, padx=(8, 0))

        self._next_btn = ttk.Button(nav, text="Next →", command=self._next)
        self._next_btn.pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _show_step(self, index: int) -> None:
        # Destroy old content
        for w in self._content_area.winfo_children():
            w.destroy()

        self._step_index = index
        step = self._steps[index]

        # Update header
        self._title_lbl.configure(text=f"{step.title}  —  {step.subtitle}" if step.subtitle else step.title)
        self._step_counter.configure(text=f"Step {index + 1} of {len(self.STEPS)}")
        self._progress.configure(value=index)

        # If this is the summary step, give it the collected config
        if isinstance(step, SummaryStep):
            step.set_collected(self._collected)

        # Build step content inside a scrollable canvas so the wizard fits on
        # small laptop screens and inside VM/remote desktop sessions.
        canvas = tk.Canvas(self._content_area, highlightthickness=0)
        scroll = ttk.Scrollbar(self._content_area, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_content(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfigure(win, width=event.width)

        content.bind("<Configure>", _on_content)
        canvas.bind("<Configure>", _on_canvas)
        step.build(content)
        self._content_frame = content

        # Update nav buttons
        self._back_btn.configure(state=tk.NORMAL if index > 0 else tk.DISABLED)
        self._skip_btn.configure(state=tk.NORMAL if step.skippable else tk.DISABLED)

        is_last = (index == len(self.STEPS) - 1)
        self._next_btn.configure(text="Finish" if is_last else "Next →")

    def _next(self) -> None:
        step = self._steps[self._step_index]
        ok, err = step.is_valid()
        if not ok:
            messagebox.showwarning("Setup", err, parent=self)
            return
        self._collected.update(step.get_config())

        if self._step_index + 1 >= len(self.STEPS):
            self._finish()
        else:
            self._show_step(self._step_index + 1)

    def _back(self) -> None:
        if self._step_index > 0:
            self._show_step(self._step_index - 1)

    def _skip(self) -> None:
        if self._steps[self._step_index].skippable:
            if self._step_index + 1 >= len(self.STEPS):
                self._finish()
            else:
                self._show_step(self._step_index + 1)

    def _cancel(self) -> None:
        self.destroy()
        self._on_cancel()

    def _finish(self) -> None:
        # Collect last step
        step = self._steps[self._step_index]
        self._collected.update(step.get_config())

        # Write to .env
        try:
            self._write_env(self._collected)
        except Exception as exc:
            messagebox.showerror(
                "Setup Error",
                f"Could not write settings to .env:\n{exc}\n\n"
                "JAV will still launch with defaults.",
                parent=self,
            )

        # Create selected folders and setup sentinels.  We keep both an app-root
        # sentinel and a data-dir sentinel so portable folders remain movable.
        try:
            _ensure_setup_folders(self._collected)
        except Exception as exc:
            messagebox.showwarning("Setup", f"Settings were saved, but some folders could not be created:\n{exc}", parent=self)
            (_APP_ROOT / ".jav_setup_complete").touch()
            data_dir = self._collected.get("JARVIS_DATA_DIR", "data/brain")
            data_path = Path(data_dir).expanduser()
            if not data_path.is_absolute():
                data_path = _APP_ROOT / data_path
            (data_path / ".jav_setup_complete").touch()
        except Exception:
            pass

        self.destroy()
        self._on_complete(self._collected)

    # ------------------------------------------------------------------
    # .env writer (minimal — writes only the wizard's keys)
    # ------------------------------------------------------------------
    def _write_env(self, config: Dict[str, str]) -> None:
        env_path = _APP_ROOT / ".env"
        existing_lines: List[str] = []
        if env_path.exists():
            existing_lines = env_path.read_text(encoding="utf-8").splitlines()

        # Build a map of existing non-wizard lines
        new_lines: List[str] = []
        wizard_keys = set(config.keys())
        for line in existing_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key not in wizard_keys:
                new_lines.append(line)

        # Append wizard keys
        if new_lines and new_lines[-1] != "":
            new_lines.append("")
        new_lines.append("# === JAV Setup Wizard ===")
        for key, value in sorted(config.items()):
            new_lines.append(f"{key}={value}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
