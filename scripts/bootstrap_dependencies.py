"""Install/check JAV Python dependencies for source/portable runs.

This script is intentionally separate from model setup. It installs Python packages
needed by the application, but it does NOT install local LLMs, Ollama models, API
keys, Piper voice models, or Tesseract language packs.

Usage:
    python scripts/bootstrap_dependencies.py
    python scripts/bootstrap_dependencies.py --core-only
    python scripts/bootstrap_dependencies.py --with-voice --with-screen --with-gui
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CORE_PACKAGES = [
    "python-dotenv",
    "fastapi",
    "uvicorn",
    "websockets",
    "pydantic",
    "httpx",
    "psutil",
]
VOICE_PACKAGES = ["sounddevice", "numpy", "faster-whisper", "pyttsx3"]
SCREEN_PACKAGES = ["mss", "pillow", "pytesseract"]
GUI_PACKAGES = ["pyautogui", "pyperclip", "pystray", "plyer"]
BUILD_PACKAGES = ["pyinstaller"]


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Install/check JAV dependencies")
    parser.add_argument("--core-only", action="store_true", help="Install only core runtime packages")
    parser.add_argument("--with-voice", action="store_true", help="Install voice dependencies")
    parser.add_argument("--with-screen", action="store_true", help="Install screen/OCR Python dependencies")
    parser.add_argument("--with-gui", action="store_true", help="Install GUI automation/tray dependencies")
    parser.add_argument("--with-build", action="store_true", help="Install PyInstaller for building exe")
    parser.add_argument("--all", action="store_true", help="Install core + voice + screen + GUI + build packages")
    args = parser.parse_args()

    packages = list(CORE_PACKAGES)
    if args.all or args.with_voice:
        packages += VOICE_PACKAGES
    if args.all or args.with_screen:
        packages += SCREEN_PACKAGES
    if args.all or args.with_gui:
        packages += GUI_PACKAGES
    if args.all or args.with_build:
        packages += BUILD_PACKAGES

    # De-duplicate preserving order.
    packages = list(dict.fromkeys(packages))

    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", *packages])

    print("\nDone. LLMs are not installed by this script.")
    print("Configure Ollama/API keys in the app Settings Center or .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
