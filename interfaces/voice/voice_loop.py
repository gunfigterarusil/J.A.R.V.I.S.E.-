"""Voice loop: microphone -> STT -> V1 dialogue -> TTS.

This interface is intentionally outside the module tree: it is a runtime mode
started with `python main.py --voice`. The cognitive work still happens inside
modules:

    microphone -> FasterWhisperSTT -> user_utterance event
    LLM dialogue module -> memory retrieval -> response_generated event
    TTS module -> Piper/pyttsx3 -> tts_spoken/tts_error event

The loop waits for the response/TTS result before listening again so Jarvis does
not immediately transcribe its own speaker output.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

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
        self.response_timeout = float(getattr(cfg, "response_timeout", 90.0))
        self.tts_wait_timeout = float(getattr(cfg, "tts_wait_timeout", 45.0))
        self.listen_after_response_delay = float(getattr(cfg, "listen_after_response_delay", 0.35))
        self.tts_enabled = bool(getattr(cfg, "tts_enabled", True))
        self.tts_backend = str(getattr(cfg, "tts_backend", "auto") or "auto").strip().lower()

        self._running = False
        self._response_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._tts_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._original_emit = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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
        self._loop = asyncio.get_running_loop()
        self._install_event_tap()

        logger.info("[Voice] Voice loop started. Speak into the microphone. Ctrl+C to stop.")
        logger.info("[Voice] Dialogue path: STT -> user_utterance -> V1 memory/LLM -> response_generated -> TTS")
        if self.wake_word:
            logger.info("[Voice] Wake word enabled: '%s'", self.wake_word)

        self._emit_status("listening", "Voice loop started")
        try:
            while self._running and getattr(self.kernel, "running", True):
                try:
                    self._emit_status("listening", "Recording microphone chunk")
                    text = await asyncio.to_thread(self._stt.listen_once)
                except STTUnavailable as exc:
                    logger.error("[Voice] %s", exc)
                    self._emit_status("error", str(exc))
                    self.kernel.shutdown()
                    return
                except Exception as exc:
                    logger.exception("[Voice] STT error: %s", exc)
                    self._emit_status("error", f"STT error: {exc}")
                    await asyncio.sleep(1.0)
                    continue

                text = (text or "").strip()
                if not text:
                    await asyncio.sleep(0.05)
                    continue

                original_text = text
                text = self._apply_wake_word(text)
                if text is None:
                    continue

                if self.print_transcript:
                    print(f"\nYou: {text}")

                self._emit_status("thinking", "User speech transcribed; waiting for dialogue response")
                if self._is_screen_read_command(text):
                    self.kernel.event_bus.emit(
                        Event(
                            type="screen_capture_requested",
                            data={
                                "request_id": f"voice_screen_{int(__import__('time').time())}",
                                "reason": "voice_user_requested_screen_read",
                                "spoken_command": text,
                                "respond": True,
                            },
                            source_module="voice_loop",
                        ),
                        Priority.REALTIME,
                    )
                elif self._is_sleep_command(text):
                    self.kernel.event_bus.emit(
                        Event(
                            type="sleep_cycle_requested",
                            data={
                                "reason": "voice_user_requested_sleep_cycle",
                                "spoken_command": text,
                                "force": True,
                                "respond": True,
                            },
                            source_module="voice_loop",
                        ),
                        Priority.COGNITIVE,
                    )
                else:
                    self.kernel.event_bus.emit(
                        Event(
                            type="user_utterance",
                            data={"text": text, "input_mode": "voice", "raw_text": original_text},
                            source_module="voice_loop",
                        ),
                        Priority.REALTIME,
                    )

                response = await self._wait_for_response()
                if response:
                    response_text = str(response.get("text", "") or "").strip()
                    turn_id = str(response.get("turn_id", "") or "")
                    if response_text and self.print_transcript:
                        print(f"Jarvis: {response_text}\n")
                    await self._wait_for_tts_if_needed(turn_id)
                else:
                    logger.warning("[Voice] No dialogue response within %.1fs", self.response_timeout)
                    self._emit_status("timeout", "No dialogue response received")

                if self.listen_after_response_delay > 0:
                    await asyncio.sleep(self.listen_after_response_delay)
        finally:
            self._emit_status("stopped", "Voice loop stopped")
            self._restore_event_tap()
            logger.info("[Voice] Voice loop stopped")

    def stop(self) -> None:
        self._running = False

    def _apply_wake_word(self, text: str) -> Optional[str]:
        if not self.wake_word:
            return text
        lower = text.lower()
        if self.wake_word not in lower:
            logger.debug("[Voice] Ignored without wake word: %s", text)
            return None
        idx = lower.find(self.wake_word)
        command = (text[:idx] + text[idx + len(self.wake_word):]).strip(" ,.:;!-—")
        return command or text

    def _is_screen_read_command(self, text: str) -> bool:
        lower = text.lower().strip()
        triggers = (
            "what is on screen",
            "what's on screen",
            "read the screen",
            "explain the screen",
            "що на екрані",
            "що в мене на екрані",
            "прочитай екран",
            "поясни екран",
            "що тут не так",
            "что на экране",
            "прочитай экран",
            "объясни экран",
        )
        return any(trigger in lower for trigger in triggers)


    def _is_sleep_command(self, text: str) -> bool:
        lower = text.lower().strip()
        triggers = (
            "run sleep cycle",
            "start sleep cycle",
            "consolidate memory",
            "memory consolidation",
            "dream replay",
            "запусти сон",
            "режим сну",
            "консолідуй пам'ять",
            "консолідуй память",
            "консолідація пам'яті",
            "консолидация памяти",
        )
        return any(trigger in lower for trigger in triggers)

    async def _wait_for_response(self) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._response_queue.get(), timeout=self.response_timeout)
        except asyncio.TimeoutError:
            return None

    async def _wait_for_tts_if_needed(self, turn_id: str) -> None:
        if not self.tts_enabled or self.tts_backend == "none" or self.tts_wait_timeout <= 0:
            return
        self._emit_status("speaking", "Waiting for TTS output to finish")
        deadline = asyncio.get_running_loop().time() + self.tts_wait_timeout
        while self._running:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning("[Voice] TTS completion not observed within %.1fs; listening again", self.tts_wait_timeout)
                return
            try:
                event_data = await asyncio.wait_for(self._tts_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return
            event_turn_id = str(event_data.get("turn_id", "") or "")
            if turn_id and event_turn_id and event_turn_id != turn_id:
                continue
            state = "listening" if event_data.get("type") == "tts_spoken" else "tts_error"
            self._emit_status(state, event_data.get("backend") or event_data.get("error") or "TTS finished")
            return

    def _install_event_tap(self) -> None:
        if self._original_emit is not None:
            return
        self._original_emit = self.kernel.event_bus.emit

        def _voice_tap(event: Event, priority: Priority) -> None:
            assert self._original_emit is not None
            self._original_emit(event, priority)
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            if event.type == "response_generated":
                data = dict(event.data or {})
                loop.call_soon_threadsafe(self._response_queue.put_nowait, data)
            elif event.type == "sleep_cycle_completed":
                data = {"text": "Sleep cycle completed. " + str((event.data or {}).get("summary", "")), "turn_id": "sleep_cycle"}
                loop.call_soon_threadsafe(self._response_queue.put_nowait, data)
            elif event.type in {"tts_spoken", "tts_error"}:
                data = dict(event.data or {})
                data["type"] = event.type
                loop.call_soon_threadsafe(self._tts_queue.put_nowait, data)

        self.kernel.event_bus.emit = _voice_tap  # type: ignore[method-assign]

    def _restore_event_tap(self) -> None:
        if self._original_emit is not None:
            self.kernel.event_bus.emit = self._original_emit  # type: ignore[method-assign]
            self._original_emit = None

    def _emit_status(self, state: str, detail: str = "") -> None:
        try:
            self.kernel.event_bus.emit(
                Event(
                    type="voice_status",
                    data={"state": state, "detail": detail},
                    source_module="voice_loop",
                ),
                Priority.BACKGROUND,
            )
        except Exception:
            logger.debug("[Voice] Could not emit status", exc_info=True)
