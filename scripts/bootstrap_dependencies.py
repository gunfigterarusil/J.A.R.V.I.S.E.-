"""Install JAV runtime dependencies.

Usage:
  python scripts/bootstrap_dependencies.py
  python scripts/bootstrap_dependencies.py --optional
"""
from __future__ import annotations
import argparse
import subprocess
import sys

CORE = ["fastapi>=0.110", "uvicorn>=0.27", "python-dotenv>=1.0"]
OPTIONAL = ["sounddevice", "numpy", "faster-whisper", "pyttsx3", "mss", "pillow", "pytesseract", "pyinstaller"]


def install(pkgs: list[str]) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--optional", action="store_true", help="Install voice/screen/build optional dependencies too")
    args = ap.parse_args()
    install(CORE)
    if args.optional:
        install(OPTIONAL)


if __name__ == "__main__":
    main()
