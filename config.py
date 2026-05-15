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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

# Runtime path model:
# - RESOURCE_ROOT: where bundled/source Python resources live. In a PyInstaller build
#   this is the temporary/internal resource directory; in source mode it is this folder.
# - APP_ROOT: where the user placed the application. Portable data and .env live here,
#   so the whole folder can be moved to another drive and keep working.
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PROJECT_ROOT = RESOURCE_ROOT

try:
    from dotenv import load_dotenv
    # Prefer .env next to the app/exe. Fall back to normal discovery in source/dev mode.
    app_env = APP_ROOT / ".env"
    if app_env.exists():
        load_dotenv(app_env, override=False)
    else:
        load_dotenv(override=False)
except ImportError:
    # python-dotenv is optional at runtime; environment variables still work without it.
    pass


def _app_path(value: str) -> str:
    """Resolve relative portable paths against the movable application folder."""
    value = (value or "").strip()
    if not value:
        return value
    p = Path(value).expanduser()
    if p.is_absolute():
        return str(p)
    return str((APP_ROOT / p).resolve())


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
        return _app_path(explicit)
    if _env_bool("JAV_PORTABLE", "false"):
        return _app_path("data/brain")
    return "~/.jarvis_brain"


def _default_workspace_dir() -> str:
    explicit = os.environ.get("ACTION_WORKSPACE_PATH", "").strip()
    if explicit:
        return _app_path(explicit)
    if _env_bool("JAV_PORTABLE", "false"):
        return _app_path("data/workspace")
    return "~/jarvis_workspace"


def _default_screenshot_dir() -> str:
    explicit = os.environ.get("SCREENSHOT_DIR", "").strip()
    if explicit:
        return _app_path(explicit)
    if _env_bool("JAV_PORTABLE", "false"):
        return _app_path("data/screenshots")
    return ""


@dataclass
class SafetyConstitutionConfig:
    """V15.4 — Asimov-inspired ethical safety principles.

    Technical hard rules (no_mass_deletion, no_disk_operations, etc.) are
    always active and cannot be toggled.  Ethical rules can be controlled
    per-category here.
    """
    ethical_rules_enabled: bool = field(
        default_factory=lambda: _env_bool("SAFETY_CONSTITUTION_ETHICAL_RULES", "true")
    )
    inject_principles_into_prompts: bool = field(
        default_factory=lambda: _env_bool("SAFETY_INJECT_PRINCIPLES", "true")
    )
    no_private_data: bool = field(
        default_factory=lambda: _env_bool("SAFETY_ETHICS_PRIVATE_DATA", "true")
    )
    no_security_prefs: bool = field(
        default_factory=lambda: _env_bool("SAFETY_ETHICS_SECURITY_PREFS", "true")
    )
    no_silent_background: bool = field(
        default_factory=lambda: _env_bool("SAFETY_ETHICS_TRANSPARENCY", "true")
    )
    no_data_harm: bool = field(
        default_factory=lambda: _env_bool("SAFETY_ETHICS_DATA_HARM", "true")
    )


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
        str(RESOURCE_ROOT / "modules"),
    ])
    default_modules: List[str] = field(default_factory=list)


@dataclass
class LLMRouterConfig:
    """V10 modular model/API router configuration.

    Legacy provider variables are still supported, but V10 adds role-based
    routing so each subsystem can use a different model/API:
      fast, reason, code, critic, vision, embedding, action.

    Examples:
      MODEL_PROFILE=offline
      MODEL_CODE_PROVIDER=ollama
      MODEL_CODE_NAME=qwen2.5-coder:7b
      MODEL_VISION_PROVIDER=gemini
      MODEL_VISION_NAME=gemini-2.0-flash
    """
    routing: Dict[str, str] = field(default_factory=dict)

    # High-level profile: offline|balanced|power|cheap_cloud|code|voice_companion|custom
    model_profile: str = field(default_factory=lambda: os.environ.get("MODEL_PROFILE", "offline"))

    # Role provider/model overrides. Provider values: ollama|openai|gemini|anthropic|llamacpp|null
    fast_provider: str = field(default_factory=lambda: os.environ.get("MODEL_FAST_PROVIDER", ""))
    fast_model: str = field(default_factory=lambda: os.environ.get("MODEL_FAST_NAME", ""))
    reason_provider: str = field(default_factory=lambda: os.environ.get("MODEL_REASON_PROVIDER", ""))
    reason_model: str = field(default_factory=lambda: os.environ.get("MODEL_REASON_NAME", ""))
    code_provider: str = field(default_factory=lambda: os.environ.get("MODEL_CODE_PROVIDER", ""))
    code_model: str = field(default_factory=lambda: os.environ.get("MODEL_CODE_NAME", ""))
    critic_provider: str = field(default_factory=lambda: os.environ.get("MODEL_CRITIC_PROVIDER", ""))
    critic_model: str = field(default_factory=lambda: os.environ.get("MODEL_CRITIC_NAME", ""))
    vision_provider: str = field(default_factory=lambda: os.environ.get("MODEL_VISION_PROVIDER", ""))
    vision_model: str = field(default_factory=lambda: os.environ.get("MODEL_VISION_NAME", ""))
    embedding_provider: str = field(default_factory=lambda: os.environ.get("MODEL_EMBEDDING_PROVIDER", ""))
    embedding_model: str = field(default_factory=lambda: os.environ.get("MODEL_EMBEDDING_NAME", ""))
    action_provider: str = field(default_factory=lambda: os.environ.get("MODEL_ACTION_PROVIDER", ""))
    action_model: str = field(default_factory=lambda: os.environ.get("MODEL_ACTION_NAME", ""))

    # Router behavior
    model_health_check_enabled: bool = field(default_factory=lambda: _env_bool("MODEL_HEALTH_CHECK_ENABLED", "true"))
    model_fallback_enabled: bool = field(default_factory=lambda: _env_bool("MODEL_FALLBACK_ENABLED", "true"))
    model_status_emit_enabled: bool = field(default_factory=lambda: _env_bool("MODEL_STATUS_EMIT_ENABLED", "true"))

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
    default_timeout: float = field(default_factory=lambda: float(os.environ.get("MODEL_DEFAULT_TIMEOUT", "60")))
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("MODEL_MAX_TOKENS", "2048")))
    temperature: float = field(default_factory=lambda: float(os.environ.get("MODEL_TEMPERATURE", "0.7")))


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
    input_mode: str = field(default_factory=lambda: os.environ.get("VOICE_INPUT_MODE", "continuous"))  # continuous|push_to_talk
    push_to_talk_prompt: str = field(default_factory=lambda: os.environ.get("VOICE_PUSH_TO_TALK_PROMPT", "Press Enter to speak, or type q + Enter to quit: "))
    vad_enabled: bool = field(default_factory=lambda: os.environ.get("VOICE_VAD_ENABLED", "true").lower() == "true")
    vad_max_silence_ms: int = field(default_factory=lambda: int(os.environ.get("VOICE_VAD_MAX_SILENCE_MS", "700")))
    vad_min_speech_ms: int = field(default_factory=lambda: int(os.environ.get("VOICE_VAD_MIN_SPEECH_MS", "150")))
    vad_max_duration_s: float = field(default_factory=lambda: float(os.environ.get("VOICE_VAD_MAX_DURATION_S", "30")))
    interrupt_phrases: str = field(default_factory=lambda: os.environ.get("VOICE_INTERRUPT_PHRASES", "stop,зупинись,стоп,замовкни,тихо"))
    mute_phrases: str = field(default_factory=lambda: os.environ.get("VOICE_MUTE_PHRASES", "mute,мовчи,замовкни,не говори"))
    unmute_phrases: str = field(default_factory=lambda: os.environ.get("VOICE_UNMUTE_PHRASES", "unmute,говори,можеш говорити"))
    print_transcript: bool = field(default_factory=lambda: os.environ.get("VOICE_PRINT_TRANSCRIPT", "true").lower() == "true")
    response_timeout: float = field(default_factory=lambda: float(os.environ.get("VOICE_RESPONSE_TIMEOUT", "90")))
    tts_wait_timeout: float = field(default_factory=lambda: float(os.environ.get("VOICE_TTS_WAIT_TIMEOUT", "45")))
    listen_after_response_delay: float = field(default_factory=lambda: float(os.environ.get("VOICE_LISTEN_AFTER_RESPONSE_DELAY", "0.35")))

    # Text-to-speech
    tts_enabled: bool = field(default_factory=lambda: os.environ.get("VOICE_TTS_ENABLED", "true").lower() == "true")
    start_muted: bool = field(default_factory=lambda: os.environ.get("VOICE_START_MUTED", "false").lower() == "true")
    status_file: str = field(default_factory=lambda: os.environ.get("VOICE_STATUS_FILE", ""))
    tts_backend: str = field(default_factory=lambda: os.environ.get("VOICE_TTS_BACKEND", "auto"))  # auto|elevenlabs|xtts|piper|pyttsx3|none

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

    # Back-channel responses (short acknowledgments while LLM is thinking)
    back_channel_enabled: bool = field(default_factory=lambda: os.environ.get("VOICE_BACK_CHANNEL", "true").lower() == "true")
    back_channel_language: str = field(default_factory=lambda: os.environ.get("VOICE_BACK_CHANNEL_LANG", "uk"))

    # Acoustic wake word detection — openWakeWord (free, local, CPU-only)
    # Set VOICE_WAKE_WORD_DETECTOR=openwakeword and download a model to enable.
    # Model can be a community model name ("hey_jarvis") or an absolute .tflite/.onnx path.
    wake_word_detector: str = field(default_factory=lambda: os.environ.get("VOICE_WAKE_WORD_DETECTOR", "none").strip().lower())
    wake_word_model: str = field(default_factory=lambda: os.environ.get("VOICE_WAKE_WORD_MODEL", "hey_jarvis"))
    wake_word_threshold: float = field(default_factory=lambda: float(os.environ.get("VOICE_WAKE_WORD_THRESHOLD", "0.5")))
    wake_word_ack: bool = field(default_factory=lambda: os.environ.get("VOICE_WAKE_WORD_ACK", "true").lower() == "true")

    # Phase 3C — Emotional Voice Modulation
    # Emotion (arousal/frustration) and hormones (cortisol/oxytocin/adrenaline) modulate
    # TTS speed and stability in real time. strength=0 disables, strength=1 is full effect.
    emotional_tts_enabled: bool = field(default_factory=lambda: os.environ.get("VOICE_EMOTIONAL_TTS", "true").lower() == "true")
    emotional_tts_strength: float = field(default_factory=lambda: float(os.environ.get("VOICE_EMOTIONAL_TTS_STRENGTH", "1.0")))

    # XTTS v2 — Coqui local neural TTS (pip install TTS)
    # Supports voice cloning from a 6+ sec WAV sample, Ukrainian language natively
    xtts_model: str = field(default_factory=lambda: os.environ.get("JAV_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2"))
    xtts_speaker_wav: str = field(default_factory=lambda: os.environ.get("JAV_XTTS_SPEAKER_WAV", ""))
    xtts_language: str = field(default_factory=lambda: os.environ.get("JAV_XTTS_LANGUAGE", "uk"))
    xtts_device: str = field(default_factory=lambda: os.environ.get("JAV_XTTS_DEVICE", "auto"))

    # ElevenLabs — cloud premium TTS (pip install elevenlabs)
    # Lowest latency cloud option (~400ms to first audio), streaming supported
    elevenlabs_api_key: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_VOICE_ID", "Rachel"))
    elevenlabs_model: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5"))
    elevenlabs_streaming: bool = field(default_factory=lambda: os.environ.get("ELEVENLABS_STREAMING", "true").lower() == "true")
    elevenlabs_stability: float = field(default_factory=lambda: float(os.environ.get("ELEVENLABS_STABILITY", "0.5")))
    elevenlabs_similarity: float = field(default_factory=lambda: float(os.environ.get("ELEVENLABS_SIMILARITY", "0.75")))


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
    ocr_backend: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_BACKEND", "tesseract"))  # tesseract for V3/V9.6 MVP
    ocr_language: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_LANGUAGE", "eng"))
    ocr_config: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_CONFIG", "--psm 6"))
    save_screenshots: bool = field(default_factory=lambda: os.environ.get("SCREEN_SAVE_SCREENSHOTS", "true").lower() == "true")
    max_ocr_chars: int = field(default_factory=lambda: int(os.environ.get("SCREEN_MAX_OCR_CHARS", "7000")))

    # V9.6 GUI understanding / real-vision-lite. Understanding only; no clicks.
    vision_enabled: bool = field(default_factory=lambda: os.environ.get("SCREEN_VISION_ENABLED", "true").lower() == "true")
    gui_understanding_enabled: bool = field(default_factory=lambda: os.environ.get("SCREEN_GUI_UNDERSTANDING_ENABLED", "true").lower() == "true")
    active_window_enabled: bool = field(default_factory=lambda: os.environ.get("SCREEN_ACTIVE_WINDOW_ENABLED", "true").lower() == "true")
    max_ui_elements: int = field(default_factory=lambda: int(os.environ.get("SCREEN_MAX_UI_ELEMENTS", "40")))
    min_ui_confidence: int = field(default_factory=lambda: int(os.environ.get("SCREEN_MIN_UI_CONFIDENCE", "35")))

    # Phase 3B — Ambient Perception (requires auto_watch_enabled=true)
    ambient_watch_interval: float = field(default_factory=lambda: float(os.environ.get("SCREEN_AMBIENT_INTERVAL", "8.0")))
    ambient_min_gap_after_speech: float = field(default_factory=lambda: float(os.environ.get("SCREEN_AMBIENT_SPEECH_GAP", "3.0")))
    ambient_proactive: bool = field(default_factory=lambda: os.environ.get("SCREEN_AMBIENT_PROACTIVE", "true").lower() == "true")




@dataclass
class PersonaConfig:
    """Phase 2 — adaptive character that grows with the user.

    UserProfileEngine learns who the user is (name, language, style, interests).
    PersonaEvolution tracks relationship depth and shared references.
    Both are fully local — data stays in ~/.jarvis_brain/user_profile.json.
    """
    enabled: bool = field(default_factory=lambda: _env_bool("PERSONA_ENABLED", "true"))
    auto_extract_name: bool = field(default_factory=lambda: _env_bool("PERSONA_AUTO_EXTRACT_NAME", "true"))
    persona_name: str = field(default_factory=lambda: os.environ.get("PERSONA_NAME", ""))
    persona_notes_update_every: int = field(default_factory=lambda: int(os.environ.get("PERSONA_NOTES_UPDATE_EVERY", "5")))
    relationship_depth_increment: float = field(default_factory=lambda: float(os.environ.get("PERSONA_DEPTH_INCREMENT", "0.001")))
    max_shared_references: int = field(default_factory=lambda: int(os.environ.get("PERSONA_MAX_SHARED_REFS", "20")))
    max_evolution_log: int = field(default_factory=lambda: int(os.environ.get("PERSONA_MAX_EVOLUTION_LOG", "5")))


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
    """V13 advanced autonomous/guided task orchestrator settings.

    V13 decomposes broad goals into strategy A/B/C, safe steps, verification,
    retry and rollback guidance. External effects still go through V7 safety
    gates. Guided mode is default; auto mode can continue low-risk verified
    steps until it hits a safety confirmation or completion.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_ENABLED", "true").lower() == "true")
    auto_step_default: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_AUTO_STEP_DEFAULT", "false").lower() == "true")
    max_steps: int = field(default_factory=lambda: int(os.environ.get("TASK_CHAINS_MAX_STEPS", "12")))
    step_timeout_seconds: float = field(default_factory=lambda: float(os.environ.get("TASK_CHAINS_STEP_TIMEOUT_SECONDS", "120")))
    max_retries_per_step: int = field(default_factory=lambda: int(os.environ.get("TASK_CHAINS_MAX_RETRIES_PER_STEP", "2")))
    verifier_enabled: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_VERIFIER_ENABLED", "true").lower() == "true")
    rollback_enabled: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_ROLLBACK_ENABLED", "true").lower() == "true")
    strategy_count: int = field(default_factory=lambda: int(os.environ.get("TASK_CHAINS_STRATEGY_COUNT", "3")))
    auto_continue_after_safe_step: bool = field(default_factory=lambda: os.environ.get("TASK_CHAINS_AUTO_CONTINUE_AFTER_SAFE_STEP", "true").lower() == "true")


@dataclass
class GuiAutomationConfig:
    """V9.7 safe general GUI automation settings.

    This enables a small-action GUI loop: observe screen -> LLM chooses one
    allowed GUI step -> V7 safety -> execute -> observe again. It is not a
    hardcoded YouTube/browser script; YouTube is only one possible task.
    """
    enabled: bool = field(default_factory=lambda: os.environ.get("GUI_AUTOMATION_ENABLED", "true").lower() == "true")
    auto_enabled: bool = field(default_factory=lambda: os.environ.get("GUI_AUTOMATION_AUTO_ENABLED", "false").lower() == "true")
    max_steps: int = field(default_factory=lambda: int(os.environ.get("GUI_AUTOMATION_MAX_STEPS", "12")))
    step_delay_seconds: float = field(default_factory=lambda: float(os.environ.get("GUI_AUTOMATION_STEP_DELAY_SECONDS", "1.0")))
    require_confirmation: bool = field(default_factory=lambda: os.environ.get("GUI_AUTOMATION_REQUIRE_CONFIRMATION", "true").lower() == "true")
    block_sensitive: bool = field(default_factory=lambda: os.environ.get("GUI_AUTOMATION_BLOCK_SENSITIVE", "true").lower() == "true")
    verify_after_action: bool = field(default_factory=lambda: os.environ.get("GUI_AUTOMATION_VERIFY_AFTER_ACTION", "true").lower() == "true")
    screenshot_audit: bool = field(default_factory=lambda: os.environ.get("GUI_AUTOMATION_SCREENSHOT_AUDIT", "true").lower() == "true")
    semantic_click_threshold: int = field(default_factory=lambda: int(os.environ.get("GUI_AUTOMATION_SEMANTIC_CLICK_THRESHOLD", "35")))
    max_retries_per_step: int = field(default_factory=lambda: int(os.environ.get("GUI_AUTOMATION_MAX_RETRIES_PER_STEP", "2")))
    allowed_actions: List[str] = field(default_factory=lambda: [
        x.strip() for x in os.environ.get(
            "GUI_AUTOMATION_ALLOWED_ACTIONS",
            "observe,done,open_url,open_app,click_xy,click_text,type_text,press,hotkey,scroll,wait"
        ).split(",") if x.strip()
    ])


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
class SkillLearningConfig:
    """V14 procedural skill learning and lightweight knowledge graph settings."""
    enabled: bool = field(default_factory=lambda: _env_bool("SKILL_LEARNING_ENABLED", "true"))
    auto_learn: bool = field(default_factory=lambda: _env_bool("SKILL_AUTO_LEARN_ENABLED", "true"))
    min_confidence: float = field(default_factory=lambda: float(os.environ.get("SKILL_MIN_CONFIDENCE", "0.55")))
    max_skills: int = field(default_factory=lambda: int(os.environ.get("SKILL_MAX_SKILLS", "1000")))
    max_graph_edges: int = field(default_factory=lambda: int(os.environ.get("KNOWLEDGE_GRAPH_MAX_EDGES", "5000")))

@dataclass
class SystemMonitorConfig:
    """V11 local machine/system/model monitoring settings."""
    enabled: bool = field(default_factory=lambda: _env_bool("SYSTEM_MONITOR_ENABLED", "true"))
    interval_seconds: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_MONITOR_INTERVAL_SECONDS", "20")))
    alert_cooldown_seconds: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_ALERT_COOLDOWN_SECONDS", "300")))
    cpu_warn_percent: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_CPU_WARN_PERCENT", "90")))
    memory_warn_percent: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_MEMORY_WARN_PERCENT", "88")))
    disk_warn_percent: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_DISK_WARN_PERCENT", "90")))
    temp_warn_c: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_TEMP_WARN_C", "85")))
    check_network: bool = field(default_factory=lambda: _env_bool("SYSTEM_CHECK_NETWORK", "true"))
    check_ollama: bool = field(default_factory=lambda: _env_bool("SYSTEM_CHECK_OLLAMA", "true"))
    check_models: bool = field(default_factory=lambda: _env_bool("SYSTEM_CHECK_MODELS", "true"))
    network_timeout_seconds: float = field(default_factory=lambda: float(os.environ.get("SYSTEM_NETWORK_TIMEOUT_SECONDS", "3")))


@dataclass
class ProactiveConfig:
    """V11 proactive companion settings. Conservative by default."""
    enabled: bool = field(default_factory=lambda: _env_bool("PROACTIVE_COMPANION_ENABLED", "true"))
    chat_notifications: bool = field(default_factory=lambda: _env_bool("PROACTIVE_CHAT_NOTIFICATIONS", "true"))
    speak_notifications: bool = field(default_factory=lambda: _env_bool("PROACTIVE_SPEAK_NOTIFICATIONS", "false"))
    min_importance: float = field(default_factory=lambda: float(os.environ.get("PROACTIVE_MIN_IMPORTANCE", "0.55")))
    cooldown_seconds: float = field(default_factory=lambda: float(os.environ.get("PROACTIVE_COOLDOWN_SECONDS", "300")))
    notify_task_progress: bool = field(default_factory=lambda: _env_bool("PROACTIVE_NOTIFY_TASK_PROGRESS", "true"))
    daily_summary_enabled: bool = field(default_factory=lambda: _env_bool("PROACTIVE_DAILY_SUMMARY_ENABLED", "true"))
    daily_summary_interval_seconds: float = field(default_factory=lambda: float(os.environ.get("PROACTIVE_DAILY_SUMMARY_INTERVAL_SECONDS", "86400")))
    do_not_disturb: bool = field(default_factory=lambda: _env_bool("PROACTIVE_DO_NOT_DISTURB", "false"))
    startup_grace_seconds: float = field(default_factory=lambda: float(os.environ.get("PROACTIVE_STARTUP_GRACE_SECONDS", "15")))


@dataclass
class RuntimeConfig:
    """V9.5 service/runtime stability settings.

    These settings make JAV safer to run as a long-lived local assistant:
    heartbeat files for watchdogs, rotating logs, lightweight health checks,
    optional auto-sleep/consolidation on shutdown, and service-friendly paths.
    """
    service_mode: bool = field(default_factory=lambda: _env_bool("JAV_SERVICE_MODE", "false"))
    watchdog_enabled: bool = field(default_factory=lambda: _env_bool("JAV_WATCHDOG_ENABLED", "true"))
    heartbeat_interval_seconds: float = field(default_factory=lambda: float(os.environ.get("RUNTIME_HEARTBEAT_INTERVAL_SECONDS", "10")))
    heartbeat_stale_seconds: float = field(default_factory=lambda: float(os.environ.get("RUNTIME_HEARTBEAT_STALE_SECONDS", "45")))
    health_check_interval_seconds: float = field(default_factory=lambda: float(os.environ.get("RUNTIME_HEALTH_CHECK_INTERVAL_SECONDS", "30")))
    auto_sleep_on_shutdown: bool = field(default_factory=lambda: _env_bool("RUNTIME_AUTO_SLEEP_ON_SHUTDOWN", "true"))
    log_to_file: bool = field(default_factory=lambda: _env_bool("RUNTIME_LOG_TO_FILE", "true"))
    log_dir: str = field(default_factory=lambda: os.environ.get("RUNTIME_LOG_DIR", ""))
    log_max_bytes: int = field(default_factory=lambda: int(os.environ.get("RUNTIME_LOG_MAX_BYTES", "2097152")))
    log_backup_count: int = field(default_factory=lambda: int(os.environ.get("RUNTIME_LOG_BACKUP_COUNT", "5")))
    pid_file: str = field(default_factory=lambda: os.environ.get("RUNTIME_PID_FILE", ""))
    heartbeat_file: str = field(default_factory=lambda: os.environ.get("RUNTIME_HEARTBEAT_FILE", ""))
    crash_report_file: str = field(default_factory=lambda: os.environ.get("RUNTIME_CRASH_REPORT_FILE", ""))
    max_restart_attempts: int = field(default_factory=lambda: int(os.environ.get("WATCHDOG_MAX_RESTART_ATTEMPTS", "20")))
    restart_delay_seconds: float = field(default_factory=lambda: float(os.environ.get("WATCHDOG_RESTART_DELAY_SECONDS", "5")))

    def resolve_log_dir(self, data_dir: str) -> str:
        if self.log_dir.strip():
            return self.log_dir
        return str(Path(data_dir).expanduser() / "logs")

    def resolve_pid_file(self, data_dir: str) -> str:
        if self.pid_file.strip():
            return self.pid_file
        return str(Path(data_dir).expanduser() / "runtime.pid")

    def resolve_heartbeat_file(self, data_dir: str) -> str:
        if self.heartbeat_file.strip():
            return self.heartbeat_file
        return str(Path(data_dir).expanduser() / "runtime_heartbeat.json")

    def resolve_crash_report_file(self, data_dir: str) -> str:
        if self.crash_report_file.strip():
            return self.crash_report_file
        return str(Path(data_dir).expanduser() / "runtime_crash_report.json")


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
    # Phase 2 — adaptive persona (UserProfileEngine + PersonaEvolution)
    # ------------------------------------------------------------------
    persona: PersonaConfig = field(default_factory=PersonaConfig)


    # ------------------------------------------------------------------
    # V6 sleep / dream replay / memory consolidation
    # ------------------------------------------------------------------
    sleep: SleepConfig = field(default_factory=SleepConfig)

    # ------------------------------------------------------------------
    # V7 safe PC automation / tier4_actions
    # ------------------------------------------------------------------
    actions: ActionConfig = field(default_factory=ActionConfig)
    gui_automation: GuiAutomationConfig = field(default_factory=GuiAutomationConfig)
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
    # V14 skill learning + knowledge graph
    # ------------------------------------------------------------------
    skills: SkillLearningConfig = field(default_factory=SkillLearningConfig)

    # ------------------------------------------------------------------
    # V11 system monitor + proactive companion
    # ------------------------------------------------------------------
    system_monitor: SystemMonitorConfig = field(default_factory=SystemMonitorConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)

    # ------------------------------------------------------------------
    # V9.5 runtime / service mode / watchdog
    # ------------------------------------------------------------------
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

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
        str(RESOURCE_ROOT / "modules" / "tier1_essential"),
        str(RESOURCE_ROOT / "modules" / "tier2_perception"),
        str(RESOURCE_ROOT / "modules" / "tier3_reasoning"),
        str(RESOURCE_ROOT / "modules" / "tier4_actions"),
        str(RESOURCE_ROOT / "modules" / "tier5_evolution"),
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
    safety_constitution: SafetyConstitutionConfig = field(
        default_factory=SafetyConstitutionConfig
    )

    # ------------------------------------------------------------------
    # Convenience property
    # ------------------------------------------------------------------
    @property
    def web_bind(self) -> tuple[str, int]:
        """Return (host, port) as a tuple for Uvicorn / FastAPI."""
        return (self.web_host, self.web_port)


# Export a default singleton configuration instance
config = KernelConfig()
