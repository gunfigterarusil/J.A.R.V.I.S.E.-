"""JAV runtime doctor: checks common startup/runtime problems without launching the GUI.

V15.5: adds DoctorCheck dataclass and run_checks() for programmatic use by GUIDoctorPanel
and FirstLaunchWizard. The original main() still works unchanged.
"""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
for _p in (RESOURCE_ROOT, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Structured result for programmatic use (GUIDoctorPanel, FirstLaunchWizard)
# ---------------------------------------------------------------------------

@dataclass
class DoctorCheck:
    name: str
    passed: bool
    detail: str = ""
    fixable: bool = False
    fix_cmd: str = ""           # e.g. "pip install psutil"
    category: str = "required"  # "required" | "optional" | "external"


def run_checks(root: Optional[Path] = None) -> List[DoctorCheck]:
    """Return structured check results without printing anything.

    Used by GUIDoctorPanel and DependencyCheckStep in the wizard.
    """
    if root is None:
        root = ROOT

    results: List[DoctorCheck] = []

    # ── File structure ───────────────────────────────────────────────────────
    for fname in ("main.py", "config.py", "README.md", "CHANGELOG.md"):
        exists = (root / fname).exists()
        results.append(DoctorCheck(
            name=f"{fname} exists",
            passed=exists,
            detail="" if exists else f"not found at {root / fname}",
            category="required",
        ))

    results.append(DoctorCheck(
        name="modules directory",
        passed=(root / "modules").exists() or (RESOURCE_ROOT / "modules").exists(),
        category="required",
    ))
    results.append(DoctorCheck(
        name="interfaces directory",
        passed=(root / "interfaces").exists() or (RESOURCE_ROOT / "interfaces").exists(),
        category="required",
    ))

    # ── Core imports ─────────────────────────────────────────────────────────
    for mod in [
        "config",
        "core.kernel",
        "core.llm_router",
        "interfaces.desktop.desktop_app",
        "interfaces.desktop.settings_window",
    ]:
        try:
            importlib.import_module(mod)
            results.append(DoctorCheck(name=f"import {mod}", passed=True,
                                       category="required"))
        except Exception as exc:
            results.append(DoctorCheck(
                name=f"import {mod}",
                passed=False,
                detail=repr(exc),
                category="required",
            ))

    # ── Optional Python packages ─────────────────────────────────────────────
    optional_packages = [
        ("tkinter",        "Desktop UI / Tkinter",   "",                   False),
        ("psutil",         "System monitor",          "psutil",             True),
        ("mss",            "Screen capture",          "mss",                True),
        ("PIL",            "Pillow image support",    "Pillow",             True),
        ("pytesseract",    "OCR Python binding",      "pytesseract",        True),
        ("pyautogui",      "GUI automation",          "pyautogui",          True),
        ("sounddevice",    "Microphone input",        "sounddevice",        True),
        ("faster_whisper", "Whisper STT",             "faster-whisper",     True),
        ("pyttsx3",        "pyttsx3 fallback TTS",    "pyttsx3",            True),
    ]
    for mod, name, pkg, fixable in optional_packages:
        try:
            importlib.import_module(mod)
            results.append(DoctorCheck(name=name, passed=True, detail=mod,
                                       category="optional"))
        except Exception as exc:
            fix_cmd = f"pip install {pkg}" if (fixable and pkg) else ""
            # On frozen builds pip won't work — suppress the fix button
            if getattr(sys, "frozen", False):
                fixable = False
                fix_cmd = ""
            results.append(DoctorCheck(
                name=name,
                passed=False,
                detail=f"{mod} not available",
                fixable=fixable,
                fix_cmd=fix_cmd,
                category="optional",
            ))

    # ── External tools ───────────────────────────────────────────────────────
    for tool, desc, optional_tool in [
        ("tesseract", "Tesseract OCR", False),
        ("piper",     "Piper TTS",     True),
        ("ollama",    "Ollama (local LLM)", True),
    ]:
        path = shutil.which(tool)
        results.append(DoctorCheck(
            name=desc,
            passed=path is not None,
            detail=path or f"not found in PATH",
            category="optional" if optional_tool else "external",
        ))

    # ── Microphone availability ───────────────────────────────────────────────
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        has_mic = any(d["max_input_channels"] > 0 for d in devices)
        results.append(DoctorCheck(
            name="Microphone available",
            passed=has_mic,
            detail="input device found" if has_mic else "no input device detected",
            category="optional",
        ))
    except Exception:
        results.append(DoctorCheck(
            name="Microphone available",
            passed=False,
            detail="sounddevice not available",
            category="optional",
        ))

    # ── Write permissions ─────────────────────────────────────────────────────
    try:
        test_file = root / ".write_test_tmp"
        test_file.touch()
        test_file.unlink()
        results.append(DoctorCheck(
            name="Write permission in app folder",
            passed=True,
            category="required",
        ))
    except Exception as exc:
        results.append(DoctorCheck(
            name="Write permission in app folder",
            passed=False,
            detail=repr(exc),
            category="required",
        ))

    return results


# ---------------------------------------------------------------------------
# Original CLI entry point (unchanged behaviour)
# ---------------------------------------------------------------------------

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
    ok_all &= check("modules directory exists",
                    (ROOT / "modules").exists() or (RESOURCE_ROOT / "modules").exists())
    ok_all &= check("interfaces directory exists",
                    (ROOT / "interfaces").exists() or (RESOURCE_ROOT / "interfaces").exists())

    print("\nCore imports:")
    for mod in [
        "config",
        "core.kernel",
        "core.llm_router",
        "interfaces.desktop.desktop_app",
        "interfaces.desktop.settings_window",
    ]:
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
    check("Tesseract executable", shutil.which("tesseract") is not None,
          shutil.which("tesseract") or "install tesseract-ocr")
    check("Piper executable", shutil.which("piper") is not None,
          shutil.which("piper") or "optional; set PIPER_EXECUTABLE/PIPER_MODEL_PATH")
    check("Ollama executable", shutil.which("ollama") is not None,
          shutil.which("ollama") or "optional; needed for local models")

    print("\nSmoke tests:")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--help"],
            cwd=str(ROOT), text=True, capture_output=True, timeout=20,
        )
        ok_all &= check(
            "main.py --help",
            result.returncode == 0,
            (result.stderr or result.stdout).splitlines()[0]
            if (result.stderr or result.stdout) else "",
        )
    except Exception as exc:
        ok_all &= check("main.py --help", False, repr(exc))

    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--chat"],
            input="/runtime\n/exit\n",
            cwd=str(ROOT), text=True, capture_output=True, timeout=30,
        )
        ok_all &= check(
            "chat smoke test",
            result.returncode == 0,
            "returned 0"
            if result.returncode == 0
            else (result.stderr[-500:] or result.stdout[-500:]),
        )
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
