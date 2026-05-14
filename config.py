"""Global configuration for the PCA Kernel and associated subsystems.

This module defines a dataclass-based configuration that is used by
kernel_main, connector, and the web dashboard.

Usage::

    from config import KernelConfig
    cfg = KernelConfig()
    print(cfg.tick_rate)

    # Or override fields after instantiation
    cfg.web_port = 8000
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional at runtime; environment variables still work without it.
    pass


PROJECT_ROOT = Path(__file__).resolve().parent


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _default_data_dir() -> str:
    explicit = (
        os.environ.get("JARVIS_DATA_DIR")
        or os.environ.get("MEMORY_DIR")
        or os.environ.get("PERSISTENCE_DIR")
        or ""
    ).strip()
    if explicit:
        return explicit
    if _env_bool("JAV_PORTABLE", "false"):
        return str(PROJECT_ROOT / "data" / "brain")
    return "~/.jarvis_brain"


def _default_workspace_dir() -> str:
    explicit = os.environ.get("ACTION_WORKSPACE_PATH", "").strip()
    if explicit:
        return explicit
    if _env_bool("JAV_PORTABLE", "false"):
        return str(PROJECT_ROOT / "data" / "workspace")
    return "~/jarvis_workspace"


def _default_screenshot_dir() -> str:
    explicit = os.environ.get("SCREENSHOT_DIR", "").strip()
    if explicit:
        return explicit
    if _env_bool("JAV_PORTABLE", "false"):
        return str(PROJECT_ROOT / "data" / "screenshots")
    return ""


@dataclass
class SubjectiveFieldDefaults:
    """Default starting values for the SubjectiveField."""
    safety: float = 0.7
    social_warmth: float = 0.5
    mental_overload: float = 0.0
    motivation: float = 0.8
    boredom: float = 0.0


@dataclass
class LoggingConfig:
    """Logging-related settings."""
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(message)s"
    date_format: str = "%H:%M:%S"


@dataclass
class ModuleDefaults:
    """Paths and default module settings."""
    module_paths: List[str] = field(default_factory=lambda: [
        str(Path(__file__).parent / "modules"),
    ])
    default_modules: List[str] = field(default_factory=list)


@dataclass
class LLMRouterConfig:
    """Configuration for the multi-LLM router.

    API keys are read from environment variables if not set here.
    Set via env: GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
    Or edit the fields below directly.
    """
    routing: Dict[str, str] = field(default_factory=dict)

    # Ollama (local, no API key needed)
    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.2"))

    # Gemini  →  set GEMINI_API_KEY env var or fill in the string
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))

    # OpenAI-compatible  →  OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o"))
    openai_base_url: str = field(default_factory=lambda: os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))

    # Anthropic  →  ANTHROPIC_API_KEY, ANTHROPIC_MODEL
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"))

    # llama.cpp server
    llamacpp_host: str = field(default_factory=lambda: os.environ.get("LLAMACPP_HOST", "http://localhost:8080"))

    # Generation defaults
    default_timeout: float = 60.0
    max_tokens: int = 2048
    temperature: float = 0.7


@dataclass
class VoiceConfig:
    """Voice input/output settings for `python main.py --voice`.

    Dependencies are optional until voice mode is enabled.
    STT: sounddevice + faster-whisper
    TTS: Piper CLI + local voice model, with pyttsx3 fallback
    """
    enabled: bool = False

    # Speech-to-text
    stt_model: str = field(default_factory=lambda: os.environ.get("VOICE_STT_MODEL", "small"))
    stt_device: str = field(default_factory=lambda: os.environ.get("VOICE_STT_DEVICE", "cpu"))
    stt_compute_type: str = field(default_factory=lambda: os.environ.get("VOICE_STT_COMPUTE_TYPE", "int8"))
    stt_language: str = field(default_factory=lambda: os.environ.get("VOICE_STT_LANGUAGE", ""))  # empty = auto-detect
    sample_rate: int = field(default_factory=lambda: int(os.environ.get("VOICE_SAMPLE_RATE", "16000")))
    record_seconds: float = field(default_factory=lambda: float(os.environ.get("VOICE_RECORD_SECONDS", "5")))
    energy_threshold: float = field(default_factory=lambda: float(os.environ.get("VOICE_ENERGY_THRESHOLD", "0.005")))
    wake_word: str = field(default_factory=lambda: os.environ.get("VOICE_WAKE_WORD", ""))
    print_transcript: bool = field(default_factory=lambda: os.environ.get("VOICE_PRINT_TRANSCRIPT", "true").lower() == "true")
    response_timeout: float = field(default_factory=lambda: float(os.environ.get("VOICE_RESPONSE_TIMEOUT", "90")))
    tts_wait_timeout: float = field(default_factory=lambda: float(os.environ.get("VOICE_TTS_WAIT_TIMEOUT", "45")))
    listen_after_response_delay: float = field(default_factory=lambda: float(os.environ.get("VOICE_LISTEN_AFTER_RESPONSE_DELAY", "0.35")))

    # Text-to-speech
    tts_enabled: bool = field(default_factory=lambda: os.environ.get("VOICE_TTS_ENABLED", "true").lower() == "true")
    tts_backend: str = field(default_factory=lambda: os.environ.get("VOICE_TTS_BACKEND", "auto"))  # auto|piper|pyttsx3|none

    # Piper TTS
    piper_executable: str = field(default_factory=lambda: os.environ.get("PIPER_EXECUTABLE", "piper"))
    piper_model_path: str = field(default_factory=lambda: os.environ.get("PIPER_MODEL_PATH", ""))
    piper_config_path: str = field(default_factory=lambda: os.environ.get("PIPER_CONFIG_PATH", ""))
    piper_speaker: str = field(default_factory=lambda: os.environ.get("PIPER_SPEAKER", ""))
    piper_length_scale: float = field(default_factory=lambda: float(os.environ.get("PIPER_LENGTH_SCALE", "1.0")))
    piper_noise_scale: float = field(default_factory=lambda: float(os.environ.get("PIPER_NOISE_SCALE", "0.667")))
    piper_noise_w: float = field(default_factory=lambda: float(os.environ.get("PIPER_NOISE_W", "0.8")))
    piper_output_dir: str = field(default_factory=lambda: os.environ.get("PIPER_OUTPUT_DIR", ""))

    # pyttsx3 fallback TTS
    pyttsx3_voice_id: str = field(default_factory=lambda: os.environ.get("PYTTSX3_VOICE_ID", ""))
    pyttsx3_rate: int = field(default_factory=lambda: int(os.environ.get("PYTTSX3_RATE", "175")))
    pyttsx3_volume: float = field(default_factory=lambda: float(os.environ.get("PYTTSX3_VOLUME", "1.0")))


@dataclass
class ScreenConfig:
    """Screen reading settings for V3 OCR + ScreenParser.

    Dependencies are optional until /see or screen_capture_requested is used.
    Python: mss + Pillow + pytesseract
    System: Tesseract OCR binary and language packs
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("SCREEN_READING_ENABLED", "true").lower() == "true")
    auto_watch_enabled: bool = field(default_factory=lambda: os.environ.get("SCREEN_AUTO_WATCH_ENABLED", "false").lower() == "true")
    screenshot_dir: str = field(default_factory=_default_screenshot_dir)
    ocr_backend: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_BACKEND", "tesseract"))  # tesseract for V3 MVP
    ocr_language: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_LANGUAGE", "eng"))
    ocr_config: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_CONFIG", "--psm 6"))
    save_screenshots: bool = field(default_factory=lambda: os.environ.get("SCREEN_SAVE_SCREENSHOTS", "true").lower() == "true")
    max_ocr_chars: int = field(default_factory=lambda: int(os.environ.get("SCREEN_MAX_OCR_CHARS", "7000")))




@dataclass
class SelfModelConfig:
    """V5 mature self-model settings."""
    enabled: bool = field(default_factory=lambda: os.environ.get("SELF_MODEL_V5_ENABLED", "true").lower() == "true")
    self_snapshot_interval: float = field(default_factory=lambda: float(os.environ.get("SELF_MODEL_SNAPSHOT_INTERVAL", "12.0")))
    self_reflection_interval: float = field(default_factory=lambda: float(os.environ.get("SELF_MODEL_REFLECTION_INTERVAL", "45.0")))


@dataclass
class WorldModelConfig:
    """V5 world-model settings."""
    enabled: bool = field(default_factory=lambda: os.environ.get("WORLD_MODEL_V5_ENABLED", "true").lower() == "true")
    world_snapshot_interval: float = field(default_factory=lambda: float(os.environ.get("WORLD_MODEL_SNAPSHOT_INTERVAL", "10.0")))
    max_timeline_items: int = field(default_factory=lambda: int(os.environ.get("WORLD_MODEL_MAX_TIMELINE_ITEMS", "80")))
    max_open_loops: int = field(default_factory=lambda: int(os.environ.get("WORLD_MODEL_MAX_OPEN_LOOPS", "25")))






@dataclass
class WebLearningConfig:
    """V9.3 web search / web learning settings.

    Web learning is request-driven by default. It fetches sources with limits,
    summarizes them, and stores sourced notes into long-term memory.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("WEB_LEARNING_ENABLED", "true").lower() == "true")
    search_enabled: bool = field(default_factory=lambda: os.environ.get("WEB_SEARCH_ENABLED", "true").lower() == "true")
    learn_enabled: bool = field(default_factory=lambda: os.environ.get("WEB_LEARN_STORE_ENABLED", "true").lower() == "true")
    max_results: int = field(default_factory=lambda: int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5")))
    max_sources: int = field(default_factory=lambda: int(os.environ.get("WEB_LEARN_MAX_SOURCES", "4")))
    timeout_seconds: float = field(default_factory=lambda: float(os.environ.get("WEB_FETCH_TIMEOUT_SECONDS", "12")))
    max_chars_per_page: int = field(default_factory=lambda: int(os.environ.get("WEB_FETCH_MAX_CHARS_PER_PAGE", "9000")))
    user_agent: str = field(default_factory=lambda: os.environ.get("WEB_USER_AGENT", "JAV-WebLearning/0.1"))


@dataclass
class NaturalActionConfig:
    """V8.1 natural-language action routing settings.

    When enabled, ordinary chat/voice phrases can trigger the same safe actions
    as slash commands. They still pass through the V7 safety firewall.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("NATURAL_ACTIONS_ENABLED", "true").lower() == "true")
    require_explicit_verb: bool = field(default_factory=lambda: os.environ.get("NATURAL_ACTIONS_REQUIRE_EXPLICIT_VERB", "true").lower() == "true")
    repair_agent_enabled: bool = field(default_factory=lambda: os.environ.get("REPAIR_AGENT_ENABLED", "true").lower() == "true")



@dataclass
class CodeRepairConfig:
    """V9 project repair agent settings.

    The repair agent diagnoses code, asks the LLM for a minimal patch, validates
    the proposed files locally, and applies changes only through V7 safe actions.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("CODE_REPAIR_V9_ENABLED", "true").lower() == "true")
    max_files: int = field(default_factory=lambda: int(os.environ.get("CODE_REPAIR_MAX_FILES", "160")))
    max_file_chars: int = field(default_factory=lambda: int(os.environ.get("CODE_REPAIR_MAX_FILE_CHARS", "18000")))
    auto_apply: bool = field(default_factory=lambda: os.environ.get("CODE_REPAIR_AUTO_APPLY", "false").lower() == "true")
    require_llm_for_patch: bool = field(default_factory=lambda: os.environ.get("CODE_REPAIR_REQUIRE_LLM", "true").lower() == "true")



@dataclass
class TaskChainConfig:
    """V9.4 autonomous/guided task chain settings.

    A task chain decomposes a broad goal into safe steps. External effects still
    go through V7 safety gates. Guided mode is default; auto mode can continue
    low-risk steps until it hits a safety confirmation or completion.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_ENABLED", "true").lower() == "true")
    auto_step_default: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_AUTO_STEP_DEFAULT", "false").lower() == "true")
    max_steps: int = field(default_factory=lambda: int(os.environ.get("TASK_CHAINS_MAX_STEPS", "8")))
    step_timeout_seconds: float = field(default_factory=lambda: float(os.environ.get("TASK_CHAINS_STEP_TIMEOUT_SECONDS", "90")))

@dataclass
class ActionConfig:
    """V7 safe PC automation settings.

    File actions are sandboxed to ACTION_WORKSPACE_PATH by default.
    Shell actions are disabled unless ACTION_ALLOW_SHELL=true and the
    permission level is raised to L5.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("ACTIONS_V7_ENABLED", "true").lower() == "true")
    workspace_path: str = field(default_factory=_default_workspace_dir)
    allow_shell: bool = field(default_factory=lambda: os.environ.get("ACTION_ALLOW_SHELL", "false").lower() == "true")
    command_timeout: float = field(default_factory=lambda: float(os.environ.get("ACTION_COMMAND_TIMEOUT", "20")))
    max_read_chars: int = field(default_factory=lambda: int(os.environ.get("ACTION_MAX_READ_CHARS", "12000")))
    max_list_entries: int = field(default_factory=lambda: int(os.environ.get("ACTION_MAX_LIST_ENTRIES", "120")))
    allowed_commands: List[str] = field(default_factory=lambda: [
        x.strip() for x in os.environ.get("ACTION_ALLOWED_COMMANDS", "python,python3,py,pytest,pip,pip3,git").split(",")
        if x.strip()
    ])


@dataclass
class MemoryConfig:
    """V9.1 long-term memory and portable storage settings.

    Episodic decay is now measured in days, not seconds. Important memories
    are archived/retained instead of silently disappearing after minutes.
    """
    data_dir: str = field(default_factory=_default_data_dir)
    stm_lifetime_seconds: float = field(default_factory=lambda: float(os.environ.get("MEMORY_STM_LIFETIME_SECONDS", "30")))
    episodic_retention_days: float = field(default_factory=lambda: float(os.environ.get("MEMORY_EPISODIC_RETENTION_DAYS", "730")))
    episodic_max_items: int = field(default_factory=lambda: int(os.environ.get("MEMORY_EPISODIC_MAX_ITEMS", "20000")))
    archive_decayed: bool = field(default_factory=lambda: os.environ.get("MEMORY_ARCHIVE_DECAYED", "true").lower() == "true")
    semantic_autostore: bool = field(default_factory=lambda: os.environ.get("MEMORY_SEMANTIC_AUTOSTORE", "true").lower() == "true")
    save_interval_seconds: float = field(default_factory=lambda: float(os.environ.get("MEMORY_SAVE_INTERVAL_SECONDS", "60")))
    sqlite_enabled: bool = field(default_factory=lambda: os.environ.get("MEMORY_SQLITE_ENABLED", "true").lower() == "true")
    vector_enabled: bool = field(default_factory=lambda: os.environ.get("MEMORY_VECTOR_ENABLED", "true").lower() == "true")
    vector_dimensions: int = field(default_factory=lambda: int(os.environ.get("MEMORY_VECTOR_DIMENSIONS", "256")))
    search_top_k: int = field(default_factory=lambda: int(os.environ.get("MEMORY_SEARCH_TOP_K", "8")))


@dataclass
class SleepConfig:
    """V6 sleep / dream replay / memory consolidation settings."""
    enabled: bool = field(default_factory=lambda: os.environ.get("SLEEP_V6_ENABLED", "true").lower() == "true")
    auto_enabled: bool = field(default_factory=lambda: os.environ.get("SLEEP_AUTO_ENABLED", "true").lower() == "true")
    auto_interval: float = field(default_factory=lambda: float(os.environ.get("SLEEP_AUTO_INTERVAL", "900")))
    idle_threshold: float = field(default_factory=lambda: float(os.environ.get("SLEEP_IDLE_THRESHOLD", "90")))
    energy_threshold: float = field(default_factory=lambda: float(os.environ.get("SLEEP_ENERGY_THRESHOLD", "0.38")))
    manual_min_gap: float = field(default_factory=lambda: float(os.environ.get("SLEEP_MANUAL_MIN_GAP", "3.0")))
    max_replay_events: int = field(default_factory=lambda: int(os.environ.get("SLEEP_MAX_REPLAY_EVENTS", "80")))
    max_dialogue_pairs: int = field(default_factory=lambda: int(os.environ.get("SLEEP_MAX_DIALOGUE_PAIRS", "24")))
    max_lessons_per_cycle: int = field(default_factory=lambda: int(os.environ.get("SLEEP_MAX_LESSONS_PER_CYCLE", "8")))


@dataclass
class EmotionConfig:
    """V4 affective state settings.

    This is not a human emotion simulator; it is a bounded internal state used
    to tune dialogue style, monologue depth, attention, and memory tags.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("EMOTION_V4_ENABLED", "true").lower() == "true")
    state_emit_interval: float = field(default_factory=lambda: float(os.environ.get("EMOTION_STATE_EMIT_INTERVAL", "4.0")))
    decay_strength: float = field(default_factory=lambda: float(os.environ.get("EMOTION_DECAY_STRENGTH", "0.985")))


@dataclass
class MonologueConfig:
    """V4 deep internal monologue settings."""
    enabled: bool = field(default_factory=lambda: os.environ.get("MONOLOGUE_V4_ENABLED", "true").lower() == "true")
    interval: float = field(default_factory=lambda: float(os.environ.get("MONOLOGUE_INTERVAL", "6.0")))


@dataclass
class KernelConfig:
    """Top-level configuration for the PCA Kernel and Web UI.

    All numeric values are in SI units unless otherwise noted.
    """
    # ------------------------------------------------------------------
    # Kernel timing
    # ------------------------------------------------------------------
    tick_rate: float = 0.1                # seconds between kernel ticks
    budget_units: int = 1000               # attention budget per tick

    # ------------------------------------------------------------------
    # Sensor frequencies (Hz)
    # ------------------------------------------------------------------
    default_sensor_hz: float = 1.0
    focused_sensor_hz: float = 10.0
    ignored_sensor_hz: float = 0.2
    ignore_threshold_sec: float = 10.0

    # ------------------------------------------------------------------
    # Subjective field defaults
    # ------------------------------------------------------------------
    subjective_field: SubjectiveFieldDefaults = field(default_factory=SubjectiveFieldDefaults)

    # ------------------------------------------------------------------
    # Web UI
    # ------------------------------------------------------------------
    web_host: str = field(default_factory=lambda: os.environ.get("BRAIN_HOST", "127.0.0.1"))
    web_port: int = field(default_factory=lambda: int(os.environ.get("BRAIN_PORT", "8000")))
    ws_reload: bool = field(default_factory=lambda: os.environ.get("BRAIN_RELOAD", "false").lower() == "true")  # dev only
    web_api_token: str = field(default_factory=lambda: os.environ.get("WEB_UI_API_TOKEN", ""))
    web_cors_origins: List[str] = field(default_factory=lambda: [
        origin.strip() for origin in os.environ.get("WEB_CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")
        if origin.strip()
    ])

    # ------------------------------------------------------------------
    # V4 affective state / monologue
    # ------------------------------------------------------------------
    emotion: EmotionConfig = field(default_factory=EmotionConfig)
    monologue: MonologueConfig = field(default_factory=MonologueConfig)

    # ------------------------------------------------------------------
    # V5 self/world model
    # ------------------------------------------------------------------
    self_model: SelfModelConfig = field(default_factory=SelfModelConfig)
    world_model: WorldModelConfig = field(default_factory=WorldModelConfig)


    # ------------------------------------------------------------------
    # V6 sleep / dream replay / memory consolidation
    # ------------------------------------------------------------------
    sleep: SleepConfig = field(default_factory=SleepConfig)

    # ------------------------------------------------------------------
    # V7 safe PC automation / tier4_actions
    # ------------------------------------------------------------------
    actions: ActionConfig = field(default_factory=ActionConfig)
    natural_actions: NaturalActionConfig = field(default_factory=NaturalActionConfig)
    code_repair: CodeRepairConfig = field(default_factory=CodeRepairConfig)
    task_chains: TaskChainConfig = field(default_factory=TaskChainConfig)

    # ------------------------------------------------------------------
    # V9.3 Web learning / search
    # ------------------------------------------------------------------
    web_learning: WebLearningConfig = field(default_factory=WebLearningConfig)

    # ------------------------------------------------------------------
    # Voice interface
    # ------------------------------------------------------------------
    voice: VoiceConfig = field(default_factory=VoiceConfig)

    # ------------------------------------------------------------------
    # Screen reading / OCR interface
    # ------------------------------------------------------------------
    screen: ScreenConfig = field(default_factory=ScreenConfig)

    # ------------------------------------------------------------------
    # V9.1 long-term memory / portable data directory
    # ------------------------------------------------------------------
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # ------------------------------------------------------------------
    # Module paths / defaults
    # ------------------------------------------------------------------
    modules: ModuleDefaults = field(default_factory=ModuleDefaults)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    persistence_dir: str = field(default_factory=_default_data_dir)

    # ------------------------------------------------------------------
    # Module auto-discovery
    # ------------------------------------------------------------------
    module_auto_discover: bool = True
    module_tier_paths: List[str] = field(default_factory=lambda: [
        str(Path(__file__).parent / "modules" / "tier1_essential"),
        str(Path(__file__).parent / "modules" / "tier2_perception"),
        str(Path(__file__).parent / "modules" / "tier3_reasoning"),
        str(Path(__file__).parent / "modules" / "tier4_actions"),
        str(Path(__file__).parent / "modules" / "tier5_evolution"),
    ])

    # ------------------------------------------------------------------
    # LLM Router
    # ------------------------------------------------------------------
    llm: LLMRouterConfig = field(default_factory=LLMRouterConfig)

    # ------------------------------------------------------------------
    # Safety Constitution
    # ------------------------------------------------------------------
    safety_default_level: int = 1        # L1_READ_SCREEN — default at startup
    sandbox_extra_paths: List[str] = field(default_factory=list)  # user-added write paths
    safety_audit_enabled: bool = True    # set False only for unit-test environments

    # ------------------------------------------------------------------
    # Convenience property
    # ------------------------------------------------------------------
    @property
    def web_bind(self) -> tuple[str, int]:
        """Return (host, port) as a tuple for Uvicorn / FastAPI."""
        return (self.web_host, self.web_port)


# Export a default singleton configuration instance
config = KernelConfig()
