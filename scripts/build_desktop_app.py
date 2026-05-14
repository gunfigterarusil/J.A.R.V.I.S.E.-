"""Build JAV desktop app with PyInstaller.

Usage:
    pip install pyinstaller
    python scripts/build_desktop_app.py

Output:
    dist/JAV/JAV.exe    on Windows
    dist/JAV/JAV        on Linux/macOS
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sep = ";" if os.name == "nt" else ":"

cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name",
    "JAV",
    "--onedir",
    "--windowed",
    "--add-data",
    f"{ROOT / 'modules'}{sep}modules",
    "--add-data",
    f"{ROOT / 'interfaces'}{sep}interfaces",
    "--add-data",
    f"{ROOT / 'core'}{sep}core",
    str(ROOT / "main.py"),
]

print("Building desktop app:")
print(" ".join(str(x) for x in cmd))
subprocess.check_call(cmd, cwd=str(ROOT))
print("\nDone. See dist/JAV/")
