"""Build a one-folder desktop app with PyInstaller.

This script intentionally does not bundle LLM models. Users configure Ollama/API
inside .env or the app settings.
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "JAV"


def main() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing. Run: pip install pyinstaller")
        raise SystemExit(1)
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "JAV",
        str(ROOT / "main.py"),
    ], cwd=str(ROOT))
    DIST.mkdir(parents=True, exist_ok=True)
    for name in ["README.md", "CHANGELOG.md", ".env.example", "requirements.txt", "run_desktop.bat", "run_doctor.bat"]:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, DIST / name)
    for sub in ["data/brain", "data/workspace", "data/screenshots"]:
        (DIST / sub).mkdir(parents=True, exist_ok=True)
    env = DIST / ".env"
    if not env.exists():
        env.write_text("JAV_PORTABLE=true\nJARVIS_DATA_DIR=data/brain\nACTION_WORKSPACE_PATH=data/workspace\nSCREENSHOT_DIR=data/screenshots\n", encoding="utf-8")
    print(f"Built: {DIST}")


if __name__ == "__main__":
    main()
