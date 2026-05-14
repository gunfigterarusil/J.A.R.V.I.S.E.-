"""Voice loop: microphone -> STT -> user_utterance event.

TTS is handled by modules/tier4_actions/tts/tts_module.py, which listens for
response_generated events.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from core.event_bus import CognitiveEvent as Event, Priority
from interfaces.voice.stt import FasterWhisperSTT, STTUnavailable

logger = logging.getLogger("voice.loop")


class VoiceLoop:
    """Continuously listens to the microphone and emits user_utterance events."""

    def __init__(self, kernel) -> None:
        self.kernel = kernel
        cfg = getattr(kernel.config, "voice", None)
        self.cfg = cfg
        self.wake_word = str(getattr(cfg, "wake_word", "") or "").strip().lower()
        self.print_transcript = bool(getattr(cfg, "print_transcript", True))
        self._running = False
        self._stt = FasterWhisperSTT(
            model_size=getattr(cfg, "stt_model", "small"),
            device=getattr(cfg, "stt_device", "cpu"),
            compute_type=getattr(cfg, "stt_compute_type", "int8"),
            language=getattr(cfg, "stt_language", ""),
            sample_rate=getattr(cfg, "sample_rate", 16000),
            record_seconds=getattr(cfg, "record_seconds", 5.0),
            energy_threshold=getattr(cfg, "energy_threshold", 0.005),
        )

    async def run(self) -> None:
        self._running = True
        logger.info("[Voice] Voice loop started. Speak into the microphone. Ctrl+C to stop.")
        if self.wake_word:
            logger.info("[Voice] Wake word enabled: '%s'", self.wake_word)
        try:
            while self._running and getattr(self.kernel, "running", True):
                try:
                    text = await asyncio.to_thread(self._stt.listen_once)
                except STTUnavailable as exc:
                    logger.error("[Voice] %s", exc)
                    self.kernel.shutdown()
                    return
                except Exception as exc:
                    logger.exception("[Voice] STT error: %s", exc)
                    await asyncio.sleep(1.0)
                    continue

                text = (text or "").strip()
                if not text:
                    await asyncio.sleep(0.05)
                    continue

                original_text = text
                if self.wake_word:
                    lower = text.lower()
                    if self.wake_word not in lower:
                        logger.debug("[Voice] Ignored without wake word: %s", text)
                        continue
                    # Remove only the first wake-word occurrence and keep the command.
                    idx = lower.find(self.wake_word)
                    text = (text[:idx] + text[idx + len(self.wake_word):]).strip(" ,.:;!-—")
                    if not text:
                        text = original_text

                if self.print_transcript:
                    print(f"\nYou: {text}")

                self.kernel.event_bus.emit(
                    Event(
                        type="user_utterance",
                        data={"text": text, "input_mode": "voice", "raw_text": original_text},
                        source_module="voice_loop",
                    ),
                    Priority.REALTIME,
                )
        finally:
            logger.info("[Voice] Voice loop stopped")

    def stop(self) -> None:
        self._running = False
