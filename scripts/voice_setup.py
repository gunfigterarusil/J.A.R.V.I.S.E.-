"""Voice setup diagnostics and smoke tests for JAV.

This script is safe to run before voice mode. It checks optional Python
packages, microphone devices, Piper configuration, and pyttsx3 fallback TTS.
It does not require the cognitive kernel to start.

Usage:
    python scripts/voice_setup.py --check
    python scripts/voice_setup.py --list-mics
    python scripts/voice_setup.py --test-pyttsx3 "Hello"
    python scripts/voice_setup.py --test-piper "Hello"
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env when available, without requiring python-dotenv.
def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for raw in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

_load_env()


@dataclass
class VoiceCheck:
    name: str
    status: str  # OK | WARN | FAIL | INFO
    detail: str = ""
    fix: str = ""


def _import_check(module: str, label: str, fix: str = "") -> VoiceCheck:
    try:
        importlib.import_module(module)
        return VoiceCheck(label, "OK", module)
    except Exception as exc:
        return VoiceCheck(label, "WARN", f"{module} unavailable: {exc}", fix)


def _path_exists(path: str) -> bool:
    return bool(path) and Path(path).expanduser().exists()


def collect_voice_checks() -> List[VoiceCheck]:
    checks: List[VoiceCheck] = []
    checks.append(_import_check("numpy", "numpy", "pip install numpy"))
    checks.append(_import_check("sounddevice", "Microphone backend: sounddevice", "pip install sounddevice"))
    checks.append(_import_check("faster_whisper", "STT backend: faster-whisper", "pip install faster-whisper"))
    checks.append(_import_check("pyttsx3", "Fallback TTS: pyttsx3", "pip install pyttsx3"))

    backend = os.environ.get("VOICE_TTS_BACKEND", "auto").strip().lower() or "auto"
    checks.append(VoiceCheck("VOICE_TTS_BACKEND", "INFO", backend))

    piper_exe = os.environ.get("PIPER_EXECUTABLE", "piper") or "piper"
    piper_resolved = str(Path(piper_exe).expanduser()) if Path(piper_exe).expanduser().exists() else (shutil.which(piper_exe) or "")
    if piper_resolved:
        checks.append(VoiceCheck("Piper executable", "OK", piper_resolved))
    else:
        checks.append(VoiceCheck("Piper executable", "WARN", f"not found: {piper_exe}", "Install Piper CLI or set PIPER_EXECUTABLE"))

    model = os.environ.get("PIPER_MODEL_PATH", "")
    if model and _path_exists(model):
        checks.append(VoiceCheck("Piper voice model", "OK", str(Path(model).expanduser())))
    elif backend == "piper":
        checks.append(VoiceCheck("Piper voice model", "FAIL", "PIPER_MODEL_PATH is missing or invalid", "Set PIPER_MODEL_PATH to a .onnx voice file"))
    else:
        checks.append(VoiceCheck("Piper voice model", "WARN", "not configured; pyttsx3 fallback can still work", "Set PIPER_MODEL_PATH to use Piper"))

    try:
        import sounddevice as sd  # type: ignore
        devices = sd.query_devices()
        inputs = [d for d in devices if int(d.get("max_input_channels", 0)) > 0]
        outputs = [d for d in devices if int(d.get("max_output_channels", 0)) > 0]
        checks.append(VoiceCheck("Audio input devices", "OK" if inputs else "WARN", f"{len(inputs)} microphone/input device(s)"))
        checks.append(VoiceCheck("Audio output devices", "OK" if outputs else "WARN", f"{len(outputs)} speaker/output device(s)"))
    except Exception as exc:
        checks.append(VoiceCheck("Audio devices", "WARN", f"could not query audio devices: {exc}", "Install sounddevice and check OS audio drivers"))

    input_mode = os.environ.get("VOICE_INPUT_MODE", "continuous")
    wake_word = os.environ.get("VOICE_WAKE_WORD", "")
    start_muted = os.environ.get("VOICE_START_MUTED", "false")
    checks.append(VoiceCheck("Voice companion mode", "INFO", f"input_mode={input_mode}, wake_word={bool(wake_word)}, start_muted={start_muted}"))

    stt_model = os.environ.get("VOICE_STT_MODEL", "small")
    stt_device = os.environ.get("VOICE_STT_DEVICE", "cpu")
    stt_compute = os.environ.get("VOICE_STT_COMPUTE_TYPE", "int8")
    checks.append(VoiceCheck("STT config", "INFO", f"model={stt_model}, device={stt_device}, compute={stt_compute}"))
    return checks


def format_voice_report(checks: Optional[List[VoiceCheck]] = None) -> str:
    checks = checks if checks is not None else collect_voice_checks()
    lines = ["JAV Voice Setup Report", ""]
    for c in checks:
        extra = f" — {c.detail}" if c.detail else ""
        lines.append(f"[{c.status}] {c.name}{extra}")
        if c.fix and c.status in {"WARN", "FAIL"}:
            lines.append(f"      fix: {c.fix}")
    lines.append("")
    lines.append("Install voice Python deps:")
    lines.append("  python scripts/bootstrap_dependencies.py --with-voice")
    lines.append("Start voice mode:")
    lines.append("  python main.py --voice")
    lines.append("Push-to-talk mode:")
    lines.append("  python main.py --voice-ptt")
    return "\n".join(lines)


def list_microphones() -> str:
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:
        return f"sounddevice unavailable: {exc}\nInstall with: pip install sounddevice"
    lines = ["Audio input devices:"]
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_input_channels", 0)) > 0:
                default = " (default)" if idx == sd.default.device[0] else ""
                lines.append(f"  [{idx}] {dev.get('name')} — inputs={dev.get('max_input_channels')}{default}")
    except Exception as exc:
        return f"Could not list devices: {exc}"
    if len(lines) == 1:
        lines.append("  no microphone/input devices found")
    return "\n".join(lines)


def test_pyttsx3(text: str) -> int:
    try:
        from interfaces.voice.pyttsx3_tts import Pyttsx3TTS
        tts = Pyttsx3TTS(
            voice_id=os.environ.get("PYTTSX3_VOICE_ID", ""),
            rate=int(os.environ.get("PYTTSX3_RATE", "175")),
            volume=float(os.environ.get("PYTTSX3_VOLUME", "1.0")),
        )
        tts.speak(text)
        print("pyttsx3 test completed.")
        return 0
    except Exception as exc:
        print(f"pyttsx3 test failed: {exc}")
        return 1


def test_piper(text: str) -> int:
    try:
        from interfaces.voice.piper_tts import PiperTTS
        tts = PiperTTS(
            executable=os.environ.get("PIPER_EXECUTABLE", "piper"),
            model_path=os.environ.get("PIPER_MODEL_PATH", ""),
            config_path=os.environ.get("PIPER_CONFIG_PATH", ""),
            speaker=os.environ.get("PIPER_SPEAKER", ""),
            length_scale=float(os.environ.get("PIPER_LENGTH_SCALE", "1.0")),
            noise_scale=float(os.environ.get("PIPER_NOISE_SCALE", "0.667")),
            noise_w=float(os.environ.get("PIPER_NOISE_W", "0.8")),
            output_dir=os.environ.get("PIPER_OUTPUT_DIR", ""),
        )
        tts.speak(text)
        print("Piper test completed.")
        return 0
    except Exception as exc:
        print(f"Piper test failed: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="JAV voice setup diagnostics")
    parser.add_argument("--check", action="store_true", help="Print voice setup report")
    parser.add_argument("--list-mics", action="store_true", help="List microphone/input devices")
    parser.add_argument("--test-pyttsx3", nargs="?", const="JAV pyttsx3 voice test.", help="Speak a test phrase with pyttsx3")
    parser.add_argument("--test-piper", nargs="?", const="JAV Piper voice test.", help="Speak a test phrase with Piper")
    args = parser.parse_args()

    if args.list_mics:
        print(list_microphones())
        return 0
    if args.test_pyttsx3 is not None:
        return test_pyttsx3(args.test_pyttsx3)
    if args.test_piper is not None:
        return test_piper(args.test_piper)
    print(format_voice_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
