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
from typing import List


def _load_dotenv_fallback() -> None:
    """Load .env without requiring python-dotenv. python-dotenv is used if installed."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        return
    except Exception:
        pass
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('\"').strip("'")
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _resolve_app_path(value: str, default: str) -> str:
    value = value or default
    path = Path(value).expanduser()
    if _env_bool("JAV_PORTABLE", False) and not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return str(path)


_load_dotenv_fallback()


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
    routing: dict = field(default_factory=dict)

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
    anthropic_model: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # llama.cpp server
    llamacpp_host: str = field(default_factory=lambda: os.environ.get("LLAMACPP_HOST", "http://localhost:8080"))

    # Generation defaults
    default_timeout: float = 60.0
    max_tokens: int = 2048
    temperature: float = 0.7


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
    web_host: str = field(default_factory=lambda: os.environ.get("WEB_HOST", "127.0.0.1"))
    web_port: int = field(default_factory=lambda: _env_int("WEB_PORT", 8000))
    ws_reload: bool = False             # auto-reload on code change (dev only)

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
    persistence_dir: str = field(default_factory=lambda: _resolve_app_path(os.environ.get("JARVIS_DATA_DIR", ""), "~/.jarvis_brain"))

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
    safety_default_level: int = field(default_factory=lambda: _env_int("SAFETY_DEFAULT_LEVEL", 1))        # L1_READ_SCREEN — default at startup
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
