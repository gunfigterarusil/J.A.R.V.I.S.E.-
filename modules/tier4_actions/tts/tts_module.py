"""Tier 4 Action: Text-to-Speech Module.

Listens for response_generated events and speaks them when voice mode is enabled.
Backend order:
- auto: Piper first, then pyttsx3 fallback
- piper: Piper only
- pyttsx3: pyttsx3 only
- none: disabled
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Protocol

from core import CognitiveModule, CognitiveEvent as Event, Priority
from interfaces.voice.piper_tts import PiperTTS, PiperUnavailable
from interfaces.voice.pyttsx3_tts import Pyttsx3TTS, Pyttsx3Unavailable

logger = logging.getLogger("tts")


class SpeechBackend(Protocol):
    def speak(self, text: str) -> Any: ...


class TTSModule(CognitiveModule):
    MODULE_DESCRIPTION = "Voice output through Piper TTS with pyttsx3 fallback"
    MODULE_VERSION = "0.2.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="tts",
            cost={"cpu": 0.20, "gpu": 0.0, "ram": 0.10},
        )
        self._backends: list[tuple[str, SpeechBackend]] = []
        self._voice_enabled = False
        self._speak_lock = asyncio.Lock()
        self._last_error = ""
        self._active_backend = ""
        self._configured_backend = "auto"

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "voice", None)
        self._configured_backend = str(getattr(cfg, "tts_backend", "auto") or "auto").strip().lower()
        self._voice_enabled = bool(
            getattr(cfg, "enabled", False)
            and getattr(cfg, "tts_enabled", True)
            and self._configured_backend != "none"
        )
        kernel.event_bus.register_consumer(
            self.module_id,
            ["response_generated", "tts_say"],
        )
        if not self._voice_enabled:
            logger.info("[TTS] Disabled. Start with --voice and VOICE_TTS_ENABLED=true to enable output.")
            return

        if self._configured_backend not in {"auto", "piper", "pyttsx3", "none"}:
            logger.warning("[TTS] Unknown VOICE_TTS_BACKEND=%r; using auto", self._configured_backend)
            self._configured_backend = "auto"

        piper = PiperTTS(
            executable=getattr(cfg, "piper_executable", "piper"),
            model_path=getattr(cfg, "piper_model_path", ""),
            config_path=getattr(cfg, "piper_config_path", ""),
            speaker=getattr(cfg, "piper_speaker", ""),
            length_scale=getattr(cfg, "piper_length_scale", 1.0),
            noise_scale=getattr(cfg, "piper_noise_scale", 0.667),
            noise_w=getattr(cfg, "piper_noise_w", 0.8),
            output_dir=getattr(cfg, "piper_output_dir", ""),
        )
        pyttsx3_backend = Pyttsx3TTS(
            voice_id=getattr(cfg, "pyttsx3_voice_id", ""),
            rate=getattr(cfg, "pyttsx3_rate", 175),
            volume=getattr(cfg, "pyttsx3_volume", 1.0),
        )

        if self._configured_backend == "piper":
            self._backends = [("piper", piper)]
        elif self._configured_backend == "pyttsx3":
            self._backends = [("pyttsx3", pyttsx3_backend)]
        else:
            self._backends = [("piper", piper), ("pyttsx3", pyttsx3_backend)]

        logger.info("[TTS] Enabled with backend mode: %s", self._configured_backend)

    async def on_event(self, event: Event) -> None:
        if not self._voice_enabled or not self._backends:
            return
        if event.type not in {"response_generated", "tts_say"}:
            return
        text = str(event.data.get("text", "")).strip()
        if not text:
            return
        await self._speak(text)

    async def _speak(self, text: str) -> None:
        async with self._speak_lock:
            errors: list[str] = []
            for name, backend in self._backends:
                try:
                    await asyncio.to_thread(backend.speak, text)
                    self._active_backend = name
                    self._last_error = ""
                    if self.kernel:
                        self.kernel.event_bus.emit(
                            Event(
                                type="tts_spoken",
                                data={"text": text[:300], "backend": name},
                                source_module=self.module_id,
                            ),
                            Priority.BACKGROUND,
                        )
                    return
                except (PiperUnavailable, Pyttsx3Unavailable) as exc:
                    msg = f"{name}: {exc}"
                    errors.append(msg)
                    if self._configured_backend == "auto":
                        logger.warning("[TTS] %s; trying fallback if available", msg)
                    else:
                        logger.error("[TTS] %s", msg)
                except Exception as exc:
                    msg = f"{name}: unexpected error: {exc}"
                    errors.append(msg)
                    logger.exception("[TTS] %s", msg)

            self._last_error = " | ".join(errors) or "No TTS backend available"
            logger.error("[TTS] Could not speak. %s", self._last_error)
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="tts_error",
                        data={"error": self._last_error},
                        source_module=self.module_id,
                    ),
                    Priority.BACKGROUND,
                )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "voice_enabled": self._voice_enabled,
                "backend_mode": self._configured_backend,
                "active_backend": self._active_backend,
                "available_backends": [name for name, _ in self._backends],
                "last_error": self._last_error,
            }
        )
        return base


def create_module() -> TTSModule:
    return TTSModule()
