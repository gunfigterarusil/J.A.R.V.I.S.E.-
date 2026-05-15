"""Build Windows installer using Inno Setup.

Usage on Windows:
    python scripts/bootstrap_dependencies.py --with-build --with-gui --with-screen --with-voice
    python scripts/build_desktop_app.py
    python scripts/build_windows_installer.py

Requires Inno Setup Compiler (ISCC.exe) in PATH or set INNO_SETUP_COMPILER.
The installer allows choosing the installation folder and initializes JAV in
portable/movable mode, storing data under <install folder>/data.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "installer" / "JAV_Setup.iss"
DIST = ROOT / "dist" / "JAV"


def main() -> int:
    if not DIST.exists():
        raise SystemExit("dist/JAV not found. Run: python scripts/build_desktop_app.py")
    iscc = os.environ.get("INNO_SETUP_COMPILER") or shutil.which("ISCC.exe") or shutil.which("iscc")
    if not iscc:
        raise SystemExit("Inno Setup compiler not found. Install Inno Setup and add ISCC.exe to PATH, or set INNO_SETUP_COMPILER.")
    subprocess.check_call([iscc, str(ISS)], cwd=str(ROOT))
    print("Installer created in installer_output/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
