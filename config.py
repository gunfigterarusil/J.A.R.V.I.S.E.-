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
    screenshot_dir: str = field(default_factory=lambda: os.environ.get("SCREENSHOT_DIR", ""))
    ocr_backend: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_BACKEND", "tesseract"))  # tesseract for V3 MVP
    ocr_language: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_LANGUAGE", "eng"))
    ocr_config: str = field(default_factory=lambda: os.environ.get("SCREEN_OCR_CONFIG", "--psm 6"))
    save_screenshots: bool = field(default_factory=lambda: os.environ.get("SCREEN_SAVE_SCREENSHOTS", "true").lower() == "true")
    max_ocr_chars: int = field(default_factory=lambda: int(os.environ.get("SCREEN_MAX_OCR_CHARS", "7000")))


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
    # Voice interface
    # ------------------------------------------------------------------
    voice: VoiceConfig = field(default_factory=VoiceConfig)

    # ------------------------------------------------------------------
    # Screen reading / OCR interface
    # ------------------------------------------------------------------
    screen: ScreenConfig = field(default_factory=ScreenConfig)

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
    persistence_dir: str = "~/.jarvis_brain"

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
