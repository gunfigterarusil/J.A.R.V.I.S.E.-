"""JAV V9.5 watchdog.

Starts `python main.py --service`, watches the heartbeat JSON file, and restarts
JAV if the process exits or the heartbeat becomes stale.

Usage:
    python scripts/watchdog.py
    python scripts/watchdog.py --python python --max-restarts 20
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from config import KernelConfig, _env_bool  # noqa: E402


def resolve_heartbeat(cfg: KernelConfig) -> Path:
    data_dir = Path(cfg.persistence_dir).expanduser()
    return Path(cfg.runtime.resolve_heartbeat_file(str(data_dir))).expanduser()


def heartbeat_age(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = float(data.get("timestamp", 0))
        if ts <= 0:
            return None
        return time.time() - ts
    except Exception:
        return None


def terminate(proc: subprocess.Popen, timeout: float = 12.0) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def main() -> int:
    cfg = KernelConfig()
    parser = argparse.ArgumentParser(description="JAV watchdog")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    parser.add_argument("--max-restarts", type=int, default=cfg.runtime.max_restart_attempts)
    parser.add_argument("--restart-delay", type=float, default=cfg.runtime.restart_delay_seconds)
    parser.add_argument("--stale-seconds", type=float, default=cfg.runtime.heartbeat_stale_seconds)
    parser.add_argument("--check-interval", type=float, default=max(2.0, cfg.runtime.heartbeat_interval_seconds))
    args = parser.parse_args()

    heartbeat = resolve_heartbeat(cfg)
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    restarts = 0
    proc: subprocess.Popen | None = None

    print(f"[watchdog] Root: {ROOT}")
    print(f"[watchdog] Heartbeat: {heartbeat}")

    try:
        while True:
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    print(f"[watchdog] JAV exited with code {proc.returncode}")
                if restarts >= args.max_restarts:
                    print(f"[watchdog] Max restarts reached: {args.max_restarts}")
                    return 2
                restarts += 1
                print(f"[watchdog] Starting JAV service attempt {restarts}/{args.max_restarts}")
                env = dict(os.environ)
                env["JAV_SERVICE_MODE"] = "true"
                proc = subprocess.Popen([args.python, str(ROOT / "main.py"), "--service"], cwd=str(ROOT), env=env)
                time.sleep(args.restart_delay)

            age = heartbeat_age(heartbeat)
            if age is not None and age > args.stale_seconds:
                print(f"[watchdog] Stale heartbeat ({age:.1f}s > {args.stale_seconds:.1f}s). Restarting service.")
                terminate(proc)
                proc = None
                time.sleep(args.restart_delay)
                continue

            time.sleep(args.check_interval)
    except KeyboardInterrupt:
        print("[watchdog] Stopping")
        if proc is not None:
            terminate(proc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
