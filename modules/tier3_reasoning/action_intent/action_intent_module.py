"""V8 natural action intent layer.

This module converts plain language requests into safe V7 action_request events.
It intentionally supports a small set of transparent, auditable commands instead
of giving the LLM unrestricted computer control.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority


class ActionIntentModule(CognitiveModule):
    MODULE_DESCRIPTION = "V8 natural-language bridge to safe V7 actions"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="action_intent",
            cost={"cpu": 0.05, "gpu": 0.0, "ram": 0.03},
        )
        self.enabled = True

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(self.module_id, ["user_utterance"])

    async def on_event(self, event: Event) -> None:
        text = str(event.data.get("text", "") or "").strip()
        if not text or event.data.get("_skip_action_intent"):
            return
        parsed = self._parse(text)
        if not parsed:
            return

        action_type, payload, response = parsed
        # Mutating the routed event is intentional: if this module is loaded
        # before llm, the dialogue module will skip a duplicate generic answer.
        event.data["_skip_llm"] = True
        event.data["handled_by"] = self.module_id

        # For executable actions, let action_executor produce the user-facing result.
        # For guidance-only intents (for example broad repair requests), respond here.
        if action_type and self.kernel:
            self._emit_action(action_type, payload, event)
        elif response and self.kernel:
            self.kernel.event_bus.emit(
                Event(type="response_generated", data={"text": response, "source": "action_intent/v8"}, source_module=self.module_id),
                Priority.COGNITIVE,
            )

    def _emit_action(self, action_type: str, payload: Dict[str, Any], parent: Event) -> None:
        if not self.kernel:
            return
        payload = dict(payload)
        request_id = payload.get("request_id") or f"nl_action_{int(time.time() * 1000)}"
        payload["request_id"] = request_id
        top_path = payload.get("path") or payload.get("cwd")
        resolved_path = None
        if top_path:
            raw = Path(str(top_path)).expanduser()
            if not raw.is_absolute():
                workspace = Path(getattr(getattr(self.kernel.config, "actions", None), "workspace_path", "~/jarvis_workspace")).expanduser()
                resolved_path = str((workspace / raw).resolve())
            else:
                resolved_path = str(raw.resolve())
        self.kernel.event_bus.emit(
            Event(
                type="action_request",
                data={
                    "action_type": action_type,
                    "payload": payload,
                    "path": resolved_path,
                    "request_id": request_id,
                    "respond": True,
                    "natural_language_request": parent.data.get("text", ""),
                },
                source_module=self.module_id,
                causal_parent_id=parent._id,
            ),
            Priority.REALTIME,
        )

    def _parse(self, text: str) -> Optional[Tuple[str, Dict[str, Any], str]]:
        lower = text.lower().strip()

        # list files: "покажи файли .", "show files src", "список файлів"
        m = re.search(r"(?:покажи|покаж[иі]|список|list|show)\s+(?:файли|файлів|files)(?:\s+(?:в|у|in)?\s*(.+))?$", lower)
        if m:
            path = (m.group(1) or ".").strip().strip('"\'')
            return "list_files", {"path": path}, f"Показую файли в workspace: {path}"

        # read file: "прочитай файл README.md", "read file config.py"
        m = re.search(r"(?:прочитай|відкрий|покажи|read|open|show)\s+(?:файл\s+|file\s+)?(.+)$", lower)
        if m and any(w in lower for w in ["прочитай", "read file", "open file", "відкрий файл"]):
            path = m.group(1).strip().strip('"\'')
            return "read_file", {"path": path}, f"Читаю файл через sandbox: {path}"

        # search: "знайди error в .", "search error in src"
        m = re.search(r"(?:знайди|пошукай|search|find)\s+(.+?)(?:\s+(?:в|у|in)\s+(.+))?$", lower)
        if m:
            query = m.group(1).strip().strip('"\'')
            path = (m.group(2) or ".").strip().strip('"\'')
            # Avoid treating broad repair requests as plain search.
            if query not in {"помилки", "ошибки", "errors", "баги", "bugs"}:
                return "search_files", {"path": path, "query": query}, f"Шукаю `{query}` у workspace: {path}"

        # mkdir: "створи папку notes"
        m = re.search(r"(?:створи|создай|create|make)\s+(?:папку|директорію|folder|dir)\s+(.+)$", lower)
        if m:
            path = m.group(1).strip().strip('"\'')
            return "create_dir", {"path": path}, f"Створюю папку через sandbox: {path}"

        # write: "запиши в file.txt :: hello"
        m = re.search(r"(?:запиши|write)\s+(?:в|to)\s+(.+?)\s*::\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            path = m.group(1).strip().strip('"\'')
            content = m.group(2)
            return "write_file", {"path": path, "content": content}, f"Готую запис у файл через safety layer: {path}"

        # run safe command: "запусти python --version"
        m = re.search(r"(?:запусти|виконай|run|execute)\s+(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            command = m.group(1).strip()
            return "run_command", {"cwd": ".", "command": command}, "Готую запуск команди через safety layer. Для shell потрібні ACTION_ALLOW_SHELL=true і safety L5."

        # Repair/code-fix intent: respond with current capabilities and safe workflow.
        repair_words = ["виправ", "почини", "пофікси", "исправ", "fix", "repair"]
        error_words = ["помил", "ошиб", "error", "bug", "traceback", "exception"]
        if any(w in lower for w in repair_words) and any(w in lower for w in error_words):
            msg = (
                "Я розумію задачу як ремонт/фікс проєкту. У цій V8 MVP-версії я вже можу через розмову "
                "читати файли, шукати помилки, запускати allowlisted-команди й записувати патчі в sandbox після safety-перевірки. "
                "Повний autonomous code-fixer ще обмежений: спочатку дай шлях у workspace або скажи конкретніше, наприклад: "
                "`знайди ModuleNotFoundError в .`, `прочитай файл main.py`, `запусти pytest`, "
                "потім після аналізу я підготую правку через `запиши в file.py :: ...`."
            )
            return "", {}, msg

        return None

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["supported_natural_actions"] = [
            "list_files", "read_file", "search_files", "create_dir", "write_file", "run_command", "repair_intent_guidance"
        ]
        return base


def create_module() -> ActionIntentModule:
    return ActionIntentModule()
