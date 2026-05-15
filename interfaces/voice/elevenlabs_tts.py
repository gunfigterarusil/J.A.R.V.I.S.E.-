"""ElevenLabs cloud TTS backend for JAV voice output.

Install: pip install elevenlabs>=1.0
API key: set ELEVENLABS_API_KEY in .env

Uses PCM output format to avoid MP3 decoding dependencies.
Streaming mode starts playing the first audio chunk ~400ms after request,
while the rest of the response is still being generated.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("voice.elevenlabs")

# PCM sample rate matching ElevenLabs pcm_22050 output format
_PCM_SAMPLERATE = 22050
_PCM_FORMAT = "pcm_22050"
_CHUNK_SIZE = 4096  # bytes per chunk — ~46ms of audio at 22050 Hz, 16-bit mono


class ElevenLabsUnavailable(RuntimeError):
    """Raised when ElevenLabs cannot be used (missing key, network, or package)."""


class ElevenLabsTTS:
    """Cloud TTS via ElevenLabs API with optional streaming playback.

    Streaming mode (default): begins playing as soon as the first PCM chunk
    arrives — typically 300-500ms after the request. This gives a noticeable
    latency improvement over waiting for the full audio.

    Non-streaming mode: buffers the full response then plays it — useful
    when stop_event-based interruption needs to be precise.
    """

    def __init__(
        self,
        api_key: str = "",
        voice_id: str = "Rachel",
        model_id: str = "eleven_turbo_v2_5",
        streaming: bool = True,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> None:
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not self.api_key:
            raise ElevenLabsUnavailable(
                "ElevenLabs API key not set. Add ELEVENLABS_API_KEY to .env"
            )
        self.voice_id = voice_id
        self.model_id = model_id
        self.streaming = streaming
        self.stability = float(stability)
        self.similarity_boost = float(similarity_boost)
        self._client = None

    @staticmethod
    def is_available() -> bool:
        """Return True if the elevenlabs package is importable."""
        try:
            import elevenlabs  # noqa: F401  # type: ignore
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from elevenlabs.client import ElevenLabs  # type: ignore
        except ImportError as exc:
            raise ElevenLabsUnavailable(
                "ElevenLabs SDK not installed. Run: pip install elevenlabs>=1.0"
            ) from exc
        self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def _voice_settings(self):
        try:
            from elevenlabs import VoiceSettings  # type: ignore
            return VoiceSettings(
                stability=self.stability,
                similarity_boost=self.similarity_boost,
            )
        except ImportError:
            return None

    def speak(self, text: str, stop_event=None) -> None:
        """Synthesize and play text. Routes to streaming or buffered playback."""
        text = (text or "").strip()
        if not text:
            return
        if self.streaming:
            self._speak_streaming(text, stop_event)
        else:
            self._speak_buffered(text, stop_event)

    def _speak_streaming(self, text: str, stop_event=None) -> None:
        """Stream PCM audio from ElevenLabs and play chunks as they arrive."""
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            logger.warning("[ElevenLabs] sounddevice/numpy unavailable (%s) — falling back to buffered", exc)
            self._speak_buffered(text, stop_event)
            return

        client = self._get_client()
        settings = self._voice_settings()

        logger.debug("[ElevenLabs] Streaming synthesis: %d chars, voice=%s, model=%s", len(text), self.voice_id, self.model_id)
        t0 = time.monotonic()

        try:
            kwargs = dict(
                voice_id=self.voice_id,
                text=text,
                model_id=self.model_id,
                output_format=_PCM_FORMAT,
            )
            if settings is not None:
                kwargs["voice_settings"] = settings

            audio_stream = client.text_to_speech.stream(**kwargs)

            first_chunk = True
            with sd.OutputStream(
                samplerate=_PCM_SAMPLERATE,
                channels=1,
                dtype="int16",
            ) as stream:
                for chunk in audio_stream:
                    if stop_event is not None and stop_event.is_set():
                        logger.debug("[ElevenLabs] Playback interrupted by stop_event")
                        return
                    if not chunk:
                        continue
                    if first_chunk:
                        logger.debug("[ElevenLabs] First audio chunk at %.2f s", time.monotonic() - t0)
                        first_chunk = False
                    audio = np.frombuffer(chunk, dtype=np.int16)
                    stream.write(audio)

        except ElevenLabsUnavailable:
            raise
        except Exception as exc:
            raise ElevenLabsUnavailable(f"ElevenLabs streaming failed: {exc}") from exc

    def _speak_buffered(self, text: str, stop_event=None) -> None:
        """Fetch full PCM audio then play with stop_event support."""
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            raise ElevenLabsUnavailable(
                f"sounddevice/numpy not installed: {exc}"
            ) from exc

        client = self._get_client()
        settings = self._voice_settings()

        logger.debug("[ElevenLabs] Buffered synthesis: %d chars", len(text))

        try:
            kwargs = dict(
                voice_id=self.voice_id,
                text=text,
                model_id=self.model_id,
                output_format=_PCM_FORMAT,
            )
            if settings is not None:
                kwargs["voice_settings"] = settings

            audio_bytes = client.text_to_speech.convert(**kwargs)
            # convert() may return bytes or a generator — normalise to bytes
            if not isinstance(audio_bytes, (bytes, bytearray)):
                audio_bytes = b"".join(audio_bytes)

        except ElevenLabsUnavailable:
            raise
        except Exception as exc:
            raise ElevenLabsUnavailable(f"ElevenLabs convert failed: {exc}") from exc

        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype("float32") / 32768.0
        sd.play(audio, _PCM_SAMPLERATE)
        while sd.get_stream().active:
            if stop_event is not None and stop_event.is_set():
                sd.stop()
                return
            time.sleep(0.05)
        sd.wait()
