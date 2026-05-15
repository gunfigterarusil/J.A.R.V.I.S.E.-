"""Acoustic wake word detection for voice companion mode.

Uses openWakeWord (free, local, CPU-only) to detect a trigger phrase in real-time.
The detector streams the mic at low power (1280-sample / 80ms chunks) and returns
True as soon as the configured wake word is heard.

Usage:
    detector = OpenWakeWordDetector("hey_jarvis", threshold=0.5)
    detected = detector.listen_for_wake_word(stop_event=some_event)

Install:
    pip install openwakeword

Download community models:
    python -c "from openwakeword.utils import download_models; download_models()"
    # Or for a specific model:
    python -c "from openwakeword.utils import download_models; download_models(['hey_jarvis'])"

Model path can be a model name (downloaded to default cache) or an absolute .tflite/.onnx path.
"""
from __future__ import annotations

import logging
import queue as _q
import threading
from typing import Optional

logger = logging.getLogger("voice.wwd")

# openWakeWord uses 1280-sample chunks at 16kHz = exactly 80ms per chunk
_CHUNK_SAMPLES = 1280
_SAMPLE_RATE = 16000


class WakeWordUnavailable(RuntimeError):
    """Raised when openWakeWord or sounddevice is not installed."""


class OpenWakeWordDetector:
    """Low-power mic stream that detects a wake word using openWakeWord models."""

    @staticmethod
    def is_available() -> bool:
        try:
            import openwakeword  # noqa: F401
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
            return True
        except ImportError:
            return False

    def __init__(
        self,
        model_path_or_name: str,
        threshold: float = 0.5,
        sample_rate: int = _SAMPLE_RATE,
    ) -> None:
        self.model_path_or_name = model_path_or_name
        self.threshold = float(threshold)
        self.sample_rate = int(sample_rate)
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from openwakeword.model import Model  # type: ignore
        except ImportError as exc:
            raise WakeWordUnavailable(
                "openWakeWord not installed. Run: pip install openwakeword"
            ) from exc
        logger.info("[WakeWord] Loading openWakeWord model: %s", self.model_path_or_name)
        try:
            self._model = Model(
                wakeword_models=[self.model_path_or_name],
                inference_framework="onnx",
            )
        except Exception:
            # Some versions don't support inference_framework kwarg
            try:
                self._model = Model(wakeword_models=[self.model_path_or_name])
            except Exception as exc:
                raise WakeWordUnavailable(f"Failed to load wake word model {self.model_path_or_name!r}: {exc}") from exc
        logger.info("[WakeWord] Model loaded (threshold=%.2f)", self.threshold)
        return self._model

    def listen_for_wake_word(self, stop_event: Optional[threading.Event] = None) -> bool:
        """Stream microphone until wake word is detected or stop_event fires.

        Returns True on wake word detection, False if stop_event was set.
        Blocks the calling thread — use asyncio.to_thread() from async code.
        """
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            raise WakeWordUnavailable("sounddevice or numpy not installed") from exc

        model = self._ensure_model()
        model.reset()   # clear internal state from any previous detection

        buf: _q.Queue = _q.Queue()

        def _cb(indata, frames, t, status):
            buf.put(indata.copy())

        logger.debug("[WakeWord] Listening for wake word...")

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=_CHUNK_SAMPLES,
            callback=_cb,
        ):
            while True:
                if stop_event is not None and stop_event.is_set():
                    logger.debug("[WakeWord] Stopped by stop_event")
                    return False
                try:
                    chunk = buf.get(timeout=0.2)
                except _q.Empty:
                    continue

                # openWakeWord expects 1-D int16 array of exactly 1280 samples
                flat = chunk.reshape(-1)
                if len(flat) != _CHUNK_SAMPLES:
                    continue

                try:
                    prediction = model.predict(flat)
                except Exception as exc:
                    logger.warning("[WakeWord] predict error: %s", exc)
                    continue

                # prediction is {model_name: float_score}
                score = 0.0
                for v in prediction.values():
                    if isinstance(v, (int, float)) and v > score:
                        score = float(v)

                if score >= self.threshold:
                    logger.info("[WakeWord] Detected! score=%.3f (threshold=%.2f)", score, self.threshold)
                    model.reset()
                    return True
