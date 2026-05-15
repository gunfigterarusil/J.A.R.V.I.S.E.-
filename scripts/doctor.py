"""JAV doctor — startup and environment diagnostics."""
from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path


def _status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


def check_import(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run_doctor(project_root: str | Path | None = None) -> int:
    root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
    print("JAV Doctor")
    print("==========")
    print(f"Project: {root}")
    print(f"Python:  {sys.version.split()[0]} ({platform.system()} {platform.release()})")

    problems: list[str] = []

    required_files = ["main.py", "config.py", "core/kernel.py", "modules"]
    print("\nCore files:")
    for item in required_files:
        ok = (root / item).exists()
        print(f"  [{_status(ok)}] {item}")
        if not ok:
            problems.append(f"Missing required file: {item}")

    print("\nRequired packages:")
    for pkg, import_name in [("fastapi", "fastapi"), ("uvicorn", "uvicorn")]:
        ok = check_import(import_name)
        print(f"  [{_status(ok)}] {pkg}")
        if not ok:
            problems.append(f"Missing package: {pkg}")

    print("\nOptional packages:")
    optional = [
        ("python-dotenv", "dotenv"),
        ("sounddevice", "sounddevice"),
        ("faster-whisper", "faster_whisper"),
        ("pyttsx3", "pyttsx3"),
        ("mss", "mss"),
        ("Pillow", "PIL"),
        ("pytesseract", "pytesseract"),
    ]
    for pkg, import_name in optional:
        ok = check_import(import_name)
        print(f"  [{_status(ok)}] {pkg}")

    print("\nConfiguration:")
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from config import KernelConfig
        cfg = KernelConfig()
        data_dir = Path(cfg.persistence_dir).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        writable = os.access(data_dir, os.W_OK)
        print(f"  [OK] data dir: {data_dir}")
        print(f"  [{_status(writable)}] data dir writable")
        if not writable:
            problems.append(f"Data directory is not writable: {data_dir}")
        print(f"  [OK] web: {cfg.web_host}:{cfg.web_port}")
        if getattr(cfg.llm, "gemini_api_key", ""):
            print("  [WARN] GEMINI_API_KEY is set in environment/.env. Keep it private.")
        else:
            print("  [OK] no hardcoded Gemini key detected")
    except Exception as exc:
        print(f"  [FAIL] config import/init: {exc}")
        problems.append(f"Config error: {exc}")

    print("\nKernel smoke test:")
    try:
        from config import KernelConfig
        from main import build_kernel
        kernel = build_kernel(KernelConfig())
        print(f"  [OK] kernel created with {len(kernel.modules)} module(s)")
        kernel.shutdown()
    except Exception as exc:
        print(f"  [FAIL] kernel startup: {exc}")
        problems.append(f"Kernel startup error: {exc}")

    print("\nResult:")
    if problems:
        print(f"  FAIL — {len(problems)} issue(s) found")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("  OK — core runtime looks usable")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_doctor())
