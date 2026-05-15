"""Optional desktop notifications for JAV Assistant Shell.

This helper never hard-fails: if a platform notification backend is missing,
it falls back to console-style no-op behavior so the desktop app can still run.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class NotificationResult:
    ok: bool
    backend: str
    message: str = ""


class DesktopNotifier:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def notify(self, title: str, message: str, timeout: int = 8) -> NotificationResult:
        if not self.enabled:
            return NotificationResult(False, "disabled", "Notifications disabled")
        title = (title or "JAV").strip()[:80]
        message = (message or "").strip()[:500]
        if not message:
            return NotificationResult(False, "none", "Empty message")

        # Preferred optional cross-platform library.
        try:
            from plyer import notification  # type: ignore
            notification.notify(title=title, message=message, timeout=timeout, app_name="JAV")
            return NotificationResult(True, "plyer")
        except Exception:
            pass

        # Linux desktop fallback.
        if sys.platform.startswith("linux"):
            try:
                subprocess.Popen(["notify-send", title, message])
                return NotificationResult(True, "notify-send")
            except Exception as exc:
                return NotificationResult(False, "notify-send", str(exc))

        # Windows/macOS fallback is intentionally no-op unless optional deps exist.
        return NotificationResult(False, "none", "No notification backend available")
