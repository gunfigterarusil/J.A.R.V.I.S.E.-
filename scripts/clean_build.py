"""scripts/clean_build.py — Remove stale build artefacts before a release build.

Removes:
  dist/            — previous PyInstaller onedir output
  build/           — PyInstaller temp files
  **/__pycache__/  — bytecode cache directories
  **/*.pyc / *.pyo — loose bytecode files
  logs/*.log       — log files older than LOG_MAX_AGE_DAYS days
  installer_output/ — (only with --all flag)
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

LOG_MAX_AGE_DAYS = 7
_ROOT = Path(__file__).resolve().parent.parent


def _rmdir(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
        print(f"  removed  {p.relative_to(_ROOT)}/")


def _rm_glob(pattern: str) -> int:
    count = 0
    for f in _ROOT.rglob(pattern):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return count


def clean(root: Path = _ROOT, include_installer_output: bool = False) -> None:
    """Remove build artefacts under *root*."""
    print("Cleaning build artefacts...")

    # PyInstaller outputs
    _rmdir(root / "dist")
    _rmdir(root / "build")

    # Bytecode cache
    for cache_dir in root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
    pyc = _rm_glob("*.pyc")
    pyo = _rm_glob("*.pyo")
    if pyc + pyo:
        print(f"  removed  {pyc} *.pyc / {pyo} *.pyo files")

    # Stale logs
    logs_dir = root / "logs"
    if logs_dir.exists():
        cutoff = time.time() - LOG_MAX_AGE_DAYS * 86400
        removed = 0
        for log_file in logs_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink(missing_ok=True)
                removed += 1
        if removed:
            print(f"  removed  {removed} stale log(s) from logs/")

    # Optional: installer output
    if include_installer_output:
        _rmdir(root / "installer_output")

    print("Clean complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean JAV build artefacts")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also remove installer_output/",
    )
    args = parser.parse_args()
    clean(_ROOT, include_installer_output=args.all)
    return 0


if __name__ == "__main__":
    sys.exit(main())
