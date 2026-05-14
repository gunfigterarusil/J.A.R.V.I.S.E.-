"""Desktop Settings Center for JAV / Jarvis Brain Core.

V8.1 exposes the main runtime features through a native Tkinter settings
window. It edits the project .env file so the same settings are used by
--desktop, --chat, --voice and --web on the next launch.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
import tkinter as tk
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    default: str = ""
    help: str = ""
    kind: str = "text"  # text | bool | password | list


SETTINGS_GROUPS: Dict[str, List[SettingSpec]] = {
    "Portable / Paths": [
        SettingSpec("JAV_PORTABLE", "Portable mode", "false", "Store data beside the program when true", kind="bool"),
        SettingSpec("JARVIS_DATA_DIR", "Brain / memory data directory", "", "Example: E:/JAV/data/brain"),
        SettingSpec("ACTION_WORKSPACE_PATH", "Workspace directory", "~/jarvis_workspace", "Files Jarvis can safely edit"),
        SettingSpec("SCREENSHOT_DIR", "Screenshot directory", "", "Leave empty to use memory_dir/screenshots"),
        SettingSpec("PIPER_OUTPUT_DIR", "Piper audio output directory", "", "Leave empty for temporary audio"),
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
        SettingSpec("PIPER_EXECUTABLE", "Piper executable", "piper"),
        SettingSpec("PIPER_MODEL_PATH", "Piper model path", ""),
        SettingSpec("PIPER_CONFIG_PATH", "Piper config path", ""),
        SettingSpec("PYTTSX3_VOICE_ID", "pyttsx3 voice id", ""),
        SettingSpec("PYTTSX3_RATE", "pyttsx3 rate", "175"),
        SettingSpec("PYTTSX3_VOLUME", "pyttsx3 volume", "1.0"),
    ],
    "Screen": [
        SettingSpec("SCREEN_READING_ENABLED", "Enable screen reading", "true", kind="bool"),
        SettingSpec("SCREEN_AUTO_WATCH_ENABLED", "Auto-watch screen", "false", kind="bool"),
        SettingSpec("SCREENSHOT_DIR", "Screenshot directory", ""),
        SettingSpec("SCREEN_OCR_BACKEND", "OCR backend", "tesseract"),
        SettingSpec("SCREEN_OCR_LANGUAGE", "OCR language", "eng"),
        SettingSpec("SCREEN_OCR_CONFIG", "OCR config", "--psm 6"),
        SettingSpec("SCREEN_SAVE_SCREENSHOTS", "Save screenshots", "true", kind="bool"),
        SettingSpec("SCREEN_MAX_OCR_CHARS", "Max OCR chars", "7000"),
        SettingSpec("TESSERACT_CMD", "Tesseract path", ""),
    ],
    "Actions": [
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
    "Web / Desktop": [
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
        self.geometry("900x680")
        self.minsize(760, 520)
        self.on_saved = on_saved
        self.env_path = _project_root() / ".env"
        self.example_path = _project_root() / ".env.example"
        self.values = load_env(self.env_path)
        if not self.values:
            self.values.update(load_env(self.example_path))
        self.vars: Dict[str, tk.StringVar] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text="Settings are saved to .env and take full effect after restarting JAV. Safety level changes still apply live.",
        ).pack(anchor="w", pady=(0, 8))
        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)
        for group, specs in SETTINGS_GROUPS.items():
            frame = ttk.Frame(notebook, padding=10)
            notebook.add(frame, text=group)
            self._build_group(frame, specs)
        row = ttk.Frame(outer)
        row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(row, text="Save", command=self._save).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(row, text="Reload", command=self._reload).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(row, text="Close", command=self.destroy).pack(side=tk.RIGHT)

    def _build_group(self, parent: ttk.Frame, specs: List[SettingSpec]) -> None:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        for row, spec in enumerate(specs):
            ttk.Label(body, text=spec.label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
            value = self.values.get(spec.key, os.environ.get(spec.key, spec.default))
            var = tk.StringVar(value=value)
            self.vars[spec.key] = var
            if spec.kind == "bool":
                box = ttk.Combobox(body, textvariable=var, values=["true", "false"], width=16, state="readonly")
                box.grid(row=row, column=1, sticky="w", pady=5)
            else:
                show = "*" if spec.kind == "password" else ""
                field_frame = ttk.Frame(body)
                field_frame.grid(row=row, column=1, sticky="ew", pady=5)
                field_frame.columnconfigure(0, weight=1)
                entry = ttk.Entry(field_frame, textvariable=var, width=60, show=show)
                entry.grid(row=0, column=0, sticky="ew")
                if spec.key in {"JARVIS_DATA_DIR", "ACTION_WORKSPACE_PATH", "SCREENSHOT_DIR", "PIPER_OUTPUT_DIR"}:
                    ttk.Button(field_frame, text="Browse", command=lambda v=var: self._browse_dir(v)).grid(row=0, column=1, padx=(6, 0))
            ttk.Label(body, text=spec.key, foreground="#777").grid(row=row, column=2, sticky="w", padx=(10, 0), pady=5)
        body.columnconfigure(1, weight=1)

    def _browse_dir(self, var: tk.StringVar) -> None:
        selected = filedialog.askdirectory(parent=self, title="Choose directory")
        if selected:
            var.set(selected)

    def _reload(self) -> None:
        self.values = load_env(self.env_path) or load_env(self.example_path)
        for key, var in self.vars.items():
            spec_default = ""
            for specs in SETTINGS_GROUPS.values():
                for spec in specs:
                    if spec.key == key:
                        spec_default = spec.default
                        break
            var.set(self.values.get(key, os.environ.get(key, spec_default)))

    def _save(self) -> None:
        updates = {key: var.get().strip() for key, var in self.vars.items()}
        try:
            save_env(self.env_path, updates)
            for key, value in updates.items():
                os.environ[key] = value
            if self.on_saved:
                self.on_saved(updates)
            messagebox.showinfo("Saved", f"Settings saved to {self.env_path}\nRestart JAV to reload all modules with new values.")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
