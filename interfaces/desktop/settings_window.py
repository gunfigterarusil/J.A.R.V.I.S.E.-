"""Improved Desktop Settings Center for JAV / Jarvis Brain Core.

V9.3 UI upgrade:
- searchable settings
- scrollable tabs that do not push buttons off-screen
- browse buttons for path-like settings
- grouped settings for LLM, voice, screen, memory, web learning and actions
- writes to .env so chat/voice/desktop/web share the same configuration
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
import tkinter as tk
from typing import Callable, Dict, List


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    default: str = ""
    help: str = ""
    kind: str = "text"  # text | bool | password | list | path | file


SETTINGS_GROUPS: Dict[str, List[SettingSpec]] = {
    "Portable / Paths": [
        SettingSpec("JAV_PORTABLE", "Portable mode", "false", "Store data beside the program when true", kind="bool"),
        SettingSpec("JARVIS_DATA_DIR", "Brain / memory data directory", "", "Example: E:/JAV/data/brain", kind="path"),
        SettingSpec("ACTION_WORKSPACE_PATH", "Workspace directory", "~/jarvis_workspace", "Files Jarvis can safely edit", kind="path"),
        SettingSpec("SCREENSHOT_DIR", "Screenshot directory", "", "Leave empty to use memory_dir/screenshots", kind="path"),
        SettingSpec("PIPER_OUTPUT_DIR", "Piper audio output directory", "", "Leave empty for temporary audio", kind="path"),
    ],
    "LLM": [
        SettingSpec("OLLAMA_HOST", "Ollama host", "http://localhost:11434"),
        SettingSpec("OLLAMA_MODEL", "Ollama model", "llama3.2"),
        SettingSpec("GEMINI_API_KEY", "Gemini API key", "", kind="password"),
        SettingSpec("GEMINI_MODEL", "Gemini model", "gemini-2.0-flash"),
        SettingSpec("OPENAI_API_KEY", "OpenAI API key", "", kind="password"),
        SettingSpec("OPENAI_MODEL", "OpenAI model", "gpt-4o"),
        SettingSpec("OPENAI_BASE_URL", "OpenAI-compatible base URL", "https://api.openai.com/v1"),
        SettingSpec("ANTHROPIC_API_KEY", "Anthropic API key", "", kind="password"),
        SettingSpec("ANTHROPIC_MODEL", "Anthropic model", "claude-3-5-sonnet-latest"),
        SettingSpec("LLAMACPP_HOST", "llama.cpp server", "http://localhost:8080"),
    ],
    "Voice": [
        SettingSpec("VOICE_STT_MODEL", "STT model", "small"),
        SettingSpec("VOICE_STT_DEVICE", "STT device", "cpu"),
        SettingSpec("VOICE_STT_COMPUTE_TYPE", "STT compute type", "int8"),
        SettingSpec("VOICE_STT_LANGUAGE", "STT language", ""),
        SettingSpec("VOICE_RECORD_SECONDS", "Record seconds", "5"),
        SettingSpec("VOICE_WAKE_WORD", "Wake word", ""),
        SettingSpec("VOICE_TTS_ENABLED", "Enable TTS", "true", kind="bool"),
        SettingSpec("VOICE_TTS_BACKEND", "TTS backend", "auto"),
        SettingSpec("PIPER_EXECUTABLE", "Piper executable", "piper", kind="file"),
        SettingSpec("PIPER_MODEL_PATH", "Piper model path", "", kind="file"),
        SettingSpec("PIPER_CONFIG_PATH", "Piper config path", "", kind="file"),
        SettingSpec("PYTTSX3_VOICE_ID", "pyttsx3 voice id", ""),
        SettingSpec("PYTTSX3_RATE", "pyttsx3 rate", "175"),
        SettingSpec("PYTTSX3_VOLUME", "pyttsx3 volume", "1.0"),
    ],
    "Screen / OCR": [
        SettingSpec("SCREEN_READING_ENABLED", "Enable screen reading", "true", kind="bool"),
        SettingSpec("SCREEN_AUTO_WATCH_ENABLED", "Auto-watch screen", "false", kind="bool"),
        SettingSpec("SCREENSHOT_DIR", "Screenshot directory", "", kind="path"),
        SettingSpec("SCREEN_OCR_BACKEND", "OCR backend", "tesseract"),
        SettingSpec("SCREEN_OCR_LANGUAGE", "OCR language", "eng"),
        SettingSpec("SCREEN_OCR_CONFIG", "OCR config", "--psm 6"),
        SettingSpec("SCREEN_SAVE_SCREENSHOTS", "Save screenshots", "true", kind="bool"),
        SettingSpec("SCREEN_MAX_OCR_CHARS", "Max OCR chars", "7000"),
        SettingSpec("TESSERACT_CMD", "Tesseract path", "", kind="file"),
    ],
    "Actions / Repair": [
        SettingSpec("ACTIONS_V7_ENABLED", "Enable safe actions", "true", kind="bool"),
        SettingSpec("ACTION_MAX_READ_CHARS", "Max read chars", "12000"),
        SettingSpec("ACTION_MAX_LIST_ENTRIES", "Max list entries", "120"),
        SettingSpec("ACTION_ALLOW_SHELL", "Allow shell actions", "false", kind="bool"),
        SettingSpec("ACTION_COMMAND_TIMEOUT", "Command timeout", "20"),
        SettingSpec("ACTION_ALLOWED_COMMANDS", "Allowed commands", "python,python3,py,pytest,pip,pip3,git", kind="list"),
        SettingSpec("NATURAL_ACTIONS_ENABLED", "Natural language actions", "true", kind="bool"),
        SettingSpec("NATURAL_ACTIONS_REQUIRE_EXPLICIT_VERB", "Require explicit action verb", "true", kind="bool"),
        SettingSpec("REPAIR_AGENT_ENABLED", "Enable repair intent", "true", kind="bool"),
        SettingSpec("CODE_REPAIR_V9_ENABLED", "Enable V9 repair agent", "true", kind="bool"),
        SettingSpec("CODE_REPAIR_MAX_FILES", "Repair max files", "160"),
        SettingSpec("CODE_REPAIR_MAX_FILE_CHARS", "Repair max file chars", "18000"),
        SettingSpec("CODE_REPAIR_AUTO_APPLY", "Auto-apply repair proposals", "false", kind="bool"),
        SettingSpec("CODE_REPAIR_REQUIRE_LLM", "Require LLM for patch", "true", kind="bool"),
        SettingSpec("TASK_CHAINS_ENABLED", "Enable V9.4 task chains", "true", kind="bool"),
        SettingSpec("TASK_CHAINS_AUTO_STEP_DEFAULT", "Task chains auto-step by default", "false", kind="bool"),
        SettingSpec("TASK_CHAINS_MAX_STEPS", "Task chain max steps", "8"),
        SettingSpec("TASK_CHAINS_STEP_TIMEOUT_SECONDS", "Task step timeout seconds", "90"),
    ],
    "Memory / Sleep": [
        SettingSpec("MEMORY_STM_LIFETIME_SECONDS", "Short-term memory lifetime seconds", "30"),
        SettingSpec("MEMORY_EPISODIC_RETENTION_DAYS", "Episodic retention days", "730"),
        SettingSpec("MEMORY_EPISODIC_MAX_ITEMS", "Max episodic items", "20000"),
        SettingSpec("MEMORY_ARCHIVE_DECAYED", "Archive expired memories", "true", kind="bool"),
        SettingSpec("MEMORY_SEMANTIC_AUTOSTORE", "Auto-store important facts", "true", kind="bool"),
        SettingSpec("MEMORY_SAVE_INTERVAL_SECONDS", "Memory save interval seconds", "60"),
        SettingSpec("MEMORY_SQLITE_ENABLED", "Enable SQLite durable memory", "true", kind="bool"),
        SettingSpec("MEMORY_VECTOR_ENABLED", "Enable local vector search", "true", kind="bool"),
        SettingSpec("MEMORY_VECTOR_DIMENSIONS", "Vector dimensions", "256"),
        SettingSpec("MEMORY_SEARCH_TOP_K", "Default memory search results", "8"),
        SettingSpec("SLEEP_V6_ENABLED", "Enable sleep/consolidation", "true", kind="bool"),
        SettingSpec("SLEEP_AUTO_ENABLED", "Auto sleep", "true", kind="bool"),
        SettingSpec("SLEEP_AUTO_INTERVAL", "Auto interval seconds", "900"),
        SettingSpec("SLEEP_IDLE_THRESHOLD", "Idle threshold seconds", "90"),
        SettingSpec("SLEEP_ENERGY_THRESHOLD", "Energy threshold", "0.38"),
        SettingSpec("SLEEP_MANUAL_MIN_GAP", "Manual min gap", "3.0"),
        SettingSpec("SLEEP_MAX_REPLAY_EVENTS", "Max replay events", "80"),
        SettingSpec("SLEEP_MAX_DIALOGUE_PAIRS", "Max dialogue pairs", "24"),
        SettingSpec("SLEEP_MAX_LESSONS_PER_CYCLE", "Max lessons", "8"),
    ],
    "Web Learning": [
        SettingSpec("WEB_LEARNING_ENABLED", "Enable web learning module", "true", kind="bool"),
        SettingSpec("WEB_SEARCH_ENABLED", "Enable web search", "true", kind="bool"),
        SettingSpec("WEB_LEARN_STORE_ENABLED", "Store web learning into memory", "true", kind="bool"),
        SettingSpec("WEB_SEARCH_MAX_RESULTS", "Search max results", "5"),
        SettingSpec("WEB_LEARN_MAX_SOURCES", "Learning max sources", "4"),
        SettingSpec("WEB_FETCH_TIMEOUT_SECONDS", "Fetch timeout seconds", "12"),
        SettingSpec("WEB_FETCH_MAX_CHARS_PER_PAGE", "Max readable chars per page", "9000"),
        SettingSpec("WEB_USER_AGENT", "User-Agent", "JAV-WebLearning/0.1"),
    ],
    "Self / World / Emotion": [
        SettingSpec("EMOTION_V4_ENABLED", "Enable emotion layer", "true", kind="bool"),
        SettingSpec("EMOTION_STATE_EMIT_INTERVAL", "Emotion emit interval", "4.0"),
        SettingSpec("EMOTION_DECAY_STRENGTH", "Emotion decay", "0.985"),
        SettingSpec("MONOLOGUE_V4_ENABLED", "Enable monologue", "true", kind="bool"),
        SettingSpec("MONOLOGUE_INTERVAL", "Monologue interval", "6.0"),
        SettingSpec("SELF_MODEL_V5_ENABLED", "Enable self model", "true", kind="bool"),
        SettingSpec("SELF_MODEL_SNAPSHOT_INTERVAL", "Self snapshot interval", "12.0"),
        SettingSpec("SELF_MODEL_REFLECTION_INTERVAL", "Self reflection interval", "45.0"),
        SettingSpec("WORLD_MODEL_V5_ENABLED", "Enable world model", "true", kind="bool"),
        SettingSpec("WORLD_MODEL_SNAPSHOT_INTERVAL", "World snapshot interval", "10.0"),
        SettingSpec("WORLD_MODEL_MAX_TIMELINE_ITEMS", "Max timeline items", "80"),
        SettingSpec("WORLD_MODEL_MAX_OPEN_LOOPS", "Max open loops", "25"),
    ],
    "Web UI / Desktop": [
        SettingSpec("BRAIN_HOST", "Web host", "127.0.0.1"),
        SettingSpec("BRAIN_PORT", "Web port", "8000"),
        SettingSpec("BRAIN_RELOAD", "Web reload", "false", kind="bool"),
        SettingSpec("WEB_UI_API_TOKEN", "Web API token", "", kind="password"),
        SettingSpec("WEB_CORS_ORIGINS", "CORS origins", "http://127.0.0.1:8000,http://localhost:8000", kind="list"),
    ],
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def save_env(path: Path, updates: Dict[str, str]) -> None:
    existing_lines: List[str] = []
    seen: set[str] = set()
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: List[str] = []
    for raw in existing_lines:
        if "=" in raw and not raw.lstrip().startswith("#"):
            key = raw.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                out.append(raw)
        else:
            out.append(raw)
    missing = [(k, v) for k, v in updates.items() if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# Added by JAV Settings Center")
        for key, value in missing:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


class SettingsWindow(tk.Toplevel):
    def __init__(self, master: tk.Tk, on_saved: Callable[[Dict[str, str]], None] | None = None) -> None:
        super().__init__(master)
        self.title("JAV Settings Center")
        self.geometry("980x720")
        self.minsize(860, 560)
        self.on_saved = on_saved
        self.env_path = _project_root() / ".env"
        self.example_path = _project_root() / ".env.example"
        self.values = load_env(self.example_path)
        self.values.update(load_env(self.env_path))
        self.vars: Dict[str, tk.StringVar] = {}
        self.rows: List[tuple[str, ttk.Frame, SettingSpec]] = []
        self.search_var = tk.StringVar()
        self._build_ui()

    def _build_ui(self) -> None:
        self.configure(bg="#0f1218")
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Settings Center", font=("Segoe UI", 15, "bold")).pack(side=tk.LEFT)
        ttk.Label(top, text="Saved to .env. Restart for provider/path/module changes.").pack(side=tk.LEFT, padx=(14, 0))

        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(8, 8))
        ttk.Label(search_row, text="Search:").pack(side=tk.LEFT)
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        ttk.Button(search_row, text="Clear", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)
        self.search_var.trace_add("write", lambda *_: self._apply_filter())

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        for group, specs in SETTINGS_GROUPS.items():
            frame = ttk.Frame(self.notebook, padding=0)
            self.notebook.add(frame, text=group)
            self._build_group(frame, specs)

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Save settings", command=self._save).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="Reload from .env", command=self._reload).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Open project folder", command=lambda: self._open_folder(_project_root())).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Open .env", command=self._open_env_hint).pack(side=tk.LEFT, padx=(6, 0))

    def _build_group(self, parent: ttk.Frame, specs: List[SettingSpec]) -> None:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, padding=10)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _configure_body(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        body.bind("<Configure>", _configure_body)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e, c=canvas: c.yview_scroll(int(-1 * (e.delta / 120)), "units") if self.focus_get() else None)

        for row, spec in enumerate(specs):
            row_frame = ttk.Frame(body)
            row_frame.grid(row=row, column=0, sticky="ew", pady=4)
            row_frame.columnconfigure(1, weight=1)
            ttk.Label(row_frame, text=spec.label, width=26).grid(row=0, column=0, sticky="w", padx=(0, 8))
            var = tk.StringVar(value=self.values.get(spec.key, spec.default))
            self.vars[spec.key] = var
            if spec.kind == "bool":
                cb = ttk.Checkbutton(row_frame, variable=var, onvalue="true", offvalue="false")
                cb.grid(row=0, column=1, sticky="w")
            else:
                show = "*" if spec.kind == "password" else ""
                ent = ttk.Entry(row_frame, textvariable=var, show=show)
                ent.grid(row=0, column=1, sticky="ew")
                if spec.kind in {"path", "file"}:
                    ttk.Button(row_frame, text="Browse", command=lambda s=spec: self._browse(s)).grid(row=0, column=2, padx=(6, 0))
            ttk.Label(row_frame, text=spec.key, foreground="#6c7685").grid(row=1, column=1, sticky="w")
            if spec.help:
                ttk.Label(row_frame, text=spec.help, foreground="#7f8da3").grid(row=2, column=1, sticky="w")
            self.rows.append((spec.key, row_frame, spec))
        body.columnconfigure(0, weight=1)

    def _browse(self, spec: SettingSpec) -> None:
        current = self.vars[spec.key].get().strip()
        initial = current if current and not current.startswith("~") else str(_project_root())
        if spec.kind == "file":
            path = filedialog.askopenfilename(initialdir=initial if Path(initial).is_dir() else str(_project_root()))
        else:
            path = filedialog.askdirectory(initialdir=initial if Path(initial).exists() else str(_project_root()))
        if path:
            self.vars[spec.key].set(path)

    def _apply_filter(self) -> None:
        q = self.search_var.get().strip().lower()
        for key, frame, spec in self.rows:
            hay = f"{key} {spec.label} {spec.help}".lower()
            visible = not q or q in hay
            if visible:
                frame.grid()
            else:
                frame.grid_remove()

    def _save(self) -> None:
        updates = {key: var.get().strip() for key, var in self.vars.items()}
        try:
            save_env(self.env_path, updates)
        except Exception as exc:
            messagebox.showerror("Settings", f"Could not save .env: {exc}")
            return
        if self.on_saved:
            self.on_saved(updates)
        messagebox.showinfo("Settings", "Saved to .env. Restart JAV for all changes to fully apply.")

    def _reload(self) -> None:
        self.values = load_env(self.example_path)
        self.values.update(load_env(self.env_path))
        for key, var in self.vars.items():
            default = ""
            for specs in SETTINGS_GROUPS.values():
                for spec in specs:
                    if spec.key == key:
                        default = spec.default
                        break
            var.set(self.values.get(key, default))
        self._apply_filter()

    def _open_folder(self, path: Path) -> None:
        import os, subprocess, sys
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showinfo("Open folder", f"Folder: {path}\n{exc}")

    def _open_env_hint(self) -> None:
        messagebox.showinfo(".env location", f"{self.env_path}\n\nYou can edit it manually, then restart JAV.")
