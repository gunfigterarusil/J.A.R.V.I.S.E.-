"""Tier 4 Action: Text-to-Speech Module.

Listens for response_generated events and speaks them when voice mode is enabled.
Backend priority (auto mode):
  1. ElevenLabs  — cloud, ~400ms latency, streaming PCM (requires ELEVENLABS_API_KEY)
  2. XTTS v2     — local neural, voice cloning, Ukrainian support (requires pip install TTS)
  3. Piper       — local CLI, fast, decent quality (requires Piper executable + model)
  4. pyttsx3     — local OS voices, always available
Explicit backends: elevenlabs | xtts | piper | pyttsx3 | none
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, Protocol

from core import CognitiveModule, CognitiveEvent as Event, Priority
from interfaces.voice.piper_tts import PiperTTS, PiperUnavailable
from interfaces.voice.pyttsx3_tts import Pyttsx3TTS, Pyttsx3Unavailable
from interfaces.voice.xtts_tts import XttsTTS, XttsUnavailable
from interfaces.voice.elevenlabs_tts import ElevenLabsTTS, ElevenLabsUnavailable

logger = logging.getLogger("tts")


class SpeechBackend(Protocol):
    def speak(self, text: str) -> Any: ...


class TTSModule(CognitiveModule):
    MODULE_DESCRIPTION = "Voice output: ElevenLabs / XTTS v2 / Piper / pyttsx3 with automatic fallback chain"
    MODULE_VERSION = "0.3.0"

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
        self._stop_event: threading.Event = threading.Event()
        self._muted = False
        # Phase 3C — emotional voice modulation
        self._mod_enabled: bool = True
        self._mod_strength: float = 0.35
        self._emotion_affect: dict = {}
        self._hormone_levels: dict = {}
        self._base_pyttsx3_rate: int = 175
        self._base_piper_length: float = 1.0
        self._base_el_stability: float = 0.5

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "voice", None)
        self._configured_backend = str(getattr(cfg, "tts_backend", "auto") or "auto").strip().lower()
        self._voice_enabled = bool(
            getattr(cfg, "enabled", False)
            and getattr(cfg, "tts_enabled", True)
            and self._configured_backend != "none"
        )
        self._muted = bool(getattr(cfg, "start_muted", False))
        kernel.event_bus.register_consumer(
            self.module_id,
            ["response_generated", "response_part", "tts_say", "tts_interrupt", "tts_mute", "tts_unmute", "tts_toggle_mute", "tts_status_requested",
             "emotional_state", "hormone_levels"],
        )
        if not self._voice_enabled:
            logger.info("[TTS] Disabled. Start with --voice and VOICE_TTS_ENABLED=true to enable output.")
            return

        _valid = {"auto", "elevenlabs", "xtts", "piper", "pyttsx3", "none"}
        if self._configured_backend not in _valid:
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

        mode = self._configured_backend
        if mode == "piper":
            self._backends = [("piper", piper)]
        elif mode == "pyttsx3":
            self._backends = [("pyttsx3", pyttsx3_backend)]
        elif mode == "elevenlabs":
            el_key = getattr(cfg, "elevenlabs_api_key", "")
            try:
                el = ElevenLabsTTS(
                    api_key=el_key,
                    voice_id=getattr(cfg, "elevenlabs_voice_id", "Rachel"),
                    model_id=getattr(cfg, "elevenlabs_model", "eleven_turbo_v2_5"),
                    streaming=getattr(cfg, "elevenlabs_streaming", True),
                    stability=getattr(cfg, "elevenlabs_stability", 0.5),
                    similarity_boost=getattr(cfg, "elevenlabs_similarity", 0.75),
                )
                self._backends = [("elevenlabs", el)]
            except ElevenLabsUnavailable as exc:
                logger.error("[TTS] ElevenLabs init failed: %s", exc)
                self._backends = []
        elif mode == "xtts":
            xt = XttsTTS(
                model_name=getattr(cfg, "xtts_model", "tts_models/multilingual/multi-dataset/xtts_v2"),
                speaker_wav=getattr(cfg, "xtts_speaker_wav", ""),
                language=getattr(cfg, "xtts_language", "uk"),
                device=getattr(cfg, "xtts_device", "auto"),
            )
            self._backends = [("xtts", xt)]
        else:
            # auto: elevenlabs → xtts → piper → pyttsx3
            self._backends = []
            el_key = getattr(cfg, "elevenlabs_api_key", "")
            if el_key and ElevenLabsTTS.is_available():
                try:
                    el = ElevenLabsTTS(
                        api_key=el_key,
                        voice_id=getattr(cfg, "elevenlabs_voice_id", "Rachel"),
                        model_id=getattr(cfg, "elevenlabs_model", "eleven_turbo_v2_5"),
                        streaming=getattr(cfg, "elevenlabs_streaming", True),
                        stability=getattr(cfg, "elevenlabs_stability", 0.5),
                        similarity_boost=getattr(cfg, "elevenlabs_similarity", 0.75),
                    )
                    self._backends.append(("elevenlabs", el))
                    logger.info("[TTS] ElevenLabs backend registered (voice=%s)", getattr(cfg, "elevenlabs_voice_id", "Rachel"))
                except ElevenLabsUnavailable as exc:
                    logger.warning("[TTS] ElevenLabs skipped: %s", exc)
            if XttsTTS.is_available():
                xt = XttsTTS(
                    model_name=getattr(cfg, "xtts_model", "tts_models/multilingual/multi-dataset/xtts_v2"),
                    speaker_wav=getattr(cfg, "xtts_speaker_wav", ""),
                    language=getattr(cfg, "xtts_language", "uk"),
                    device=getattr(cfg, "xtts_device", "auto"),
                )
                self._backends.append(("xtts", xt))
                logger.info("[TTS] XTTS v2 backend registered (lang=%s, device=%s)", getattr(cfg, "xtts_language", "uk"), getattr(cfg, "xtts_device", "auto"))
            self._backends.extend([("piper", piper), ("pyttsx3", pyttsx3_backend)])

        self._mod_enabled = bool(getattr(cfg, "emotional_tts_enabled", True))
        self._mod_strength = max(0.0, min(1.0, float(getattr(cfg, "emotional_tts_strength", 0.35))))
        for name, b in self._backends:
            if name == "pyttsx3":
                self._base_pyttsx3_rate = int(getattr(b, "rate", 175))
            elif name == "piper":
                self._base_piper_length = float(getattr(b, "length_scale", 1.0))
            elif name == "elevenlabs":
                self._base_el_stability = float(getattr(b, "stability", 0.5))

        logger.info(
            "[TTS] Enabled | mode=%s | chain=%s | emotional_tts=%s",
            self._configured_backend,
            [n for n, _ in self._backends],
            self._mod_enabled,
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "tts_interrupt":
            self._stop_event.set()
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(type="tts_interrupted", data={"reason": event.data.get("reason", "manual")}, source_module=self.module_id),
                    Priority.BACKGROUND,
                )
            return
        if event.type == "tts_mute":
            self._muted = True
            self._stop_event.set()
            self._emit_status("muted")
            return
        if event.type == "tts_unmute":
            self._muted = False
            self._emit_status("unmuted")
            return
        if event.type == "tts_toggle_mute":
            self._muted = not self._muted
            self._stop_event.set()
            self._emit_status("muted" if self._muted else "unmuted")
            return
        if event.type == "tts_status_requested":
            self._emit_status("status")
            return
        if event.type == "emotional_state":
            if self._mod_enabled:
                self._emotion_affect = dict(event.data or {})
                self._apply_voice_modulation()
            return
        if event.type == "hormone_levels":
            if self._mod_enabled:
                self._hormone_levels = dict(event.data or {})
                self._apply_voice_modulation()
            return

        if not self._voice_enabled or not self._backends:
            return
        if event.type not in {"response_generated", "tts_say", "response_part"}:
            return

        # Streaming: response_generated is informational only (parts already spoken)
        if event.type == "response_generated" and event.data.get("streamed"):
            return

        text = str(event.data.get("text", "")).strip()
        if not text:
            return
        turn_id = str(event.data.get("turn_id", "") or "")

        # Non-streaming response: interrupt any ongoing back-channel before speaking
        if event.type == "response_generated":
            self._stop_event.set()
        # First streaming part: interrupt back-channel
        if event.type == "response_part" and event.data.get("is_first_part"):
            self._stop_event.set()

        if self._muted:
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(type="tts_muted", data={"text": text[:300], "turn_id": turn_id, "reason": "muted"}, source_module=self.module_id),
                    Priority.BACKGROUND,
                )
            return
        await self._speak(text, turn_id=turn_id)

    async def _speak(self, text: str, turn_id: str = "") -> None:
        async with self._speak_lock:
            self._stop_event.clear()
            errors: list[str] = []
            for name, backend in self._backends:
                try:
                    _ev = self._stop_event
                    await asyncio.to_thread(lambda: backend.speak(text, stop_event=_ev))
                    self._active_backend = name
                    self._last_error = ""
                    if self.kernel:
                        self.kernel.event_bus.emit(
                            Event(
                                type="tts_spoken",
                                data={"text": text[:300], "backend": name, "turn_id": turn_id},
                                source_module=self.module_id,
                            ),
                            Priority.BACKGROUND,
                        )
                    return
                except (PiperUnavailable, Pyttsx3Unavailable, XttsUnavailable, ElevenLabsUnavailable) as exc:
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
                        data={"error": self._last_error, "turn_id": turn_id},
                        source_module=self.module_id,
                    ),
                    Priority.BACKGROUND,
                )

    def _compute_voice_modulation(self) -> dict:
        a = self._emotion_affect
        h = self._hormone_levels
        arousal        = float(a.get("arousal", 0.0))
        valence        = float(a.get("valence", 0.0))
        frustration    = float(a.get("frustration", 0.0))
        cognitive_load = float(a.get("cognitive_load", 0.0))
        cortisol   = float(h.get("cortisol", 0.2))
        oxytocin   = float(h.get("oxytocin", 0.3))
        adrenaline = float(h.get("adrenaline", 0.1))

        speed_delta = (arousal * 0.25 + frustration * 0.12
                       + (adrenaline - 0.1) * 0.30 - cognitive_load * 0.10)
        speed = max(0.70, min(1.40, 1.0 + speed_delta * self._mod_strength))

        stab_delta = (oxytocin * 0.20 - abs(arousal) * 0.15
                      - cortisol * 0.10 + valence * 0.05)
        stability = max(0.20, min(0.95,
                        self._base_el_stability + stab_delta * self._mod_strength))
        return {"speed_factor": speed, "stability": stability}

    def _apply_voice_modulation(self) -> None:
        if not self._mod_enabled or not self._backends:
            return
        mod = self._compute_voice_modulation()
        speed = mod["speed_factor"]
        for name, b in self._backends:
            if name == "pyttsx3":
                b.rate = max(100, min(300, int(self._base_pyttsx3_rate * speed)))
            elif name == "piper":
                b.length_scale = round(self._base_piper_length / speed, 3)
            elif name == "elevenlabs":
                b.stability = round(mod["stability"], 3)
        logger.debug("[TTS] Modulation: speed=%.2f stab=%.2f emotion=%s",
                     speed, mod["stability"], self._emotion_affect.get("emotion", "?"))

    def _emit_status(self, reason: str = "status") -> None:
        if not self.kernel:
            return
        self.kernel.event_bus.emit(
            Event(
                type="tts_status",
                data={
                    "reason": reason,
                    "muted": self._muted,
                    "voice_enabled": self._voice_enabled,
                    "active_backend": self._active_backend,
                    "backend_mode": self._configured_backend,
                    "emotional_tts": self._mod_enabled,
                    "emotional_strength": self._mod_strength,
                    "voice_modulation": self._compute_voice_modulation() if self._mod_enabled else {},
                },
                source_module=self.module_id,
            ),
            Priority.BACKGROUND,
        )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        backends_info = []
        for name, b in self._backends:
            info: dict = {"name": name}
            if name == "xtts":
                info["language"] = getattr(b, "language", "")
                info["has_speaker_wav"] = bool(getattr(b, "speaker_wav", ""))
            elif name == "elevenlabs":
                info["voice_id"] = getattr(b, "voice_id", "")
                info["model"] = getattr(b, "model_id", "")
                info["streaming"] = getattr(b, "streaming", True)
            backends_info.append(info)
        base.update(
            {
                "voice_enabled": self._voice_enabled,
                "backend_mode": self._configured_backend,
                "active_backend": self._active_backend,
                "available_backends": [name for name, _ in self._backends],
                "backends_info": backends_info,
                "last_error": self._last_error,
                "muted": self._muted,
                "emotional_tts": self._mod_enabled,
                "emotional_strength": self._mod_strength,
                "voice_modulation": self._compute_voice_modulation() if self._mod_enabled else {},
            }
        )
        return base


def create_module() -> TTSModule:
    return TTSModule()
