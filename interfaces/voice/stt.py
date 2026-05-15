"""Speech-to-text helpers for the Voice MVP.

Uses sounddevice for microphone capture and faster-whisper for local STT.
All heavy dependencies are imported lazily so the core can still start without them.
"""
from __future__ import annotations

import logging
import tempfile
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voice.stt")


class STTUnavailable(RuntimeError):
    """Raised when voice input dependencies are missing."""


class FasterWhisperSTT:
    """Small wrapper around faster-whisper + sounddevice microphone capture."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
        sample_rate: int = 16000,
        record_seconds: float = 5.0,
        energy_threshold: float = 0.005,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language or None
        self.sample_rate = int(sample_rate)
        self.record_seconds = float(record_seconds)
        self.energy_threshold = float(energy_threshold)
        self._model = None

    def _import_audio_stack(self):
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            raise STTUnavailable(
                "Voice input needs dependencies: pip install sounddevice numpy faster-whisper"
            ) from exc
        return np, sd

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise STTUnavailable(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            ) from exc
        logger.info(
            "[Voice/STT] Loading faster-whisper model=%s device=%s compute_type=%s",
            self.model_size,
            self.device,
            self.compute_type,
        )
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model

    def record_once(self):
        """Record one microphone chunk and return a mono float32 numpy array."""
        np, sd = self._import_audio_stack()
        frames = int(self.sample_rate * self.record_seconds)
        audio = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="float32")
        sd.wait()
        audio = audio.reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        if rms < self.energy_threshold:
            logger.debug("[Voice/STT] Silence skipped rms=%.5f threshold=%.5f", rms, self.energy_threshold)
            return None
        return audio

    def _write_temp_wav(self, audio) -> Path:
        import numpy as np  # type: ignore

        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)
        tmp = tempfile.NamedTemporaryFile(prefix="jarvis_voice_", suffix=".wav", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        with wave.open(str(tmp_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm16.tobytes())
        return tmp_path

    def transcribe_audio(self, audio) -> str:
        """Transcribe a numpy audio chunk into text."""
        model = self._load_model()
        wav_path = self._write_temp_wav(audio)
        try:
            segments, _info = model.transcribe(
                str(wav_path),
                language=self.language,
                vad_filter=True,
                beam_size=1,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
            return text.strip()
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

    def listen_once(self) -> str:
        """Record one chunk and transcribe it. Returns empty string on silence."""
        audio = self.record_once()
        if audio is None:
            return ""
        return self.transcribe_audio(audio)

    def listen_with_vad(
        self,
        max_silence_ms: int = 700,
        min_speech_ms: int = 150,
        max_duration_s: float = 30.0,
        stop_event=None,
    ) -> str:
        """Stream mic; stop when speech ends. Returns empty string on silence/stop."""
        import queue as _q
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore

        chunk_ms = 30
        chunk_frames = int(self.sample_rate * chunk_ms / 1000)
        max_silence_chunks = max(1, int(max_silence_ms / chunk_ms))
        min_speech_chunks = max(1, int(min_speech_ms / chunk_ms))
        max_total = int(max_duration_s * 1000 / chunk_ms)

        buf: _q.Queue = _q.Queue()

        def _cb(indata, frames, t, status):  # type: ignore[misc]
            buf.put(indata.copy())

        chunks: list = []
        speech_count = 0
        silence_count = 0
        in_speech = False

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_frames,
            callback=_cb,
        ):
            while len(chunks) < max_total:
                if stop_event is not None and stop_event.is_set():
                    return ""
                try:
                    chunk = buf.get(timeout=0.1)
                except _q.Empty:
                    continue
                rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0
                is_speech = rms > self.energy_threshold
                if is_speech:
                    in_speech = True
                    silence_count = 0
                    speech_count += 1
                    chunks.append(chunk)
                elif in_speech:
                    silence_count += 1
                    chunks.append(chunk)
                    if silence_count >= max_silence_chunks:
                        break

        if speech_count < min_speech_chunks:
            return ""
        audio = np.concatenate(chunks).reshape(-1)
        return self.transcribe_audio(audio)
