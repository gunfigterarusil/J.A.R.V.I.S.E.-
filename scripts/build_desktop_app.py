"""Build JAV as a movable desktop application with PyInstaller.

Usage:
    python scripts/bootstrap_dependencies.py --with-build --with-gui
    python scripts/build_desktop_app.py

Output:
    dist/JAV/JAV.exe          windowed desktop app, double-click friendly
    dist/JAV/JAV-Console.exe  console helper for --doctor, --chat, --service

The output folder is portable-ready: it contains .env, data/ folders, launchers,
README and CHANGELOG. LLMs are intentionally NOT bundled; configure Ollama/API
providers inside the app Settings Center or .env.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
APP_DIST = DIST_ROOT / "JAV"
sep = ";" if os.name == "nt" else ":"

COMMON = [
    "--noconfirm",
    "--clean",
    "--onedir",
    "--collect-submodules", "core",
    "--collect-submodules", "modules",
    "--collect-submodules", "interfaces",
    "--collect-submodules", "scripts",
    "--add-data", f"{ROOT / 'modules'}{sep}modules",
    "--add-data", f"{ROOT / 'interfaces'}{sep}interfaces",
    "--add-data", f"{ROOT / 'core'}{sep}core",
    "--add-data", f"{ROOT / 'scripts'}{sep}scripts",
]

PORTABLE_ENV = """# JAV portable configuration. Paths are relative to this folder.
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
ACTION_WORKSPACE_PATH=data/workspace
SCREENSHOT_DIR=data/screenshots
RUNTIME_LOG_DIR=data/brain/logs
RUNTIME_HEARTBEAT_FILE=data/brain/runtime_heartbeat.json
RUNTIME_PID_FILE=data/brain/runtime.pid
MODEL_PROFILE=offline
MODEL_FAST_PROVIDER=ollama
MODEL_FAST_NAME=qwen2.5:7b
MODEL_REASON_PROVIDER=ollama
MODEL_REASON_NAME=llama3.1:8b
MODEL_CODE_PROVIDER=ollama
MODEL_CODE_NAME=qwen2.5-coder:7b
MODEL_ACTION_PROVIDER=ollama
MODEL_ACTION_NAME=qwen2.5:7b
PROACTIVE_SPEAK_NOTIFICATIONS=false
GUI_AUTOMATION_AUTO_ENABLED=false
DESKTOP_NOTIFICATIONS_ENABLED=true
"""


def run_pyinstaller(name: str, windowed: bool) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", *COMMON, "--name", name]
    cmd.append("--windowed" if windowed else "--console")
    cmd.append(str(ROOT / "main.py"))
    print("Building", name)
    print(" ".join(str(x) for x in cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))


def copy_optional(src_name: str, dst: Path) -> None:
    src = ROOT / src_name
    if not src.exists():
        return
    target = dst / src.name
    if src.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.log", "build", "dist"))
    else:
        shutil.copy2(src, target)


def merge_console_build() -> None:
    console = DIST_ROOT / "JAV-Console"
    if not console.exists():
        return
    exe_name = "JAV-Console.exe" if os.name == "nt" else "JAV-Console"
    src_exe = console / exe_name
    if src_exe.exists():
        shutil.copy2(src_exe, APP_DIST / exe_name)
    # Keep only the console executable; both builds share the same bundled resources layout.
    shutil.rmtree(console, ignore_errors=True)


def write_launchers(dst: Path) -> None:
    (dst / "run_desktop.bat").write_text(
        "@echo off\r\n"
        "cd /d %~dp0\r\n"
        "if not exist .env (\r\n"
        "  echo Creating portable configuration...\r\n"
        "  JAV-Console.exe --init-portable .\r\n"
        ")\r\n"
        "start \"JAV\" \"%~dp0JAV.exe\"\r\n",
        encoding="utf-8",
    )
    (dst / "run_doctor.bat").write_text(
        "@echo off\r\ncd /d %~dp0\r\nJAV-Console.exe --doctor\r\npause\r\n",
        encoding="utf-8",
    )
    (dst / "run_chat.bat").write_text(
        "@echo off\r\ncd /d %~dp0\r\nJAV-Console.exe --chat\r\npause\r\n",
        encoding="utf-8",
    )
    (dst / "run_voice_doctor.bat").write_text(
        "@echo off\r\ncd /d %~dp0\r\nJAV-Console.exe --voice-doctor\r\npause\r\n",
        encoding="utf-8",
    )
    sh = dst / "run_desktop.sh"
    sh.write_text('#!/usr/bin/env bash\ncd "$(dirname "$0")"\n[ -f .env ] || ./JAV-Console --init-portable .\n./JAV &\n', encoding="utf-8")
    doctor = dst / "run_doctor.sh"
    doctor.write_text('#!/usr/bin/env bash\ncd "$(dirname "$0")"\n./JAV-Console --doctor\n', encoding="utf-8")
    chat = dst / "run_chat.sh"
    chat.write_text('#!/usr/bin/env bash\ncd "$(dirname "$0")"\n./JAV-Console --chat\n', encoding="utf-8")
    for f in (sh, doctor, chat):
        try:
            f.chmod(0o755)
        except Exception:
            pass


def prepare_dist() -> None:
    for item in ["README.md", "CHANGELOG.md", ".env.example", "requirements.txt"]:
        copy_optional(item, APP_DIST)
    for folder in ["data/brain/logs", "data/workspace", "data/screenshots"]:
        (APP_DIST / folder).mkdir(parents=True, exist_ok=True)
    env = APP_DIST / ".env"
    if not env.exists():
        env.write_text(PORTABLE_ENV, encoding="utf-8")
    write_launchers(APP_DIST)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Build JAV desktop app with PyInstaller")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip removing dist/JAV and dist/JAV-Console before building",
    )
    args = parser.parse_args()

    if not args.no_clean:
        shutil.rmtree(APP_DIST, ignore_errors=True)
        shutil.rmtree(DIST_ROOT / "JAV-Console", ignore_errors=True)

    run_pyinstaller("JAV", windowed=True)
    run_pyinstaller("JAV-Console", windowed=False)
    merge_console_build()
    prepare_dist()
    print("\nDone. See dist/JAV/")
    print("Move dist/JAV anywhere, including an external drive. It stores data in dist/JAV/data by default.")
    print("LLMs are not bundled. Configure Ollama/API providers in Settings Center or .env.")


if __name__ == "__main__":
    main()
