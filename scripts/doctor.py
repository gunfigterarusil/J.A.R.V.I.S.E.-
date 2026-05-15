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

    # ── First launch / portable setup state ──────────────────────────────────
    try:
        from config import KernelConfig
        cfg = KernelConfig()
        env_exists = (root / ".env").exists()
        data_dir = Path(cfg.persistence_dir).expanduser()
        if not data_dir.is_absolute():
            data_dir = root / data_dir
        setup_done = (root / ".jav_setup_complete").exists() or (data_dir / ".jav_setup_complete").exists()
        results.append(DoctorCheck(
            name="First-launch setup state",
            passed=True,
            detail=("complete" if setup_done else "not completed; run python main.py --setup"),
            category="optional",
        ))
        results.append(DoctorCheck(
            name=".env configuration file",
            passed=env_exists,
            detail=str(root / ".env") if env_exists else "missing; wizard can create it",
            category="optional",
        ))
        results.append(DoctorCheck(
            name="Memory/data directory",
            passed=data_dir.exists(),
            detail=str(data_dir),
            category="optional",
        ))
    except Exception as exc:
        results.append(DoctorCheck(
            name="First-launch setup state",
            passed=False,
            detail=repr(exc),
            category="optional",
        ))

    return results


# ---------------------------------------------------------------------------
# Original CLI entry point (unchanged behaviour)
# ---------------------------------------------------------------------------

def check(name: str, ok: bool, detail: str = "", severity: str = "required") -> bool:
    """Print a doctor result. Only required failures should fail the doctor.

    severity:
      required  -> [OK]/[FAIL] and contributes to exit code
      optional  -> [OK]/[WARN] for feature-specific dependencies
      external  -> [OK]/[WARN] for external tools such as Ollama/Tesseract
      info      -> [INFO] informational row
    """
    sev = (severity or "required").lower()
    if ok:
        mark = "OK"
    elif sev in {"optional", "external"}:
        mark = "WARN"
    elif sev == "info":
        mark = "INFO"
    else:
        mark = "FAIL"
    print(f"[{mark}] {name}{': ' + detail if detail else ''}")
    return ok if sev == "required" else True


def optional_import(module: str, feature: str, install_hint: str = "") -> None:
    try:
        importlib.import_module(module)
        check(feature, True, module, severity="optional")
    except Exception as exc:
        hint = f"; install: {install_hint}" if install_hint else ""
        check(feature, False, f"{module} not available ({exc}){hint}", severity="optional")


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
    optional_import("psutil", "System monitor", "pip install psutil")
    optional_import("mss", "Screen capture", "pip install mss")
    optional_import("PIL", "Pillow image support", "pip install Pillow")
    optional_import("pytesseract", "OCR Python binding", "pip install pytesseract")
    optional_import("pyautogui", "GUI automation", "pip install pyautogui")
    optional_import("sounddevice", "Microphone input", "pip install sounddevice")
    optional_import("faster_whisper", "Whisper STT", "pip install faster-whisper")
    optional_import("pyttsx3", "pyttsx3 fallback TTS", "pip install pyttsx3")

    print("\nExternal tools:")
    check("Tesseract executable", shutil.which("tesseract") is not None,
          shutil.which("tesseract") or "install tesseract-ocr; required only for OCR", severity="external")
    check("Piper executable", shutil.which("piper") is not None,
          shutil.which("piper") or "optional; set PIPER_EXECUTABLE/PIPER_MODEL_PATH", severity="external")
    check("Ollama executable", shutil.which("ollama") is not None,
          shutil.which("ollama") or "optional; needed only for local Ollama models", severity="external")

    print("\nSetup / portable state:")
    try:
        from config import KernelConfig
        cfg = KernelConfig()
        data_dir = Path(cfg.persistence_dir).expanduser()
        if not data_dir.is_absolute():
            data_dir = ROOT / data_dir
        setup_done = (ROOT / ".jav_setup_complete").exists() or (data_dir / ".jav_setup_complete").exists()
        check("First-launch wizard", True, "complete" if setup_done else "not completed; run: python main.py --setup", severity="info")
        check(".env file", (ROOT / ".env").exists(), str(ROOT / ".env") if (ROOT / ".env").exists() else "missing; setup wizard can create it", severity="optional")
        check("Memory/data directory", data_dir.exists(), str(data_dir), severity="optional")
    except Exception as exc:
        check("setup state", False, repr(exc), severity="optional")

    print("\nVoice setup:")
    try:
        from scripts.voice_setup import collect_voice_checks
        for item in collect_voice_checks():
            sev = "external" if item.status in {"WARN", "INFO"} else "required"
            check(item.name, item.status in {"OK", "INFO"}, item.detail + (("; " + item.fix) if item.fix and item.status in {"WARN", "FAIL"} else ""), severity=sev)
    except Exception as exc:
        check("voice setup diagnostics", False, repr(exc), severity="optional")

    print("\nModel router:")
    try:
        from config import KernelConfig
        from core.llm_router import LLMRouter
        cfg = KernelConfig().llm
        router = LLMRouter(cfg)
        status = router.status(refresh=True)
        check("Model profile", True, str(status.get("profile")))
        roles = status.get("roles") or {}
        for role in ["fast", "reason", "code", "critic", "vision", "embedding", "action"]:
            info = roles.get(role) or {}
            detail = f"{info.get('provider', 'n/a')}/{info.get('model', '')}"
            if info.get("detail"):
                detail += f" — {info.get('detail')}"
            check(f"Model role {role}", bool(info.get("available")), detail, severity="external")
        check("At least one real model provider", any(p != "null" for p in (status.get("available") or [])), ", ".join(status.get("available") or []) or "none configured; chat will use NullProvider", severity="external")
    except Exception as exc:
        ok_all &= check("model router diagnostics", False, repr(exc))

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
        print("Core runtime looks usable. WARN items are optional/external and only affect their specific features.")
        return 0
    print("Some REQUIRED checks failed. WARN items are optional/external and do not block core startup.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
