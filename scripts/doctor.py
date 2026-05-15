"""JAV runtime doctor: checks common startup/runtime problems without launching the GUI."""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {name}{': ' + detail if detail else ''}")
    return ok


def optional_import(module: str, feature: str) -> None:
    try:
        importlib.import_module(module)
        check(feature, True, module)
    except Exception as exc:
        check(feature, False, f"{module} not available ({exc})")


def main() -> int:
    print("JAV Doctor")
    print(f"Root: {ROOT}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"OS: {platform.platform()}")
    print()

    ok_all = True
    ok_all &= check("main.py exists", (ROOT / "main.py").exists())
    ok_all &= check("config.py exists", (ROOT / "config.py").exists())
    ok_all &= check("README.md exists", (ROOT / "README.md").exists())
    ok_all &= check("CHANGELOG.md exists", (ROOT / "CHANGELOG.md").exists())
    ok_all &= check("modules directory exists", (ROOT / "modules").exists())
    ok_all &= check("interfaces directory exists", (ROOT / "interfaces").exists())

    print("\nCore imports:")
    for mod in ["config", "core.kernel", "core.llm_router", "interfaces.desktop.desktop_app", "interfaces.desktop.settings_window"]:
        try:
            importlib.import_module(mod)
            ok_all &= check(mod, True)
        except Exception as exc:
            ok_all &= check(mod, False, repr(exc))

    print("\nOptional features:")
    optional_import("tkinter", "Desktop UI / Tkinter")
    optional_import("psutil", "System monitor")
    optional_import("mss", "Screen capture")
    optional_import("PIL", "Pillow image support")
    optional_import("pytesseract", "OCR Python binding")
    optional_import("pyautogui", "GUI automation")
    optional_import("sounddevice", "Microphone input")
    optional_import("faster_whisper", "Whisper STT")
    optional_import("pyttsx3", "pyttsx3 fallback TTS")

    print("\nExternal tools:")
    check("Tesseract executable", shutil.which("tesseract") is not None, shutil.which("tesseract") or "install tesseract-ocr")
    check("Piper executable", shutil.which("piper") is not None, shutil.which("piper") or "optional; set PIPER_EXECUTABLE/PIPER_MODEL_PATH")
    check("Ollama executable", shutil.which("ollama") is not None, shutil.which("ollama") or "optional; needed for local models")

    print("\nSmoke tests:")
    try:
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--help"], cwd=str(ROOT), text=True, capture_output=True, timeout=20)
        ok_all &= check("main.py --help", result.returncode == 0, (result.stderr or result.stdout).splitlines()[0] if (result.stderr or result.stdout) else "")
    except Exception as exc:
        ok_all &= check("main.py --help", False, repr(exc))

    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--chat"],
            input="/runtime\n/exit\n",
            cwd=str(ROOT), text=True, capture_output=True, timeout=30,
        )
        ok_all &= check("chat smoke test", result.returncode == 0, "returned 0" if result.returncode == 0 else (result.stderr[-500:] or result.stdout[-500:]))
    except Exception as exc:
        ok_all &= check("chat smoke test", False, repr(exc))

    print("\nResult:")
    if ok_all:
        print("Core runtime looks usable. Optional FAIL items only affect their specific features.")
        return 0
    print("Some required checks failed. See messages above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
