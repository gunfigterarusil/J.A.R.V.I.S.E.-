"""Voice companion loop: microphone -> STT -> V1 dialogue -> TTS.

V17 adds a safer companion mode on top of the original voice MVP:
- continuous or push-to-talk input mode;
- wake word filtering;
- voice status events/file: idle/listening/thinking/speaking/muted/error;
- spoken and chat-driven mute/unmute/interrupt controls;
- protection against listening while TTS is still speaking.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core.event_bus import CognitiveEvent as Event, Priority
from interfaces.voice.back_channel import pick_phrase
from interfaces.voice.stt import FasterWhisperSTT, STTUnavailable
from interfaces.voice.wake_word_detector import OpenWakeWordDetector, WakeWordUnavailable

logger = logging.getLogger("voice.loop")


class VoiceLoop:
    """Continuously listens to the microphone and emits user_utterance events."""

    def __init__(self, kernel) -> None:
        self.kernel = kernel
        cfg = getattr(kernel.config, "voice", None)
        self.cfg = cfg
        self.wake_word = str(getattr(cfg, "wake_word", "") or "").strip().lower()
        self.input_mode = str(getattr(cfg, "input_mode", "continuous") or "continuous").strip().lower()
        if self.input_mode not in {"continuous", "push_to_talk"}:
            logger.warning("[Voice] Unknown VOICE_INPUT_MODE=%r; using continuous", self.input_mode)
            self.input_mode = "continuous"
        self.push_to_talk_prompt = str(getattr(cfg, "push_to_talk_prompt", "Press Enter to speak, or type q + Enter to quit: ") or "")
        self.print_transcript = bool(getattr(cfg, "print_transcript", True))
        self.response_timeout = float(getattr(cfg, "response_timeout", 90.0))
        self.tts_wait_timeout = float(getattr(cfg, "tts_wait_timeout", 45.0))
        self.listen_after_response_delay = float(getattr(cfg, "listen_after_response_delay", 0.35))
        self.tts_enabled = bool(getattr(cfg, "tts_enabled", True))
        self.tts_backend = str(getattr(cfg, "tts_backend", "auto") or "auto").strip().lower()
        self.muted = bool(getattr(cfg, "start_muted", False))

        self.vad_enabled = bool(getattr(cfg, "vad_enabled", True))
        self.vad_max_silence_ms = int(getattr(cfg, "vad_max_silence_ms", 700))
        self.vad_min_speech_ms = int(getattr(cfg, "vad_min_speech_ms", 150))
        self.vad_max_duration_s = float(getattr(cfg, "vad_max_duration_s", 30.0))
        self.interrupt_phrases = self._phrase_set(getattr(cfg, "interrupt_phrases", "stop,зупинись,стоп"))
        self.mute_phrases = self._phrase_set(getattr(cfg, "mute_phrases", "mute,мовчи,замовкни,не говори"))
        self.unmute_phrases = self._phrase_set(getattr(cfg, "unmute_phrases", "unmute,говори,можеш говорити"))
        self.back_channel_enabled = bool(getattr(cfg, "back_channel_enabled", True))
        self.back_channel_language = str(getattr(cfg, "back_channel_language", "uk") or "uk")
        self._vad_stop = threading.Event()

        self._running = False
        self._response_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._tts_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._original_emit = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._status_file = self._resolve_status_file(str(getattr(cfg, "status_file", "") or ""))

        self._stt = FasterWhisperSTT(
            model_size=getattr(cfg, "stt_model", "small"),
            device=getattr(cfg, "stt_device", "cpu"),
            compute_type=getattr(cfg, "stt_compute_type", "int8"),
            language=getattr(cfg, "stt_language", ""),
            sample_rate=getattr(cfg, "sample_rate", 16000),
            record_seconds=getattr(cfg, "record_seconds", 5.0),
            energy_threshold=getattr(cfg, "energy_threshold", 0.005),
        )

        # Phase 3A — acoustic wake word detector (optional, lazy)
        self._wwd: Optional[OpenWakeWordDetector] = None
        self._wake_word_ack: bool = bool(getattr(cfg, "wake_word_ack", True))
        self._init_wake_word_detector(cfg)

    @staticmethod
    def _phrase_set(raw: Any) -> set[str]:
        return {p.strip().lower() for p in str(raw or "").split(",") if p.strip()}

    def _resolve_status_file(self, configured: str) -> Path:
        if configured:
            return Path(configured).expanduser()
        data_dir = Path(getattr(self.kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        return data_dir / "runtime_voice_status.json"

    async def run(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._install_event_tap()

        logger.info("[Voice] Voice companion started. mode=%s backend=%s", self.input_mode, self.tts_backend)
        if self.wake_word:
            logger.info("[Voice] Wake word enabled: '%s'", self.wake_word)
        if self.input_mode == "push_to_talk":
            logger.info("[Voice] Push-to-talk mode: press Enter before each utterance")

        if self.muted:
            self._emit_tts_control("tts_mute", "start_muted")
        self._emit_status("idle", "Voice companion started")
        try:
            while self._running and getattr(self.kernel, "running", True):
                if self.input_mode == "push_to_talk":
                    should_continue = await self._wait_for_push_to_talk()
                    if not should_continue:
                        self.kernel.shutdown()
                        return

                # Phase 3A: acoustic wake word gate (if detector is active)
                if self._wwd is not None:
                    detected = await self._wait_for_wake_word()
                    if not detected:
                        # stop_event fired — exit loop
                        break

                try:
                    self._emit_status("listening", "Recording microphone")
                    if self.vad_enabled:
                        # B: interrupt TTS the instant speech is detected (before transcription)
                        def _on_speech_start() -> None:
                            self._emit_tts_control("tts_interrupt", "speech_start_detected")

                        text = await asyncio.to_thread(
                            self._stt.listen_with_vad,
                            self.vad_max_silence_ms,
                            self.vad_min_speech_ms,
                            self.vad_max_duration_s,
                            self._vad_stop,
                            _on_speech_start,
                        )
                    else:
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
                    self._emit_status("idle", "No speech detected")
                    await asyncio.sleep(0.05)
                    continue

                if self._handle_voice_control_command(text):
                    continue

                original_text = text
                text = self._apply_wake_word(text)
                if text is None:
                    self._emit_status("idle", "Ignored utterance without wake word")
                    continue

                # Auto-interrupt any ongoing TTS when a new real utterance starts.
                self._emit_tts_control("tts_interrupt", "new_utterance")

                if self.print_transcript:
                    print(f"\nYou: {text}")

                self._emit_status("thinking", "Speech transcribed; waiting for response")
                self._dispatch_user_text(text, original_text)
                # A: acknowledge immediately while LLM thinks
                self._emit_back_channel(text)

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
                self._emit_status("idle", "Ready")
        finally:
            self._emit_status("stopped", "Voice companion stopped")
            self._restore_event_tap()
            logger.info("[Voice] Voice companion stopped")

    async def _wait_for_push_to_talk(self) -> bool:
        self._emit_status("idle", "Push-to-talk waiting")
        marker = await asyncio.to_thread(input, self.push_to_talk_prompt)
        marker = (marker or "").strip().lower()
        return marker not in {"q", "quit", "exit", "/exit", "/quit"}

    def stop(self) -> None:
        self._running = False
        self._vad_stop.set()

    def _dispatch_user_text(self, text: str, original_text: str) -> None:
        if self._is_screen_read_command(text):
            self.kernel.event_bus.emit(
                Event(
                    type="screen_capture_requested",
                    data={
                        "request_id": f"voice_screen_{int(time.time())}",
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
                    data={"reason": "voice_user_requested_sleep_cycle", "spoken_command": text, "force": True, "respond": True},
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

    def _handle_voice_control_command(self, text: str) -> bool:
        normalized = text.lower().strip().rstrip(".,!?")
        if normalized in self.interrupt_phrases:
            self._emit_tts_control("tts_interrupt", "voice_interrupt_phrase")
            self._emit_status("listening", "TTS interrupted by voice command")
            return True
        if normalized in self.mute_phrases:
            self.muted = True
            self._emit_tts_control("tts_mute", "voice_mute_phrase")
            self._emit_status("muted", "Voice output muted")
            return True
        if normalized in self.unmute_phrases:
            self.muted = False
            self._emit_tts_control("tts_unmute", "voice_unmute_phrase")
            self._emit_status("listening", "Voice output unmuted")
            return True
        return False

    def _emit_tts_control(self, event_type: str, reason: str) -> None:
        self.kernel.event_bus.emit(
            Event(type=event_type, data={"reason": reason}, source_module="voice_loop"),
            Priority.REALTIME,
        )

    def _emit_back_channel(self, user_text: str) -> None:
        """Emit a short acknowledgment phrase while the LLM is thinking (Feature A)."""
        if not self.back_channel_enabled or self.muted or self.tts_backend == "none":
            return
        phrase = pick_phrase(user_text, self.back_channel_language)
        self.kernel.event_bus.emit(
            Event(
                type="tts_say",
                data={"text": phrase, "turn_id": "back_channel", "is_back_channel": True},
                source_module="voice_loop",
            ),
            Priority.REALTIME,
        )

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
            "what is on screen", "what's on screen", "read the screen", "explain the screen",
            "що на екрані", "що в мене на екрані", "прочитай екран", "поясни екран", "що тут не так",
            "что на экране", "прочитай экран", "объясни экран",
        )
        return any(trigger in lower for trigger in triggers)

    def _is_sleep_command(self, text: str) -> bool:
        lower = text.lower().strip()
        triggers = (
            "run sleep cycle", "start sleep cycle", "consolidate memory", "memory consolidation", "dream replay",
            "запусти сон", "режим сну", "консолідуй пам'ять", "консолідуй память", "консолідація пам'яті",
            "консолидация памяти",
        )
        return any(trigger in lower for trigger in triggers)

    async def _wait_for_response(self) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._response_queue.get(), timeout=self.response_timeout)
        except asyncio.TimeoutError:
            return None

    async def _wait_for_tts_if_needed(self, turn_id: str) -> None:
        if not self.tts_enabled or self.tts_backend == "none" or self.tts_wait_timeout <= 0 or self.muted:
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
            etype = event_data.get("type")
            if etype in {"tts_muted", "tts_interrupted"}:
                self._emit_status("muted" if etype == "tts_muted" else "listening", event_data.get("reason", etype))
                return
            state = "listening" if etype == "tts_spoken" else "tts_error"
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
                loop.call_soon_threadsafe(self._response_queue.put_nowait, dict(event.data or {}))
            elif event.type == "sleep_cycle_completed":
                data = {"text": "Sleep cycle completed. " + str((event.data or {}).get("summary", "")), "turn_id": "sleep_cycle"}
                loop.call_soon_threadsafe(self._response_queue.put_nowait, data)
            elif event.type in {"tts_spoken", "tts_error", "tts_muted", "tts_interrupted"}:
                data = dict(event.data or {})
                data["type"] = event.type
                loop.call_soon_threadsafe(self._tts_queue.put_nowait, data)
            elif event.type == "tts_status":
                data = event.data or {}
                self.muted = bool(data.get("muted", self.muted))

        self.kernel.event_bus.emit = _voice_tap  # type: ignore[method-assign]

    def _restore_event_tap(self) -> None:
        if self._original_emit is not None:
            self.kernel.event_bus.emit = self._original_emit  # type: ignore[method-assign]
            self._original_emit = None

    def _init_wake_word_detector(self, cfg) -> None:
        detector_type = str(getattr(cfg, "wake_word_detector", "none") or "none").strip().lower()
        if detector_type == "none":
            return
        if detector_type != "openwakeword":
            logger.warning("[Voice] Unknown VOICE_WAKE_WORD_DETECTOR=%r; ignoring", detector_type)
            return
        if not OpenWakeWordDetector.is_available():
            logger.warning(
                "[Voice] wake_word_detector=openwakeword but openwakeword is not installed. "
                "Run: pip install openwakeword  (falling back to text-based wake word filter)"
            )
            return
        model = str(getattr(cfg, "wake_word_model", "hey_jarvis") or "hey_jarvis").strip()
        threshold = float(getattr(cfg, "wake_word_threshold", 0.5))
        sample_rate = int(getattr(cfg, "sample_rate", 16000))
        try:
            self._wwd = OpenWakeWordDetector(model, threshold=threshold, sample_rate=sample_rate)
            logger.info("[Voice] Acoustic wake word detector ready: model=%s threshold=%.2f", model, threshold)
        except Exception as exc:
            logger.error("[Voice] Failed to init wake word detector: %s", exc)
            self._wwd = None

    async def _wait_for_wake_word(self) -> bool:
        """Block until acoustic wake word detected. Returns False if loop stopped."""
        self._emit_status("wake_word_waiting", "Waiting for wake word...")
        try:
            detected = await asyncio.to_thread(self._wwd.listen_for_wake_word, self._vad_stop)
        except WakeWordUnavailable as exc:
            logger.error("[Voice] Wake word detector unavailable: %s", exc)
            return True   # degrade gracefully: proceed to full STT anyway
        except Exception as exc:
            logger.exception("[Voice] Wake word detection error: %s", exc)
            return True
        if detected:
            self._emit_status("wake_word_detected", "Wake word heard")
            if self._wake_word_ack and not self.muted and self.tts_backend != "none":
                self.kernel.event_bus.emit(
                    Event(
                        type="tts_say",
                        data={"text": "Слухаю.", "turn_id": "wake_ack", "is_back_channel": True},
                        source_module="voice_loop",
                    ),
                    Priority.REALTIME,
                )
        return detected

    def _emit_status(self, state: str, detail: str = "") -> None:
        payload = {
            "state": state,
            "detail": detail,
            "input_mode": self.input_mode,
            "wake_word_enabled": bool(self.wake_word) or self._wwd is not None,
            "wake_word_acoustic": self._wwd is not None,
            "muted": bool(self.muted),
            "timestamp": time.time(),
        }
        try:
            self._status_file.parent.mkdir(parents=True, exist_ok=True)
            self._status_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.debug("[Voice] Could not write status file", exc_info=True)
        try:
            self.kernel.event_bus.emit(Event(type="voice_status", data=payload, source_module="voice_loop"), Priority.BACKGROUND)
        except Exception:
            logger.debug("[Voice] Could not emit status", exc_info=True)
