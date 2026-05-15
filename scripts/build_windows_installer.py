"""Build Windows installer with Inno Setup.

Requirements:
    1. Run on Windows.
    2. Install Inno Setup.
    3. Build the app first: python scripts/build_desktop_app.py

Usage:
    python scripts/build_windows_installer.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "installer" / "JAV_Setup.iss"
DIST = ROOT / "dist" / "JAV"


def find_iscc() -> str | None:
    direct = shutil.which("ISCC.exe") or shutil.which("iscc")
    if direct:
        return direct
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def main() -> None:
    if not DIST.exists():
        raise SystemExit("dist/JAV not found. Run: python scripts/build_desktop_app.py")
    if not ISS.exists():
        raise SystemExit(f"Installer script not found: {ISS}")
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup compiler was not found.")
        print("Install Inno Setup, then either run this script again or open:")
        print(f"  {ISS}")
        print("and press Compile.")
        raise SystemExit(1)
    cmd = [iscc, str(ISS)]
    print("Building installer:")
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    print("Done. See installer_output/JAV_Setup.exe")


if __name__ == "__main__":
    main()
