"""Create a movable portable JAV folder from an existing PyInstaller build.

Usage:
    python scripts/build_desktop_app.py
    python scripts/make_portable_release.py E:/JAV

The resulting folder stores memory/workspace/screenshots inside data/ so it can
be moved to another drive/folder and still work.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "JAV"

ENV_TEXT = """# JAV portable configuration. Paths are relative to this folder.
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
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create movable portable JAV folder")
    parser.add_argument("target", help="Target folder, for example E:/JAV")
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()
    if not DIST.exists():
        raise SystemExit("dist/JAV does not exist. Run: python scripts/build_desktop_app.py")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DIST, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.log"))
    for folder in ["data/brain/logs", "data/workspace", "data/screenshots"]:
        (target / folder).mkdir(parents=True, exist_ok=True)
    env = target / ".env"
    if not env.exists():
        env.write_text(ENV_TEXT, encoding="utf-8")
    print(f"Portable JAV created at: {target}")
    print("You can move this folder to another drive. Run JAV.exe or run_desktop.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
