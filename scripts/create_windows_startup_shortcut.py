"""Create a Windows startup .bat launcher for JAV watchdog.

It writes a .bat file into the current user's Startup folder so JAV can start
with Windows. Run this script from the JAV folder on Windows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        print("APPDATA is not set. This script is intended for Windows.")
        return 1
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True, exist_ok=True)
    bat = startup / "JAV Watchdog.bat"
    content = f"""@echo off
cd /d "{ROOT}"
start "JAV Watchdog" /min "{sys.executable}" "{ROOT / 'scripts' / 'watchdog.py'}"
"""
    bat.write_text(content, encoding="utf-8")
    print(f"Wrote startup launcher: {bat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
