"""scripts/build_smoke_test.py — Verify the PyInstaller dist bundle is functional.

Checks:
  1. JAV.exe and JAV-Console.exe exist in dist_dir
  2. data/ directory exists (or is created on first run — just check exe presence)
  3. .env file is present and contains JAV_PORTABLE=true
  4. run_desktop.bat is present
  5. JAV-Console.exe --doctor exits with code 0 (optional, skipped if timeout)

Usage:
  python scripts/build_smoke_test.py [dist_dir]
  dist_dir defaults to dist/JAV relative to the repo root.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DIST = _ROOT / "dist" / "JAV"

REQUIRED_FILES = [
    "JAV.exe",
    "JAV-Console.exe",
    "run_desktop.bat",
    ".env",
]


@dataclass
class SmokeResult:
    name: str
    passed: bool
    detail: str = ""


def _check_structure(dist_dir: Path) -> list[SmokeResult]:
    results: list[SmokeResult] = []
    for fname in REQUIRED_FILES:
        p = dist_dir / fname
        results.append(SmokeResult(
            name=f"File: {fname}",
            passed=p.exists(),
            detail="" if p.exists() else f"Missing: {p}",
        ))

    # .env must contain JAV_PORTABLE=true
    env_file = dist_dir / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8", errors="replace")
        has_portable = "JAV_PORTABLE=true" in content
        results.append(SmokeResult(
            name=".env contains JAV_PORTABLE=true",
            passed=has_portable,
            detail="" if has_portable else ".env exists but JAV_PORTABLE=true not found",
        ))
    return results


def _check_doctor(dist_dir: Path, timeout: int = 60) -> SmokeResult:
    console_exe = dist_dir / "JAV-Console.exe"
    if not console_exe.exists():
        return SmokeResult(
            name="Doctor check (--doctor)",
            passed=False,
            detail="JAV-Console.exe not found — cannot run doctor",
        )
    try:
        result = subprocess.run(
            [str(console_exe), "--doctor"],
            cwd=str(dist_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        passed = result.returncode == 0
        detail = "" if passed else f"exit code {result.returncode}\n{result.stdout[-500:]}"
        return SmokeResult(name="Doctor check (--doctor)", passed=passed, detail=detail)
    except subprocess.TimeoutExpired:
        return SmokeResult(
            name="Doctor check (--doctor)",
            passed=False,
            detail=f"Timed out after {timeout}s",
        )
    except Exception as exc:
        return SmokeResult(
            name="Doctor check (--doctor)",
            passed=False,
            detail=str(exc),
        )


def smoke_test_build(dist_dir: Path, run_doctor: bool = True) -> bool:
    """Run all smoke checks. Returns True if all pass."""
    print(f"Smoke testing: {dist_dir}")
    print("-" * 50)

    results = _check_structure(dist_dir)
    if run_doctor:
        results.append(_check_doctor(dist_dir))

    all_pass = True
    for r in results:
        icon = "OK" if r.passed else "FAIL"
        print(f"  [{icon}] {r.name}")
        if r.detail:
            for line in r.detail.splitlines():
                print(f"        {line}")
        if not r.passed:
            all_pass = False

    print("-" * 50)
    if all_pass:
        print("Smoke test PASSED.")
    else:
        print("Smoke test FAILED.")
    return all_pass


def main() -> int:
    parser = argparse.ArgumentParser(description="JAV build smoke test")
    parser.add_argument(
        "dist_dir",
        nargs="?",
        default=str(_DEFAULT_DIST),
        help=f"Path to dist directory (default: {_DEFAULT_DIST})",
    )
    parser.add_argument(
        "--no-doctor",
        action="store_true",
        help="Skip running --doctor (faster, structure-only check)",
    )
    args = parser.parse_args()

    dist_dir = Path(args.dist_dir)
    if not dist_dir.exists():
        print(f"ERROR: dist_dir not found: {dist_dir}", file=sys.stderr)
        return 2

    passed = smoke_test_build(dist_dir, run_doctor=not args.no_doctor)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
