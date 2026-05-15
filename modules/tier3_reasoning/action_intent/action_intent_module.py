"""V8.1 Natural Action Router.

Converts ordinary text/voice requests into the same audited events used by
slash commands and buttons. The router is deliberately transparent: it maps
known intents to known events/actions and never gives the LLM unrestricted PC
control. Every external effect still passes through V7 safety.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority
from core.safety.permission_manager import PermissionLevel


class ActionIntentModule(CognitiveModule):
    MODULE_DESCRIPTION = "V9 natural-language/voice bridge to safe Jarvis actions and cognitive repair"
    MODULE_VERSION = "0.3.0"

    def __init__(self) -> None:
        super().__init__(module_id="action_intent", cost={"cpu": 0.05, "gpu": 0.0, "ram": 0.03})
        self.enabled = True
        self.require_explicit_verb = True
        self.repair_agent_enabled = True

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "natural_actions", None)
        self.enabled = bool(getattr(cfg, "enabled", True))
        self.require_explicit_verb = bool(getattr(cfg, "require_explicit_verb", True))
        self.repair_agent_enabled = bool(getattr(cfg, "repair_agent_enabled", True))
        kernel.event_bus.register_consumer(self.module_id, ["user_utterance"])

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        text = str(event.data.get("text", "") or "").strip()
        if not text or event.data.get("_skip_action_intent"):
            return
        parsed = self._parse(text)
        if not parsed:
            return

        kind, name, payload, response = parsed
        event.data["_skip_llm"] = True
        event.data["handled_by"] = self.module_id

        if kind == "action":
            self._emit_action(name, payload, event)
        elif kind == "event":
            if name == "self_model_request":
                self._respond(self._self_status())
            elif name == "world_model_request":
                self._respond(self._world_status())
            else:
                self._emit_event(name, payload, event)
        elif kind == "safety":
            self._set_safety(int(payload.get("level", 1)))
        elif kind == "repair":
            self._emit_event("code_repair_requested", payload, event)
        elif kind == "repair_apply":
            self._emit_event("code_repair_apply_requested", payload, event)
        elif kind == "task":
            self._emit_event("task_chain_requested", payload, event)
        elif kind == "task_step":
            self._emit_event("task_chain_step_requested", payload, event)
        elif kind == "task_status":
            self._emit_event("task_chain_status_requested", payload, event)
        elif kind == "task_cancel":
            self._emit_event("task_chain_cancel_requested", payload, event)
        elif kind == "task_resume":
            self._emit_event("task_chain_resume_requested", payload, event)
        elif kind == "response" and response:
            self._respond(response)

    # ------------------------------------------------------------------
    # Emitters
    # ------------------------------------------------------------------
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

    def _emit_event(self, event_type: str, payload: Dict[str, Any], parent: Event) -> None:
        if not self.kernel:
            return
        data = dict(payload)
        data.setdefault("respond", True)
        data.setdefault("reason", "natural_language_request")
        data.setdefault("request_text", parent.data.get("text", ""))
        self.kernel.event_bus.emit(
            Event(type=event_type, data=data, source_module=self.module_id, causal_parent_id=parent._id),
            Priority.REALTIME if event_type in {"screen_capture_requested", "v7_user_approval", "v7_user_deny"} else Priority.COGNITIVE,
        )

    def _respond(self, text: str) -> None:
        if not self.kernel:
            return
        self.kernel.event_bus.emit(
            Event(type="response_generated", data={"text": text, "source": "action_intent/v8.1"}, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    def _self_status(self) -> str:
        mod = self.kernel.modules.get("self_model") if self.kernel else None
        if mod is None:
            return "Self-model module is not loaded."
        snap = mod.to_dict()
        caps = ", ".join(list((snap.get("capabilities") or {}).keys())[:14])
        return (
            f"Self-model: {snap.get('identity_name', 'JAV')} / {snap.get('role', 'assistant')}\n"
            f"confidence={snap.get('confidence')} reliability={snap.get('reliability')} maturity={snap.get('cognitive_maturity')}\n"
            f"interfaces: {', '.join(map(str, snap.get('active_interfaces', [])))}\n"
            f"capabilities: {caps}"
        )

    def _world_status(self) -> str:
        mod = self.kernel.modules.get("world_model") if self.kernel else None
        if mod is None:
            return "World-model module is not loaded."
        snap = mod.to_dict()
        return (
            "World-model:\n"
            f"active projects: {', '.join(map(str, snap.get('active_projects', [])))}\n"
            f"open loops: {snap.get('open_loop_count')} patterns: {snap.get('pattern_count')}\n"
            f"top intents: {snap.get('top_intents')}\n"
            f"environment: {snap.get('environment')}"
        )


    def _model_router_status(self) -> str:
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router is None or not hasattr(router, "status"):
            return "Model router is not available."
        status = router.status(refresh=True)
        lines = [f"Model router V10 profile: {status.get('profile')}"]
        roles = status.get("roles") or {}
        for role in ["fast", "reason", "code", "critic", "vision", "embedding", "action"]:
            info = roles.get(role) or {}
            lines.append(f"- {role}: {info.get('provider', 'not configured')} available={info.get('available', False)}")
        available = ", ".join(status.get("available") or [])
        lines.append(f"available providers: {available}")
        return "\n".join(lines)

    def _set_safety(self, level: int) -> None:
        if not self.kernel:
            return
        try:
            level = max(0, min(6, int(level)))
            self.kernel.permission_manager.set_level(PermissionLevel(level))
            self.kernel.core_state.safety_level = level
            self._respond(f"Safety level set to L{level}.")
        except Exception as exc:
            self._respond(f"Could not set safety level: {exc}")

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------
    def _parse(self, text: str) -> Optional[Tuple[str, str, Dict[str, Any], str]]:
        raw = text.strip()
        lower = raw.lower().strip()

        # Approvals/denials: "approve p12", "схвали p12", "відхили p12"
        m = re.search(r"(?:approve|allow|схвали|дозволь|підтверди|разреши)\s+(p\S+)", lower)
        if m:
            return "event", "v7_user_approval", {"pending_id": m.group(1)}, ""
        m = re.search(r"(?:deny|reject|відхили|заборони|отклони)\s+(p\S+)", lower)
        if m:
            return "event", "v7_user_deny", {"pending_id": m.group(1)}, ""

        # Safety: "постав safety 4", "рівень безпеки 5"
        m = re.search(r"(?:safety|безпек[аи]|безопасност[ьи]|рівень|уровень)\D{0,20}([0-6])", lower)
        if m:
            return "safety", "set_safety", {"level": int(m.group(1))}, ""

        # Screen reading / GUI understanding.
        if any(p in lower for p in [
            "проаналізуй екран", "розбери екран", "розбери інтерфейс", "зрозумій екран",
            "що натиснути", "куди натиснути", "яку кнопку", "analyze screen",
            "understand screen", "understand gui", "analyze gui", "what should i click"
        ]):
            return "event", "screen_understand_requested", {"request_id": f"nl_gui_{int(time.time())}", "mode": "gui_understanding"}, ""
        if any(p in lower for p in ["що на екрані", "прочитай екран", "подивись на екран", "read the screen", "what is on screen", "look at the screen", "що тут не так"]):
            return "event", "screen_capture_requested", {"request_id": f"nl_screen_{int(time.time())}"}, ""

        # Sleep/consolidation.
        if any(p in lower for p in ["запусти сон", "консолідуй пам", "консолідація пам", "run sleep", "sleep cycle", "dream replay", "consolidate memory"]):
            return "event", "sleep_cycle_requested", {"force": True}, ""


        # Web search / web learning.
        m = re.search(r"(?:вивчи|навчися|досліди|изучи|research|learn about|learn|study)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m and not any(x in lower for x in ["файл", "files", "папку", "folder"]):
            topic = m.group(1).strip().strip('"\'')
            topic = re.sub(r"^(?:тему|topic|about)\s+", "", topic, flags=re.IGNORECASE).strip()
            return "event", "web_learn_requested", {"topic": topic}, ""

        m = re.search(r"(?:пошукай\s+в\s+інтернеті|пошукай\s+в\s+вебі|знайди\s+в\s+інтернеті|web search|search web|google|гугл(?:и)?|інтернет)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m:
            query = m.group(1).strip().strip('"\'')
            return "event", "web_search_requested", {"query": query}, ""

        m = re.search(r"(?:прочитай\s+сайт|відкрий\s+сайт|fetch url|read url|прочитай\s+url)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m:
            url = m.group(1).strip().strip('"\'')
            return "event", "web_fetch_requested", {"url": url}, ""

        # Durable memory search / recall.
        m = re.search(r"(?:згадай|пригадай|пошукай(?:\s+в)?\s+пам|пошукай\s+у\s+пам|remember|recall|search memory|find in memory)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m:
            query = m.group(1).strip().strip('"\'')
            query = re.sub(r"^(?:про|about)\s+", "", query, flags=re.IGNORECASE).strip()
            return "event", "memory_search_requested", {"query_text": query, "top_k": 8}, ""

        # Runtime / service status.
        if any(p in lower for p in ["runtime status", "service status", "статус сервісу", "стан сервісу", "статус рантайму", "стан програми", "health status", "покажи runtime"]):
            return "event", "runtime_status_requested", {}, ""
        if any(p in lower for p in ["runtime self-test", "health check", "self test", "самотест", "перевір себе", "перевір стан програми"]):
            return "event", "runtime_self_test_requested", {}, ""

        # V11 system monitor / proactive companion.
        if any(p in lower for p in ["перевір систему", "діагностуй систему", "що з комп", "що з пк", "стан пк", "стан комп", "system monitor", "system status", "diagnose system", "monitor pc", "перевір ресурси"]):
            return "event", "system_diagnose_requested", {"respond": True}, ""
        if any(p in lower for p in ["покажи proactive", "proactive status", "статус напарника", "стан напарника", "companion status", "що ти помітив"]):
            return "event", "proactive_status_requested", {"respond": True}, ""
        if any(p in lower for p in ["daily summary", "денний звіт", "щоденний звіт", "підсумок дня", "companion summary", "зроби підсумок"]):
            return "event", "daily_summary_requested", {"respond": True}, ""

        # Status/self/world/settings.
        if any(p in lower for p in ["статус пам", "стан пам", "де пам", "storage status", "memory status", "покажи пам", "покажи стан пам", "де зберігається пам"]):
            return "event", "memory_status_requested", {}, ""
        if any(p in lower for p in ["статус дій", "статус action", "action status", "що ти можеш зробити", "покажи можливості"]):
            return "event", "action_status_requested", {}, ""
        if any(p in lower for p in ["хто ти", "покажи self", "твій стан", "що ти знаєш про себе", "who are you"]):
            return "event", "self_model_request", {"respond": True, "reason": "natural_language_self_query"}, ""
        if any(p in lower for p in ["що ти знаєш про світ", "покажи world", "контекст світу", "world model"]):
            return "event", "world_model_request", {"respond": True, "reason": "natural_language_world_query"}, ""
        if any(p in lower for p in ["статус моделей", "покажи моделі", "model status", "models status", "яка модель", "model router", "model health"]):
            return "response", "models", {}, self._model_router_status()
        if any(p in lower for p in ["покажи налаштування", "відкрий налаштування", "settings", "налаштування"]):
            return "response", "settings", {}, "Налаштування доступні у Desktop → Settings Center. Там можна керувати model profiles, LLM ролями, голосом, OCR, action executor, safety, sleep, emotion, self/world model і web UI. З голосу/чату я можу змінювати live safety-рівень і показувати статус моделей, а повні env-налаштування краще міняти через Settings Center."

        # V9.7 general GUI automation: natural requests for desktop/browser/app control.
        if any(p in lower for p in ["статус gui", "gui status", "статус гуі", "статус інтерфейс"]):
            return "event", "gui_task_status_requested", {}, ""
        if any(p in lower for p in ["продовжуй gui", "продовжуй гуі", "gui step", "наступний gui крок", "продовжуй інтерфейс"]):
            m2 = re.search(r"(gt\d+)", lower)
            return "event", "gui_task_step_requested", {"task_id": m2.group(1) if m2 else ""}, ""
        if any(p in lower for p in ["скасуй gui", "cancel gui", "зупини gui", "зупини гуі"]):
            m2 = re.search(r"(gt\d+)", lower)
            return "event", "gui_task_cancel_requested", {"task_id": m2.group(1) if m2 else ""}, ""
        gui_triggers = [
            "знайди на ютуб", "на youtube", "на ютуб", "увімкни", "включи", "play ",
            "відкрий браузер", "зайди в браузер", "натисни", "клікни", "click ",
            "введи в", "напиши в полі", "керуй комп", "зроби на екрані", "через інтерфейс",
            "open browser", "find on youtube", "search on youtube", "control the screen", "use the gui",
        ]
        if any(p in lower for p in gui_triggers):
            mode = "auto" if any(x in lower for x in ["автоном", "сам", "самостійно", "auto"]) else "guided"
            return "event", "gui_task_requested", {"goal": raw, "mode": mode, "respond": True}, ""

        # V9.4 task chains: broad goals, continuation, status, cancellation.
        m = re.search(r"(?:^|\b)(?:task|задача|ланцюг задач|цепочка задач)\s*(?:[:\-])?\s+(.+)$", raw, flags=re.IGNORECASE)
        if m:
            goal = m.group(1).strip().strip('"\'')
            return "task", "task_chain_requested", {"goal": goal, "autonomy": "guided"}, ""
        if any(p in lower for p in ["продовжуй задачу", "продовжи задачу", "continue task", "next task step", "наступний крок задачі"]):
            task_id = ""
            m2 = re.search(r"(tc\d+)", lower)
            if m2:
                task_id = m2.group(1)
            return "task_step", "task_chain_step_requested", {"task_id": task_id}, ""
        if any(p in lower for p in ["статус задачі", "статус task", "task status", "покажи задачі", "активні задачі"]):
            m2 = re.search(r"(tc\d+)", lower)
            return "task_status", "task_chain_status_requested", {"task_id": m2.group(1) if m2 else ""}, ""
        if any(p in lower for p in ["скасуй задачу", "cancel task", "зупини задачу"]):
            m2 = re.search(r"(tc\d+)", lower)
            return "task_cancel", "task_chain_cancel_requested", {"task_id": m2.group(1) if m2 else ""}, ""
        if any(p in lower for p in ["автономно продовжуй", "resume task", "продовжуй автономно"]):
            m2 = re.search(r"(tc\d+)", lower)
            return "task_resume", "task_chain_resume_requested", {"task_id": m2.group(1) if m2 else ""}, ""
        if any(p in lower for p in ["розберися з", "розберись з", "займись", "виріши задачу", "зроби задачу", "figure out", "handle this task"]):
            goal = raw
            return "task", "task_chain_requested", {"goal": goal, "autonomy": "auto" if ("автоном" in lower or "auto" in lower) else "guided"}, ""

        # Apply a ready V9 repair proposal. Still goes through V7 write_file safety.
        m = re.search(r"(?:застосуй|примени|apply)\s+(?:ремонт|repair|patch|патч)?\s*(rp\d+)?", lower)
        if m and ("застосуй" in lower or "apply" in lower or "примени" in lower):
            return "repair_apply", "code_repair_apply_requested", {"proposal_id": (m.group(1) or "").strip()}, ""

        # Code repair intent. This starts diagnostics + LLM patch proposal; writing still uses V7 safety.
        repair_words = ["виправ", "почини", "пофікси", "исправ", "fix", "repair", "зроби патч", "підготуй патч"]
        error_words = ["помил", "ошиб", "error", "bug", "traceback", "exception", "проект", "проєкт", "код"]
        if self.repair_agent_enabled and any(w in lower for w in repair_words) and any(w in lower for w in error_words):
            path = "."
            # Prefer the last location phrase, e.g. "виправ помилки в testproj" -> testproj.
            matches = re.findall(r"(?:\s|^)(?:в|у|in)\s+([^,.!?]+)", raw, flags=re.IGNORECASE)
            if matches:
                path = matches[-1].strip().strip('"\'') or "."
            # Cleanup common leading nouns accidentally captured from Ukrainian/Russian phrasing.
            path = re.sub(r"^(?:помилки|ошибки|errors|баги|bugs)\s+(?:в|у|in)\s+", "", path, flags=re.IGNORECASE).strip() or "."
            return "repair", "code_repair_requested", {"path": path, "request_id": f"repair_{int(time.time() * 1000)}", "request_text": raw}, ""

        # File listing.
        m = re.search(r"(?:покажи|покаж[иі]|список|list|show)\s+(?:файли|файлів|files)(?:\s+(?:в|у|in)?\s*(.+))?$", raw, flags=re.IGNORECASE)
        if m:
            path = (m.group(1) or ".").strip().strip('"\'')
            return "action", "list_files", {"path": path}, ""

        # Read file.
        m = re.search(r"(?:прочитай|відкрий|покажи|read|open|show)\s+(?:файл\s+|file\s+)?(.+)$", raw, flags=re.IGNORECASE)
        if m and any(w in lower for w in ["прочитай", "read file", "open file", "відкрий файл", "покажи файл"]):
            path = m.group(1).strip().strip('"\'')
            return "action", "read_file", {"path": path}, ""

        # Search.
        m = re.search(r"(?:знайди|пошукай|search|find)\s+(.+?)(?:\s+(?:в|у|in)\s+(.+))?$", raw, flags=re.IGNORECASE)
        if m:
            query = m.group(1).strip().strip('"\'')
            path = (m.group(2) or ".").strip().strip('"\'')
            return "action", "search_files", {"path": path, "query": query}, ""

        # mkdir.
        m = re.search(r"(?:створи|создай|create|make)\s+(?:папку|директорію|folder|dir)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m:
            path = m.group(1).strip().strip('"\'')
            return "action", "create_dir", {"path": path}, ""

        # Write / append.
        m = re.search(r"(?:допиши|append)\s+(?:в|to)\s+(.+?)\s*::\s*(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return "action", "write_file", {"path": m.group(1).strip().strip('"\''), "content": m.group(2), "append": True}, ""
        m = re.search(r"(?:запиши|write)\s+(?:в|to)\s+(.+?)\s*::\s*(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return "action", "write_file", {"path": m.group(1).strip().strip('"\''), "content": m.group(2)}, ""

        # Run allowlisted command.
        m = re.search(r"(?:запусти|виконай|run|execute)\s+(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
        if m:
            command = m.group(1).strip()
            return "action", "run_command", {"cwd": ".", "command": command}, ""

        return None

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "require_explicit_verb": self.require_explicit_verb,
            "repair_agent_enabled": self.repair_agent_enabled,
            "supported_natural_intents": [
                "screen_read", "gui_understanding_v9_6", "sleep_consolidate", "self_status", "world_status", "settings_help",
                "action_status", "set_safety", "approve_pending", "deny_pending", "list_files", "read_file",
                "search_files", "create_dir", "write_file", "append_file", "run_command", "web_search", "web_learn", "web_fetch", "code_repair_v9", "apply_repair_proposal", "task_chain_v9_4", "gui_automation_v9_7", "system_monitor_v11", "proactive_companion_v11",
            ],
        })
        return base


def create_module() -> ActionIntentModule:
    return ActionIntentModule()
