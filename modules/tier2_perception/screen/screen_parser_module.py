"""Tier 2 Perception: Screen + GUI Understanding Module (V9.6 MVP).

This module upgrades the old V3 screen reader into a safer "eyes" layer:

  screen_capture_requested / screen_read_requested / screen_understand_requested
    -> screenshot via mss
    -> OCR via pytesseract
    -> active-window probe when available
    -> GUI/text element extraction
    -> lightweight visual reasoning + recommended next actions
    -> screen_parsed + screen_understood

It does not click, type, or control the GUI. V9.6 is understanding-only. Any
future GUI automation must go through V7 safety and explicit approval gates.
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("screen")

ERROR_PATTERNS = [
    r"traceback", r"exception", r"error", r"failed", r"fatal", r"warning",
    r"denied", r"not found", r"no module named", r"permission", r"cannot",
    r"invalid", r"timeout", r"refused", r"crash", r"segmentation fault",
]
BUTTON_WORDS = {
    "ok", "yes", "no", "cancel", "close", "save", "apply", "send", "run", "start",
    "stop", "install", "update", "next", "back", "finish", "continue", "retry",
    "login", "sign in", "submit", "search", "browse", "open", "settings", "copy",
    "delete", "remove", "download", "upload", "accept", "deny", "approve",
    "так", "ні", "скасувати", "закрити", "зберегти", "застосувати", "надіслати",
    "запустити", "встановити", "оновити", "далі", "назад", "продовжити",
    "пошук", "відкрити", "налаштування", "копіювати", "видалити", "підтвердити",
}


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
        active_window: str = "",
        ui_elements: Optional[List[Dict[str, Any]]] = None,
        visual_summary: str = "",
        recommended_actions: Optional[List[str]] = None,
        error: str = "",
    ) -> None:
        self.request_id = request_id
        self.ok = ok
        self.screenshot_path = screenshot_path
        self.raw_text = raw_text
        self.summary = summary
        self.important_blocks = important_blocks or []
        self.likely_context = likely_context
        self.active_window = active_window
        self.ui_elements = ui_elements or []
        self.visual_summary = visual_summary
        self.recommended_actions = recommended_actions or []
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
            "active_window": self.active_window,
            "ui_elements": self.ui_elements or [],
            "visual_summary": self.visual_summary,
            "recommended_actions": self.recommended_actions or [],
            "error": self.error,
            "timestamp": time.time(),
        }


class ScreenParserModule(CognitiveModule):
    """V9.6 screen capture + OCR + GUI understanding."""

    MODULE_DESCRIPTION = "V9.6 screen/GUI understanding MVP — OCR, active window, UI blocks and safe recommendations"
    MODULE_VERSION = "9.6.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="screen_parser",
            cost={"cpu": 0.35, "gpu": 0.00, "ram": 0.18},
        )
        self.enabled_by_config = True
        self.auto_watch_enabled = False
        self.screenshot_dir = ""
        self.ocr_language = "eng"
        self.ocr_config = "--psm 6"
        self.save_screenshots = True
        self.max_ocr_chars = 7000
        self.vision_enabled = True
        self.gui_understanding_enabled = True
        self.active_window_enabled = True
        self.max_ui_elements = 40
        self.min_ui_confidence = 35
        self.last_result: Dict[str, Any] = {}
        # Phase 3B — ambient watch state
        self._ambient_interval: float = 8.0
        self._ambient_speech_gap: float = 3.0
        self._ambient_proactive: bool = True
        self._last_ambient_ts: float = 0.0
        self._last_user_speech_ts: float = 0.0
        self._ambient_pending: bool = False
        self._last_ctx: str = ""
        self._last_window: str = ""
        self._last_errors: List[str] = []
        self._ambient_baseline_ready: bool = False
        self._ambient_privacy_mode: bool = True
        self._ambient_store_screenshots: bool = False
        self._ambient_proactive_cooldown: float = 120.0
        self._ambient_same_error_cooldown: float = 300.0
        self._ambient_excluded_apps: List[str] = []
        self._ambient_pause_on_sensitive: bool = True
        self._last_proactive_ts: float = 0.0
        self._last_error_hash: str = ""
        self._last_error_ts: float = 0.0
        # Per-content dedup so the same app switch / context is not re-announced
        # after the global cooldown expires.
        self._last_switch_window: str = ""
        self._last_switch_ts: float = 0.0
        self._last_ctx_announced: str = ""
        self._last_ctx_announced_ts: float = 0.0
        _SWITCH_DEDUP_TTL: float = 180.0
        _CTX_DEDUP_TTL: float = 120.0

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
            self.vision_enabled = bool(getattr(screen_cfg, "vision_enabled", True))
            self.gui_understanding_enabled = bool(getattr(screen_cfg, "gui_understanding_enabled", True))
            self.active_window_enabled = bool(getattr(screen_cfg, "active_window_enabled", True))
            self.max_ui_elements = int(getattr(screen_cfg, "max_ui_elements", 40) or 40)
            self.min_ui_confidence = int(getattr(screen_cfg, "min_ui_confidence", 35) or 35)
            self._ambient_interval = float(getattr(screen_cfg, "ambient_watch_interval", 8.0))
            self._ambient_speech_gap = float(getattr(screen_cfg, "ambient_min_gap_after_speech", 3.0))
            self._ambient_proactive = bool(getattr(screen_cfg, "ambient_proactive", True))
            self._ambient_privacy_mode = bool(getattr(screen_cfg, "ambient_privacy_mode", True))
            self._ambient_store_screenshots = bool(getattr(screen_cfg, "ambient_store_screenshots", False))
            self._ambient_proactive_cooldown = float(getattr(screen_cfg, "ambient_proactive_cooldown", 120.0))
            self._ambient_same_error_cooldown = float(getattr(screen_cfg, "ambient_same_error_cooldown", 300.0))
            excluded = str(getattr(screen_cfg, "ambient_excluded_apps", "") or "")
            self._ambient_excluded_apps = [x.strip().lower() for x in excluded.split(",") if x.strip()]
            self._ambient_pause_on_sensitive = bool(getattr(screen_cfg, "ambient_pause_on_sensitive", True))

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "screen_capture_requested",
                "screen_read_requested",
                "screen_understand_requested",
                "gui_understanding_requested",
                "screen_focus",
                "user_utterance",
            ],
        )
        logger.info("[ScreenParser] V9.6 screen/GUI understanding module initialized")

    async def on_event(self, event: Event) -> None:
        if event.type in {"screen_capture_requested", "screen_read_requested", "screen_understand_requested", "gui_understanding_requested"}:
            result = self._read_screen(event)
            if event.data.get("reason") == "ambient_perception":
                self._ambient_pending = False
                self._check_ambient_change(result)
            self._emit_result(result, event)
        elif event.type == "screen_focus":
            logger.info("[ScreenParser] screen_focus received")
        elif event.type == "user_utterance":
            self._last_user_speech_ts = time.time()

    def update(self, dt: float) -> None:
        if not self.auto_watch_enabled or self._ambient_pending:
            return
        now = time.time()
        if now - self._last_user_speech_ts < self._ambient_speech_gap:
            return
        if now - self._last_ambient_ts < self._ambient_interval:
            return
        self._last_ambient_ts = now
        self._ambient_pending = True
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="screen_capture_requested",
                    data={"request_id": f"ambient_{int(now)}", "reason": "ambient_perception", "respond": False},
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )

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
        active_window = self._get_active_window_title() if self.active_window_enabled else ""
        try:
            screenshot_path = self._capture_screenshot(request_id)
        except Exception as exc:
            return ScreenReadResult(
                request_id=request_id,
                ok=False,
                active_window=active_window,
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
                active_window=active_window,
                error=(
                    "Screenshot captured, but OCR failed. Install Tesseract OCR and pytesseract. "
                    "Ubuntu: sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ukr. "
                    f"Details: {exc}"
                ),
                important_blocks=[],
            )

        raw_text = self._normalize_text(raw_text)[: self.max_ocr_chars]
        parsed = self._parse_text(raw_text)
        ui_elements: List[Dict[str, Any]] = []
        visual_summary = ""
        recommended_actions: List[str] = []

        if self.vision_enabled or self.gui_understanding_enabled:
            ui_elements = self._extract_ui_elements(screenshot_path)[: self.max_ui_elements]
            visual_summary = self._summarize_visual_scene(screenshot_path, active_window, ui_elements, parsed)
            recommended_actions = self._recommend_actions(parsed["likely_context"], parsed["important_blocks"], ui_elements, active_window)

        summary = parsed["summary"]
        if visual_summary:
            summary = f"{summary} {visual_summary}"
        if active_window:
            summary = f"Active window: {active_window}. {summary}"

        return ScreenReadResult(
            request_id=request_id,
            ok=True,
            screenshot_path=screenshot_path,
            raw_text=raw_text,
            summary=summary,
            important_blocks=parsed["important_blocks"],
            likely_context=parsed["likely_context"],
            active_window=active_window,
            ui_elements=ui_elements,
            visual_summary=visual_summary,
            recommended_actions=recommended_actions,
        )

    def _capture_screenshot(self, request_id: str) -> str:
        try:
            import mss  # type: ignore
            from PIL import Image  # noqa: F401
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

    def _extract_ui_elements(self, image_path: str) -> List[Dict[str, Any]]:
        """Extract approximate GUI/text elements from OCR boxes.

        This is not full computer vision yet, but it is much richer than raw OCR:
        every visible text line gets coordinates, a type guess and confidence.
        """
        if not self.gui_understanding_enabled:
            return []
        try:
            import pytesseract  # type: ignore
            from PIL import Image
        except Exception:
            return []

        tesseract_cmd = os.environ.get("TESSERACT_CMD", "").strip()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        elements: List[Dict[str, Any]] = []
        try:
            with Image.open(image_path) as img:
                data = pytesseract.image_to_data(
                    img,
                    lang=self.ocr_language,
                    config=self.ocr_config,
                    output_type=pytesseract.Output.DICT,
                )
                width, height = img.size
        except Exception as exc:
            logger.debug("[ScreenParser] OCR box extraction failed: %s", exc)
            return []

        grouped: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
        n = len(data.get("text", []))
        for i in range(n):
            text = str(data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data.get("conf", [0])[i])
            except Exception:
                conf = 0.0
            if conf >= 0 and conf < self.min_ui_confidence:
                continue
            key = (int(data.get("block_num", [0])[i]), int(data.get("par_num", [0])[i]), int(data.get("line_num", [0])[i]))
            left = int(data.get("left", [0])[i])
            top = int(data.get("top", [0])[i])
            w = int(data.get("width", [0])[i])
            h = int(data.get("height", [0])[i])
            item = grouped.setdefault(key, {"texts": [], "conf": [], "x1": left, "y1": top, "x2": left + w, "y2": top + h})
            item["texts"].append(text)
            item["conf"].append(conf)
            item["x1"] = min(item["x1"], left)
            item["y1"] = min(item["y1"], top)
            item["x2"] = max(item["x2"], left + w)
            item["y2"] = max(item["y2"], top + h)

        for item in grouped.values():
            text = " ".join(item.pop("texts", [])).strip()
            if not text:
                continue
            x1, y1, x2, y2 = item["x1"], item["y1"], item["x2"], item["y2"]
            bbox = [x1, y1, x2 - x1, y2 - y1]
            conf_values = [c for c in item.pop("conf", []) if c >= 0]
            conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
            etype = self._classify_ui_text(text, bbox, width, height)
            elements.append({
                "type": etype,
                "text": text[:240],
                "bbox": bbox,
                "confidence": round(conf, 1),
                "center": [round(x1 + (x2 - x1) / 2), round(y1 + (y2 - y1) / 2)],
            })

        def priority(el: Dict[str, Any]) -> Tuple[int, int]:
            order = {"error_text": 0, "button_or_action": 1, "input_or_label": 2, "menu_or_tab": 3, "text_block": 4}
            return (order.get(str(el.get("type")), 9), int(el.get("bbox", [0, 0, 0, 0])[1]))

        elements.sort(key=priority)
        return elements

    def _classify_ui_text(self, text: str, bbox: List[int], width: int, height: int) -> str:
        t = text.strip().lower()
        words = len(t.split())
        x, y, w, h = bbox
        if re.search("|".join(ERROR_PATTERNS), t, re.IGNORECASE):
            return "error_text"
        if t in BUTTON_WORDS or (words <= 3 and 14 <= h <= 70 and w <= width * 0.35):
            return "button_or_action"
        if y < height * 0.12 and words <= 6:
            return "menu_or_tab"
        if any(sym in t for sym in [":", "=", "_"]) and words <= 6:
            return "input_or_label"
        return "text_block"

    def _get_active_window_title(self) -> str:
        try:
            import pygetwindow as gw  # type: ignore
            win = gw.getActiveWindow()
            if win and getattr(win, "title", ""):
                return str(win.title).strip()[:180]
        except Exception:
            pass
        return ""

    def _summarize_visual_scene(self, image_path: str, active_window: str, elements: List[Dict[str, Any]], parsed: Dict[str, Any]) -> str:
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                w, h = img.size
        except Exception:
            w = h = 0
        counts: Dict[str, int] = {}
        for el in elements:
            counts[str(el.get("type", "unknown"))] = counts.get(str(el.get("type", "unknown")), 0) + 1
        if not elements:
            base = "GUI understanding did not find structured UI elements yet."
        else:
            parts = [f"{v} {k.replace('_', ' ')}" for k, v in sorted(counts.items())]
            base = "GUI understanding found " + ", ".join(parts[:5]) + "."
        if w and h:
            base += f" Screenshot size: {w}x{h}."
        return base

    def _recommend_actions(self, likely_context: str, important: List[str], elements: List[Dict[str, Any]], active_window: str) -> List[str]:
        actions: List[str] = []
        joined = "\n".join(important).lower()
        if "no module named" in joined:
            actions.append("Install the missing Python package in the project environment, then rerun the command.")
        if "traceback" in joined or "exception" in joined or "programming error" in likely_context:
            actions.append("Use the project repair agent: say 'виправ помилки в <папка>' or run /repair <path>.")
        if "permission" in joined or "denied" in joined:
            actions.append("Check permissions/path access before retrying; do not raise privileges unless you understand the change.")
        if "terminal" in likely_context or "command-line" in likely_context:
            actions.append("Copy the exact error text into chat or let Jarvis read the screen again after rerunning the command.")
        if any(el.get("type") == "button_or_action" for el in elements):
            labels = [str(el.get("text")) for el in elements if el.get("type") == "button_or_action"][:6]
            actions.append("Visible action-like UI labels: " + ", ".join(labels) + ". I can advise, but I will not click automatically in V9.6.")
        if not actions:
            actions.append("Ask a focused question like 'що тут не так?', 'що натиснути?', or 'поясни цей екран'.")
        return actions[:6]

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
        rx = re.compile("|".join(ERROR_PATTERNS), re.IGNORECASE)
        hits: List[str] = []
        for line in lines:
            if rx.search(line):
                cleaned = line[:500]
                if cleaned not in hits:
                    hits.append(cleaned)
        if not hits and lines:
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
        if any(x in t for x in ["settings", "налаштування", "preferences", "configuration"]):
            return "a settings/configuration screen"
        if len(text) > 2000:
            return "a text-heavy page or document"
        return "a normal desktop/app screen"

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _is_sensitive_screen(self, result: ScreenReadResult) -> bool:
        text = " ".join([
            str(result.active_window or ""),
            str(result.summary or ""),
            " ".join(result.important_blocks or []),
        ]).lower()
        sensitive_terms = [
            "password", "passwd", "пароль", "логін", "login", "token", "api key", "apikey",
            "secret", "bank", "банкінг", "payment", "card number", "cvv", "credit card",
            "private key", "seed phrase", "recovery phrase",
        ]
        return any(term in text for term in sensitive_terms)

    def _check_ambient_change(self, result: ScreenReadResult) -> None:
        now = time.time()
        window_l = (result.active_window or "").lower()
        if any(app in window_l for app in self._ambient_excluded_apps):
            logger.debug("[ScreenParser] Ambient skipped excluded window: %s", result.active_window)
            return
        if self._ambient_privacy_mode and self._ambient_pause_on_sensitive and self._is_sensitive_screen(result):
            logger.info("[ScreenParser] Ambient skipped sensitive screen")
            # Update baseline enough to avoid repeated alerts when leaving sensitive screen.
            self._last_window = result.active_window
            self._last_ctx = result.likely_context
            self._last_errors = list(result.important_blocks)
            self._ambient_baseline_ready = True
            return

        changed_reasons: List[str] = []
        if result.active_window != self._last_window:
            changed_reasons.append("app_switched")
        if result.likely_context != self._last_ctx:
            changed_reasons.append("context_changed")
        new_errors = [e for e in result.important_blocks if e not in self._last_errors]
        if new_errors:
            changed_reasons.append("error_detected")

        self._last_window = result.active_window
        self._last_ctx = result.likely_context
        self._last_errors = list(result.important_blocks)

        # First ambient capture establishes a baseline only. Otherwise JAV would
        # always announce an app/context change immediately after enabling watch.
        if not self._ambient_baseline_ready:
            self._ambient_baseline_ready = True
            logger.debug("[ScreenParser] Ambient baseline captured")
            return

        if not changed_reasons or not self._ambient_proactive or not self.kernel:
            return

        if now - self._last_proactive_ts < self._ambient_proactive_cooldown:
            return

        error_hash = "|".join(new_errors[:3])
        if new_errors and error_hash == self._last_error_hash and now - self._last_error_ts < self._ambient_same_error_cooldown:
            return
        if new_errors:
            self._last_error_hash = error_hash
            self._last_error_ts = now

        # Dedup app_switched — suppress if same window was already announced recently.
        if "app_switched" in changed_reasons:
            win = result.active_window or ""
            if win == self._last_switch_window and now - self._last_switch_ts < 180.0:
                changed_reasons = [r for r in changed_reasons if r != "app_switched"]
            else:
                self._last_switch_window = win
                self._last_switch_ts = now

        # Dedup context_changed — suppress if same context string was announced recently.
        if "context_changed" in changed_reasons:
            ctx = result.likely_context or ""
            if ctx == self._last_ctx_announced and now - self._last_ctx_announced_ts < 120.0:
                changed_reasons = [r for r in changed_reasons if r != "context_changed"]
            else:
                self._last_ctx_announced = ctx
                self._last_ctx_announced_ts = now

        if not changed_reasons:
            return

        importance = 0.7 if "error_detected" in changed_reasons else 0.4
        suggestion = result.recommended_actions[0] if result.recommended_actions else ""
        self._last_proactive_ts = now
        self.kernel.event_bus.emit(
            Event(
                type="proactive_event",
                data={
                    "reason": changed_reasons[0],
                    "summary": result.summary[:300],
                    "active_window": result.active_window,
                    "errors": new_errors[:3],
                    "suggestion": suggestion,
                    "importance": importance,
                    "source": "ambient_perception",
                    "privacy_mode": self._ambient_privacy_mode,
                },
                source_module=self.module_id,
            ),
            Priority.BACKGROUND,
        )
        logger.debug("[ScreenParser] Ambient change: %s importance=%.1f", changed_reasons, importance)

    def _emit_result(self, result: ScreenReadResult, parent: Event) -> None:
        if not self.kernel:
            return
        data = result.to_event_data()
        if parent.data.get("gui_task_id"):
            data["gui_task_id"] = parent.data.get("gui_task_id")
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
                Event(type="screen_understood", data=data, source_module=self.module_id, causal_parent_id=parent._id),
                Priority.COGNITIVE,
            )
            self.kernel.event_bus.emit(
                Event(
                    type="sensory_input",
                    data={
                        "kind": "screen",
                        "summary": result.summary,
                        "raw_text": result.raw_text[:1200],
                        "ui_elements": result.ui_elements[:12],
                        "recommended_actions": result.recommended_actions,
                        "request_id": result.request_id,
                    },
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
                            "source": "screen_parser/v9.6",
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
                        data={"text": f"I could not read/understand the screen yet: {result.error}", "source": "screen_parser/v9.6", "request_id": result.request_id},
                        source_module=self.module_id,
                        causal_parent_id=parent._id,
                    ),
                    Priority.COGNITIVE,
                )

    def _format_user_response(self, result: ScreenReadResult) -> str:
        blocks = result.important_blocks or []
        elements = result.ui_elements or []
        element_lines = []
        for el in elements[:8]:
            label = str(el.get("text", ""))[:80]
            etype = str(el.get("type", "ui"))
            bbox = el.get("bbox", [])
            element_lines.append(f"- {etype}: {label} @ {bbox}")
        action_lines = [f"- {a}" for a in (result.recommended_actions or [])[:6]]

        parts = [f"I analyzed the screen. Context: {result.likely_context}."]
        if result.active_window:
            parts.append(f"Active window: {result.active_window}.")
        if blocks:
            parts.append("\nImportant visible text:\n" + "\n".join(f"- {block}" for block in blocks[:6]))
        if element_lines:
            parts.append("\nDetected UI/text elements:\n" + "\n".join(element_lines))
        if action_lines:
            parts.append("\nSuggested next steps:\n" + "\n".join(action_lines))
        parts.append(f"\nScreenshot saved: {result.screenshot_path}")
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "v9_6_gui_understanding": True,
            "enabled_by_config": self.enabled_by_config,
            "vision_enabled": self.vision_enabled,
            "gui_understanding_enabled": self.gui_understanding_enabled,
            "active_window_enabled": self.active_window_enabled,
            "ocr_language": self.ocr_language,
            "last_result_ok": self.last_result.get("ok"),
            "last_summary": self.last_result.get("summary", "")[:180],
            "last_ui_elements": len(self.last_result.get("ui_elements", []) or []),
            "last_active_window": self.last_result.get("active_window", ""),
        })
        return base


def create_module() -> ScreenParserModule:
    return ScreenParserModule()
