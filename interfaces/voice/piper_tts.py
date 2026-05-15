"""Piper TTS wrapper for local voice output."""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

logger = logging.getLogger("voice.piper")


class PiperUnavailable(RuntimeError):
    """Raised when Piper is not configured or cannot be executed."""


class PiperTTS:
    """Generate speech with Piper and play it locally."""

    def __init__(
        self,
        executable: str = "piper",
        model_path: str = "",
        config_path: str = "",
        speaker: str = "",
        length_scale: float = 1.0,
        noise_scale: float = 0.667,
        noise_w: float = 0.8,
        output_dir: str = "",
    ) -> None:
        self.executable = executable or "piper"
        self.model_path = model_path
        self.config_path = config_path
        self.speaker = speaker
        self.length_scale = float(length_scale)
        self.noise_scale = float(noise_scale)
        self.noise_w = float(noise_w)
        self.output_dir = Path(output_dir).expanduser() if output_dir else None

    def _resolve_executable(self) -> str:
        exe = Path(self.executable).expanduser()
        if exe.exists():
            return str(exe)
        found = shutil.which(self.executable)
        if found:
            return found
        raise PiperUnavailable(
            "Piper executable not found. Set PIPER_EXECUTABLE or install Piper CLI."
        )

    def _validate_model(self) -> str:
        if not self.model_path:
            raise PiperUnavailable(
                "Piper model is not configured. Set PIPER_MODEL_PATH in .env."
            )
        model = Path(self.model_path).expanduser()
        if not model.exists():
            raise PiperUnavailable(f"Piper model not found: {model}")
        return str(model)

    def synthesize_to_file(self, text: str) -> Path:
        """Run Piper and return the generated WAV path."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Cannot synthesize empty text")

        executable = self._resolve_executable()
        model = self._validate_model()
        out_dir = self.output_dir or Path(tempfile.gettempdir())
        out_dir.mkdir(parents=True, exist_ok=True)
        fd, wav_name = tempfile.mkstemp(prefix="jarvis_tts_", suffix=".wav", dir=str(out_dir))
        os.close(fd)
        wav_path = Path(wav_name)

        cmd = [
            executable,
            "--model", model,
            "--output_file", str(wav_path),
            "--length_scale", str(self.length_scale),
            "--noise_scale", str(self.noise_scale),
            "--noise_w", str(self.noise_w),
        ]
        if self.config_path:
            cmd.extend(["--config", str(Path(self.config_path).expanduser())])
        if self.speaker:
            cmd.extend(["--speaker", self.speaker])

        logger.debug("[Piper] Running: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise PiperUnavailable(proc.stderr.strip() or "Piper failed without stderr")
        return wav_path

    def play_file(self, wav_path: Path, stop_event=None) -> None:
        """Play WAV output with sounddevice when available, then OS fallbacks.

        stop_event: optional threading.Event — stops playback early if set.
        """
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
            logger.debug("[Piper] sounddevice playback unavailable: %s", exc)

        system = platform.system().lower()
        candidates: list[list[str]] = []
        if system == "linux":
            candidates = [["aplay", str(wav_path)], ["paplay", str(wav_path)], ["ffplay", "-nodisp", "-autoexit", str(wav_path)]]
        elif system == "darwin":
            candidates = [["afplay", str(wav_path)]]
        elif system == "windows":
            candidates = [["powershell", "-c", f"(New-Object Media.SoundPlayer '{wav_path}').PlaySync();"]]

        for cmd in candidates:
            if shutil.which(cmd[0]):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                return
        raise PiperUnavailable("No audio playback backend found. Install sounddevice or aplay/paplay/ffplay.")

    def speak(self, text: str, cleanup: bool = True, stop_event=None) -> Path:
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
