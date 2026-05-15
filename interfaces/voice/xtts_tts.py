"""XTTS v2 (Coqui) neural TTS backend for JAV voice output.

Install: pip install TTS
Model:   tts_models/multilingual/multi-dataset/xtts_v2 (~1.8 GB, auto-downloaded)
Supports Ukrainian, English, and 16 other languages natively.
Supports voice cloning from a 6+ second WAV reference sample.
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
import wave
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger("voice.xtts")

_SUPPORTED_LANGUAGES = {
    "uk", "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru",
    "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko",
}


class XttsUnavailable(RuntimeError):
    """Raised when XTTS v2 cannot be loaded or used."""


class XttsTTS:
    """Neural TTS using Coqui XTTS v2. Lazy-loads the model on first use.

    The model is ~1.8 GB and takes 15–30 sec to load on first call,
    then stays in memory for instant subsequent synthesis.
    """

    _global_model = None
    _global_lock = Lock()

    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        speaker_wav: str = "",
        language: str = "uk",
        device: str = "auto",
        output_dir: str = "",
    ) -> None:
        self.model_name = model_name
        self.speaker_wav = speaker_wav
        self.language = language if language in _SUPPORTED_LANGUAGES else "en"
        self.output_dir = Path(output_dir).expanduser() if output_dir else None
        self._device = self._resolve_device(device)
        self._model = None

    @staticmethod
    def is_available() -> bool:
        """Return True if the TTS package (Coqui) is importable."""
        try:
            import TTS  # noqa: F401  # type: ignore
            return True
        except ImportError:
            return False

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            try:
                import torch  # type: ignore
                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return device

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with XttsTTS._global_lock:
            if self._model is not None:
                return
            try:
                from TTS.api import TTS  # type: ignore
            except ImportError as exc:
                raise XttsUnavailable(
                    "Coqui TTS not installed. Run: pip install TTS"
                ) from exc

            logger.info("[XTTS] Loading model '%s' on %s (first load ~15-30s)…", self.model_name, self._device)
            t0 = time.monotonic()
            try:
                # gpu=True uses CUDA when self._device is "cuda"
                model = TTS(model_name=self.model_name, gpu=(self._device == "cuda"))
            except Exception as exc:
                raise XttsUnavailable(f"XTTS model load failed: {exc}") from exc

            elapsed = time.monotonic() - t0
            logger.info("[XTTS] Model loaded in %.1f s", elapsed)
            self._model = model
            XttsTTS._global_model = model

    def synthesize_to_file(self, text: str) -> Path:
        """Synthesize text to a WAV file. Returns the file path."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Cannot synthesize empty text")

        self._ensure_loaded()

        out_dir = self.output_dir or Path(tempfile.gettempdir())
        out_dir.mkdir(parents=True, exist_ok=True)
        fd, wav_name = tempfile.mkstemp(prefix="jav_xtts_", suffix=".wav", dir=str(out_dir))
        os.close(fd)
        wav_path = Path(wav_name)

        try:
            kwargs: dict = {
                "text": text,
                "language": self.language,
                "file_path": str(wav_path),
            }
            if self.speaker_wav:
                sp = Path(self.speaker_wav).expanduser()
                if sp.exists():
                    kwargs["speaker_wav"] = str(sp)
                else:
                    logger.warning("[XTTS] speaker_wav not found: %s — using default voice", sp)

            logger.debug("[XTTS] Synthesizing %d chars (%s)…", len(text), self.language)
            t0 = time.monotonic()
            self._model.tts_to_file(**kwargs)
            logger.debug("[XTTS] Synthesis done in %.2f s", time.monotonic() - t0)
        except Exception as exc:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise XttsUnavailable(f"XTTS synthesis failed: {exc}") from exc

        return wav_path

    def play_file(self, wav_path: Path, stop_event=None) -> None:
        """Play WAV file through sounddevice with stop_event support."""
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore

            with wave.open(str(wav_path), "rb") as wav:
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                frames = wav.readframes(wav.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0
                if channels > 1:
                    audio = audio.reshape(-1, channels)

            sd.play(audio, sample_rate)
            while sd.get_stream().active:
                if stop_event is not None and stop_event.is_set():
                    sd.stop()
                    return
                time.sleep(0.05)
            sd.wait()
            return
        except Exception as exc:
            logger.debug("[XTTS] sounddevice playback unavailable: %s", exc)

        # OS-level fallbacks
        import platform
        import shutil
        import subprocess

        system = platform.system().lower()
        if system == "linux":
            for cmd in [["aplay", str(wav_path)], ["ffplay", "-nodisp", "-autoexit", str(wav_path)]]:
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
                    return
        elif system == "darwin":
            subprocess.run(["afplay", str(wav_path)], timeout=120)
            return
        elif system == "windows":
            subprocess.run(
                ["powershell", "-c", f"(New-Object Media.SoundPlayer '{wav_path}').PlaySync();"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
            )
            return
        raise XttsUnavailable("No audio playback backend found. Install sounddevice.")

    def speak(self, text: str, cleanup: bool = True, stop_event=None) -> Path:
        """Synthesize and play text. Main entry point for TTSModule."""
        wav_path = self.synthesize_to_file(text)
        try:
            self.play_file(wav_path, stop_event=stop_event)
        finally:
            if cleanup:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    pass
        return wav_path
