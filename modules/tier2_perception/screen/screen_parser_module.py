"""Tier 2 Perception: Screen Reading Module (V3 MVP).

Provides the first real "eyes" for Jarvis:
  screen_capture_requested
    -> screenshot via mss
    -> OCR via pytesseract
    -> lightweight ScreenParser summary
    -> screen_parsed (+ optional response_generated)

All dependencies are optional at import time. If the OS/OCR stack is missing,
the module emits screen_error instead of crashing the kernel.
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("screen")


class ScreenReadResult:
    def __init__(
        self,
        request_id: str,
        ok: bool,
        screenshot_path: str = "",
        raw_text: str = "",
        summary: str = "",
        important_blocks: Optional[List[str]] = None,
        likely_context: str = "unknown",
        error: str = "",
    ) -> None:
        self.request_id = request_id
        self.ok = ok
        self.screenshot_path = screenshot_path
        self.raw_text = raw_text
        self.summary = summary
        self.important_blocks = important_blocks or []
        self.likely_context = likely_context
        self.error = error

    def to_event_data(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "ok": self.ok,
            "screenshot_path": self.screenshot_path,
            "raw_text": self.raw_text,
            "summary": self.summary,
            "important_blocks": self.important_blocks or [],
            "likely_context": self.likely_context,
            "error": self.error,
            "timestamp": time.time(),
        }



class ScreenParserModule(CognitiveModule):
    """V3 MVP screen capture + OCR + simple parser."""

    MODULE_DESCRIPTION = "V3 screen reading MVP — screenshot capture, OCR and lightweight screen parsing"
    MODULE_VERSION = "3.0.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="screen_parser",
            cost={"cpu": 0.25, "gpu": 0.00, "ram": 0.15},
        )
        self.enabled_by_config = True
        self.auto_watch_enabled = False
        self.screenshot_dir = ""
        self.ocr_language = "eng"
        self.ocr_config = "--psm 6"
        self.save_screenshots = True
        self.max_ocr_chars = 7000
        self.last_result: Dict[str, Any] = {}

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel, "config", None)
        screen_cfg = getattr(cfg, "screen", None)
        if screen_cfg is not None:
            self.enabled_by_config = bool(getattr(screen_cfg, "enabled", True))
            self.auto_watch_enabled = bool(getattr(screen_cfg, "auto_watch_enabled", False))
            self.screenshot_dir = str(getattr(screen_cfg, "screenshot_dir", "") or "")
            self.ocr_language = str(getattr(screen_cfg, "ocr_language", "eng") or "eng")
            self.ocr_config = str(getattr(screen_cfg, "ocr_config", "--psm 6") or "--psm 6")
            self.save_screenshots = bool(getattr(screen_cfg, "save_screenshots", True))
            self.max_ocr_chars = int(getattr(screen_cfg, "max_ocr_chars", 7000) or 7000)

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "screen_capture_requested",
                "screen_read_requested",
                "screen_focus",
            ],
        )
        logger.info("[ScreenParser] V3 screen reading module initialized")

    async def on_event(self, event: Event) -> None:
        if event.type in {"screen_capture_requested", "screen_read_requested"}:
            result = self._read_screen(event)
            self._emit_result(result, event)
        elif event.type == "screen_focus":
            logger.info("[ScreenParser] screen_focus received")

    def update(self, dt: float) -> None:
        # V3 MVP is request-driven. Continuous watching is intentionally off
        # until V7 automation, to avoid privacy/performance surprises.
        return

    def _read_screen(self, event: Event) -> ScreenReadResult:
        request_id = str(event.data.get("request_id") or f"screen_{int(time.time())}")
        if not self.enabled_by_config:
            return ScreenReadResult(
                request_id=request_id,
                ok=False,
                error="Screen reading is disabled by SCREEN_READING_ENABLED=false.",
                important_blocks=[],
            )

        screenshot_path = ""
        try:
            screenshot_path = self._capture_screenshot(request_id)
        except Exception as exc:
            return ScreenReadResult(
                request_id=request_id,
                ok=False,
                error=(
                    "Could not capture the screen. Install dependencies and ensure a graphical session is available. "
                    f"Details: {exc}"
                ),
                important_blocks=[],
            )

        try:
            raw_text = self._ocr_image(screenshot_path)
        except Exception as exc:
            return ScreenReadResult(
                request_id=request_id,
                ok=False,
                screenshot_path=screenshot_path,
                error=(
                    "Screenshot captured, but OCR failed. Install Tesseract OCR and pytesseract. "
                    "Ubuntu: sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ukr. "
                    f"Details: {exc}"
                ),
                important_blocks=[],
            )

        raw_text = self._normalize_text(raw_text)[: self.max_ocr_chars]
        parsed = self._parse_text(raw_text)
        return ScreenReadResult(
            request_id=request_id,
            ok=True,
            screenshot_path=screenshot_path,
            raw_text=raw_text,
            summary=parsed["summary"],
            important_blocks=parsed["important_blocks"],
            likely_context=parsed["likely_context"],
        )

    def _capture_screenshot(self, request_id: str) -> str:
        try:
            import mss  # type: ignore
            from PIL import Image  # noqa: F401  # imported to verify Pillow is installed
        except ImportError as exc:
            raise RuntimeError("Missing Python packages: pip install mss Pillow") from exc

        if self.screenshot_dir:
            out_dir = Path(self.screenshot_dir).expanduser()
        elif self._kernel is not None:
            out_dir = Path(self._kernel.persistence._base) / "screenshots"
        else:
            out_dir = Path.home() / ".jarvis_brain" / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{request_id}.png"

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            from PIL import Image

            img = Image.frombytes("RGB", shot.size, shot.rgb)
            img.save(path)
        return str(path)

    def _ocr_image(self, image_path: str) -> str:
        try:
            import pytesseract  # type: ignore
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Missing Python packages: pip install pytesseract Pillow") from exc

        tesseract_cmd = os.environ.get("TESSERACT_CMD", "").strip()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        with Image.open(image_path) as img:
            return pytesseract.image_to_string(
                img,
                lang=self.ocr_language,
                config=self.ocr_config,
            )

    def _parse_text(self, raw_text: str) -> Dict[str, Any]:
        text = raw_text.strip()
        if not text:
            return {
                "likely_context": "empty_or_unreadable_screen",
                "summary": "I captured the screen, but OCR did not find readable text.",
                "important_blocks": [],
            }

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        important = self._extract_important_blocks(lines)
        likely_context = self._detect_context(text, important)

        if important:
            summary = f"I can read the screen. It looks like {likely_context}. Most important: " + " | ".join(important[:3])
        else:
            preview = " ".join(lines[:5])[:500]
            summary = f"I can read the screen. It looks like {likely_context}. Visible text starts with: {preview}"

        return {
            "likely_context": likely_context,
            "summary": summary,
            "important_blocks": important[:12],
        }

    def _extract_important_blocks(self, lines: List[str]) -> List[str]:
        patterns = [
            r"traceback",
            r"exception",
            r"error",
            r"failed",
            r"fatal",
            r"warning",
            r"denied",
            r"not found",
            r"no module named",
            r"permission",
            r"cannot",
            r"invalid",
            r"timeout",
            r"refused",
            r"crash",
        ]
        rx = re.compile("|".join(patterns), re.IGNORECASE)
        hits: List[str] = []
        for line in lines:
            if rx.search(line):
                cleaned = line[:500]
                if cleaned not in hits:
                    hits.append(cleaned)
        if not hits and lines:
            # Fallback to first meaningful text blocks.
            hits = lines[:5]
        return hits

    def _detect_context(self, text: str, important: List[str]) -> str:
        t = text.lower()
        if "traceback" in t or "exception" in t or "no module named" in t:
            return "a programming error or terminal traceback"
        if "error" in t or "failed" in t or "warning" in t:
            return "a screen containing warnings or errors"
        if "http" in t or "localhost" in t or "github" in t:
            return "a browser or web/developer page"
        if "def " in text or "class " in text or "import " in text:
            return "a code editor or source file"
        if "$ " in text or "> " in text or "sudo " in t or "pip " in t:
            return "a terminal or command-line window"
        if len(text) > 2000:
            return "a text-heavy page or document"
        return "a normal desktop/app screen"

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _emit_result(self, result: ScreenReadResult, parent: Event) -> None:
        if not self.kernel:
            return
        data = result.to_event_data()
        self.last_result = data

        if result.ok:
            self.kernel.event_bus.emit(
                Event(type="screen_captured", data={"request_id": result.request_id, "path": result.screenshot_path}, source_module=self.module_id, causal_parent_id=parent._id),
                Priority.COGNITIVE,
            )
            self.kernel.event_bus.emit(
                Event(type="ocr_completed", data={"request_id": result.request_id, "chars": len(result.raw_text), "raw_text": result.raw_text}, source_module=self.module_id, causal_parent_id=parent._id),
                Priority.COGNITIVE,
            )
            self.kernel.event_bus.emit(
                Event(type="screen_parsed", data=data, source_module=self.module_id, causal_parent_id=parent._id),
                Priority.COGNITIVE,
            )
            self.kernel.event_bus.emit(
                Event(
                    type="sensory_input",
                    data={"kind": "screen", "summary": result.summary, "raw_text": result.raw_text[:1200], "request_id": result.request_id},
                    source_module=self.module_id,
                    causal_parent_id=parent._id,
                ),
                Priority.COGNITIVE,
            )
            if parent.data.get("respond", True):
                self.kernel.event_bus.emit(
                    Event(
                        type="response_generated",
                        data={
                            "text": self._format_user_response(result),
                            "source": "screen_parser/v3",
                            "request_id": result.request_id,
                        },
                        source_module=self.module_id,
                        causal_parent_id=parent._id,
                    ),
                    Priority.COGNITIVE,
                )
        else:
            self.kernel.event_bus.emit(
                Event(type="screen_error", data=data, source_module=self.module_id, causal_parent_id=parent._id),
                Priority.COGNITIVE,
            )
            if parent.data.get("respond", True):
                self.kernel.event_bus.emit(
                    Event(
                        type="response_generated",
                        data={"text": f"I could not read the screen yet: {result.error}", "source": "screen_parser/v3", "request_id": result.request_id},
                        source_module=self.module_id,
                        causal_parent_id=parent._id,
                    ),
                    Priority.COGNITIVE,
                )

    def _format_user_response(self, result: ScreenReadResult) -> str:
        blocks = result.important_blocks or []
        if not blocks:
            return result.summary
        bullet_lines = "\n".join(f"- {block}" for block in blocks[:6])
        return (
            f"I read the screen. Context: {result.likely_context}.\n\n"
            f"Important visible text:\n{bullet_lines}\n\n"
            f"Screenshot saved: {result.screenshot_path}"
        )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "v3_screen_reading": True,
            "enabled_by_config": self.enabled_by_config,
            "ocr_language": self.ocr_language,
            "last_result_ok": self.last_result.get("ok"),
            "last_summary": self.last_result.get("summary", "")[:180],
        })
        return base


def create_module() -> ScreenParserModule:
    return ScreenParserModule()
