"""Optional system tray support for JAV.

Requires optional dependencies: pystray + Pillow. If they are absent, the tray
feature simply reports unavailable and the main Tkinter UI continues normally.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class TrayStatus:
    available: bool
    running: bool = False
    message: str = ""


class AssistantTray:
    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None], on_status: Callable[[], None]) -> None:
        self.on_show = on_show
        self.on_quit = on_quit
        self.on_status = on_status
        self.icon = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> TrayStatus:
        try:
            import pystray  # type: ignore
            from PIL import Image, ImageDraw  # type: ignore
        except Exception as exc:
            return TrayStatus(False, False, f"Tray dependencies missing: {exc}")

        def make_image():
            img = Image.new("RGB", (64, 64), "#0e1117")
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 56, 56), fill="#1f6feb")
            d.text((23, 20), "J", fill="white")
            return img

        def _show(_icon=None, _item=None):
            self.on_show()

        def _status(_icon=None, _item=None):
            self.on_status()

        def _quit(icon=None, _item=None):
            try:
                if icon:
                    icon.stop()
            finally:
                self.on_quit()

        self.icon = pystray.Icon(
            "JAV",
            make_image(),
            "JAV Assistant",
            menu=pystray.Menu(
                pystray.MenuItem("Show JAV", _show),
                pystray.MenuItem("Status", _status),
                pystray.MenuItem("Quit", _quit),
            ),
        )
        self.thread = threading.Thread(target=self.icon.run, daemon=True)
        self.thread.start()
        return TrayStatus(True, True, "Tray started")

    def stop(self) -> None:
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
