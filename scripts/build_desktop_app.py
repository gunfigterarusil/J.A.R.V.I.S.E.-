"""Build JAV desktop app with PyInstaller.

Usage:
    pip install pyinstaller
    python scripts/build_desktop_app.py

Output:
    dist/JAV/JAV.exe    on Windows
    dist/JAV/JAV        on Linux/macOS

The script also copies README.md, CHANGELOG.md, .env.example and launchers
into dist/JAV so the output folder can be used as a portable app base.
"""
from __future__ import annotations

import os
import shutil
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


def copy_optional(src_name: str, dst: Path) -> None:
    src = ROOT / src_name
    if src.exists():
        target = dst / src.name
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.log"))
        else:
            shutil.copy2(src, target)


def write_dist_launchers(dst: Path) -> None:
    (dst / "run_desktop.bat").write_text(
        "@echo off\r\n"
        "cd /d %~dp0\r\n"
        "JAV.exe\r\n"
        "pause\r\n",
        encoding="utf-8",
    )
    sh = dst / "run_desktop.sh"
    sh.write_text('#!/usr/bin/env bash\ncd "$(dirname "$0")"\n./JAV\n', encoding="utf-8")
    try:
        sh.chmod(0o755)
    except Exception:
        pass


def main() -> None:
    print("Building desktop app:")
    print(" ".join(str(x) for x in cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))

    dist = ROOT / "dist" / "JAV"
    for item in ["README.md", "CHANGELOG.md", ".env.example", "requirements.txt"]:
        copy_optional(item, dist)
    write_dist_launchers(dist)

    print("\nDone. See dist/JAV/")
    print("For portable use, copy dist/JAV to your external drive and create .env with JAV_PORTABLE=true.")


if __name__ == "__main__":
    main()
