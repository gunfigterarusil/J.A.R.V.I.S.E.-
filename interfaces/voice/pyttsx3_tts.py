"""pyttsx3 fallback TTS wrapper for offline voice output."""
from __future__ import annotations

import logging

logger = logging.getLogger("voice.pyttsx3")


class Pyttsx3Unavailable(RuntimeError):
    """Raised when pyttsx3 is not installed or cannot initialize."""


class Pyttsx3TTS:
    """Speak text locally with pyttsx3.

    pyttsx3 is used as a fallback when Piper is missing or not configured.
    It uses the operating system's available voices, so quality depends on the OS.
    """

    def __init__(self, voice_id: str = "", rate: int = 175, volume: float = 1.0) -> None:
        self.voice_id = voice_id
        self.rate = int(rate)
        self.volume = max(0.0, min(1.0, float(volume)))
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise Pyttsx3Unavailable(
                "pyttsx3 is not installed. Run: pip install pyttsx3"
            ) from exc

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)
            engine.setProperty("volume", self.volume)
            if self.voice_id:
                engine.setProperty("voice", self.voice_id)
            self._engine = engine
            return engine
        except Exception as exc:  # pragma: no cover - depends on host audio drivers
            raise Pyttsx3Unavailable(f"pyttsx3 failed to initialize: {exc}") from exc

    def speak(self, text: str, stop_event=None) -> None:  # stop_event not supported
        text = (text or "").strip()
        if not text:
            return
        engine = self._get_engine()
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:  # pragma: no cover - depends on host audio drivers
            raise Pyttsx3Unavailable(f"pyttsx3 failed to speak: {exc}") from exc
