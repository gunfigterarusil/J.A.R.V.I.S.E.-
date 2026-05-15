"""Create a user-level systemd service file for JAV watchdog.

This script writes (but does not enable) a service file into:
  ~/.config/systemd/user/jav-watchdog.service

Then run:
  systemctl --user daemon-reload
  systemctl --user enable --now jav-watchdog.service
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_FILE = SERVICE_DIR / "jav-watchdog.service"


def main() -> int:
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    content = f"""[Unit]
Description=JAV Jarvis Brain Core Watchdog
After=network-online.target

[Service]
Type=simple
WorkingDirectory={ROOT}
ExecStart={python} {ROOT / 'scripts' / 'watchdog.py'}
Restart=always
RestartSec=8
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    SERVICE_FILE.write_text(content, encoding="utf-8")
    print(f"Wrote: {SERVICE_FILE}")
    print("Next commands:")
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now jav-watchdog.service")
    print("  systemctl --user status jav-watchdog.service")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
