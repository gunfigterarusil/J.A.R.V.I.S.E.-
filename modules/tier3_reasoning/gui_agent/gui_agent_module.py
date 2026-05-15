"""V9.7 General GUI Agent — safe screen-driven desktop automation.

This module is intentionally *general* instead of hardcoded for one app/site.
It uses an observe -> reason -> act -> observe loop:

  user voice/chat/desktop goal
  -> gui_task_requested
  -> screen_understand_requested
  -> LLM chooses one small next action from a strict schema
  -> action_request through V7 safety/firewall
  -> action_result
  -> repeat only within configured limits

The module never receives raw unrestricted OS control. It can only request
small GUI actions that the V7 action executor supports, and those actions still
pass through PermissionManager + RiskEngine + user confirmation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

try:
    from core.llm_router import TaskType
except Exception:  # pragma: no cover
    TaskType = None  # type: ignore

logger = logging.getLogger("gui_agent.v9_7")


class GuiTask:
    def __init__(self, task_id: str, goal: str, mode: str = "guided", status: str = "created") -> None:
        self.task_id = task_id
        self.goal = goal
        self.mode = mode  # guided|auto
        self.status = status
        self.created_at = time.time()
        self.steps_done = 0
        self.awaiting_observation = False
        self.awaiting_action = False
        self.last_observation: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.last_action: Dict[str, Any] = {}


class GuiAgentModule(CognitiveModule):
    MODULE_DESCRIPTION = "V9.7 general safe GUI automation agent"
    MODULE_VERSION = "9.7.0"

    def __init__(self) -> None:
        super().__init__(module_id="gui_agent", cost={"cpu": 0.15, "gpu": 0.0, "ram": 0.05})
        self.enabled = True
        self.auto_enabled = False
        self.max_steps = 12
        self.step_delay = 1.0
        self.allowed_actions = {
            "observe", "done", "open_url", "open_app", "click_xy", "click_text",
            "type_text", "press", "hotkey", "scroll", "wait",
        }
        self.require_confirmation = True
        self.block_sensitive = True
        self.active_task_id: str = ""
        self.tasks: Dict[str, GuiTask] = {}
        self._last_screen: Dict[str, Any] = {}

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "gui_automation", None)
        if cfg is not None:
            self.enabled = bool(getattr(cfg, "enabled", True))
            self.auto_enabled = bool(getattr(cfg, "auto_enabled", False))
            self.max_steps = int(getattr(cfg, "max_steps", 12) or 12)
            self.step_delay = float(getattr(cfg, "step_delay_seconds", 1.0) or 1.0)
            raw = getattr(cfg, "allowed_actions", []) or []
            self.allowed_actions = {str(x).strip() for x in raw if str(x).strip()} or self.allowed_actions
            self.require_confirmation = bool(getattr(cfg, "require_confirmation", True))
            self.block_sensitive = bool(getattr(cfg, "block_sensitive", True))
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "gui_task_requested",
                "gui_task_step_requested",
                "gui_task_status_requested",
                "gui_task_cancel_requested",
                "screen_understood",
                "screen_parsed",
                "screen_error",
                "action_result",
            ],
        )
        logger.info("[V9.7] GUI agent initialized enabled=%s auto_enabled=%s", self.enabled, self.auto_enabled)

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        if event.type == "gui_task_requested":
            await self._start_task(event)
        elif event.type == "gui_task_step_requested":
            await self._step_requested(event)
        elif event.type == "gui_task_status_requested":
            await self._status(event)
        elif event.type == "gui_task_cancel_requested":
            await self._cancel(event)
        elif event.type in {"screen_understood", "screen_parsed", "screen_error"}:
            self._last_screen = dict(event.data)
            await self._handle_observation(event)
        elif event.type == "action_result":
            await self._handle_action_result(event)

    async def _start_task(self, event: Event) -> None:
        goal = str(event.data.get("goal", "") or event.data.get("text", "") or "").strip()
        if not goal:
            await self._respond("GUI task needs a goal, for example: /gui-task знайди музику на YouTube")
            return
        mode = str(event.data.get("mode") or event.data.get("autonomy") or "guided").lower()
        if mode == "auto" and not self.auto_enabled:
            mode = "guided"
        task_id = f"gt{int(time.time() * 1000)}"
        task = GuiTask(task_id=task_id, goal=goal, mode=mode, status="observing")
        self.tasks[task_id] = task
        self.active_task_id = task_id
        await self._respond(
            f"GUI task created: {task_id}\n"
            f"Goal: {goal}\n"
            f"Mode: {mode}. I will observe the screen, decide one safe next step, and route any GUI action through safety gates."
        )
        await self._request_observation(task)

    async def _step_requested(self, event: Event) -> None:
        task = self._get_task(str(event.data.get("task_id", "") or ""))
        if task is None:
            await self._respond("No active GUI task. Start one with /gui-task <goal> or say what you want me to do on the computer.")
            return
        if task.status in {"done", "cancelled", "failed"}:
            await self._respond(f"GUI task {task.task_id} is {task.status}.")
            return
        await self._request_observation(task)

    async def _status(self, event: Event) -> None:
        task = self._get_task(str(event.data.get("task_id", "") or ""))
        if task is None:
            if not self.tasks:
                await self._respond("No GUI tasks yet.")
                return
            rows = []
            for t in list(self.tasks.values())[-8:]:
                rows.append(f"- {t.task_id}: {t.status}, steps={t.steps_done}, mode={t.mode}, goal={t.goal[:80]}")
            await self._respond("GUI tasks:\n" + "\n".join(rows))
            return
        await self._respond(self._format_task(task))

    async def _cancel(self, event: Event) -> None:
        task = self._get_task(str(event.data.get("task_id", "") or ""))
        if task is None:
            await self._respond("No active GUI task to cancel.")
            return
        task.status = "cancelled"
        task.awaiting_action = False
        task.awaiting_observation = False
        await self._respond(f"GUI task cancelled: {task.task_id}")

    async def _request_observation(self, task: GuiTask) -> None:
        task.awaiting_observation = True
        task.awaiting_action = False
        task.status = "observing"
        if not self.kernel:
            return
        self.kernel.event_bus.emit(
            Event(
                type="screen_understand_requested",
                data={
                    "request_id": f"gui_{task.task_id}_{task.steps_done}",
                    "reason": "gui_agent_observe",
                    "mode": "gui_automation_observe",
                    "respond": False,
                    "gui_task_id": task.task_id,
                },
                source_module=self.module_id,
            ),
            Priority.REALTIME,
        )

    async def _handle_observation(self, event: Event) -> None:
        task_id = str(event.data.get("gui_task_id") or self.active_task_id or "")
        task = self.tasks.get(task_id)
        if task is None or not task.awaiting_observation:
            return
        task.awaiting_observation = False
        task.last_observation = dict(event.data)
        task.history.append({"kind": "observation", "data": self._compact_observation(event.data), "ts": time.time()})
        if not event.data.get("ok", True):
            task.status = "failed"
            await self._respond(f"GUI task {task.task_id} could not observe the screen: {event.data.get('error', 'unknown error')}")
            return
        await self._decide_and_act(task)

    async def _handle_action_result(self, event: Event) -> None:
        req = str(event.data.get("request_id", ""))
        if not req.startswith("gui_"):
            return
        task_id = req.split("_", 2)[1] if "_" in req else self.active_task_id
        task = self.tasks.get(task_id)
        if task is None:
            return
        task.awaiting_action = False
        task.history.append({"kind": "action_result", "data": dict(event.data), "ts": time.time()})
        ok = bool(event.data.get("ok"))
        if not ok:
            task.status = "blocked_or_failed"
            await self._respond(
                f"GUI step for {task.task_id} did not complete: {event.data.get('error', 'unknown error')}\n"
                f"You can approve pending actions if shown, adjust safety level, or ask me to choose a safer step."
            )
            return
        if task.mode == "auto" and task.steps_done < self.max_steps:
            await asyncio.sleep(max(0.1, self.step_delay))
            await self._request_observation(task)
        else:
            task.status = "waiting_next_step"
            await self._respond(f"GUI step completed for {task.task_id}. Say 'продовжуй GUI задачу' or use /gui-step {task.task_id} for the next step.")

    async def _decide_and_act(self, task: GuiTask) -> None:
        if task.steps_done >= self.max_steps:
            task.status = "paused_max_steps"
            await self._respond(f"GUI task {task.task_id} paused after {self.max_steps} steps. Increase GUI_AUTOMATION_MAX_STEPS if needed.")
            return
        action = await self._choose_action(task)
        action = self._sanitize_action(task, action)
        task.last_action = action
        task.history.append({"kind": "decision", "data": action, "ts": time.time()})
        if action.get("action") == "done":
            task.status = "done"
            await self._respond(f"GUI task done: {task.task_id}\n{action.get('reason', 'Goal appears complete.')}")
            return
        if action.get("action") == "observe":
            await self._respond(f"I need another screen observation for {task.task_id}: {action.get('reason', '')}")
            await self._request_observation(task)
            return
        if action.get("action") not in self.allowed_actions:
            task.status = "waiting_next_step"
            await self._respond(f"I chose unsupported GUI action: {action.get('action')}. Allowed: {', '.join(sorted(self.allowed_actions))}")
            return
        mapped = self._map_gui_action(task, action)
        if not mapped:
            task.status = "waiting_next_step"
            await self._respond(f"I could not map the GUI decision into a safe action. Decision: {json.dumps(action, ensure_ascii=False)}")
            return
        task.steps_done += 1
        task.awaiting_action = True
        task.status = "acting"
        self._emit_action(mapped[0], mapped[1], task, action)
        await self._respond(
            f"GUI task {task.task_id} step {task.steps_done}: {action.get('action')} — {action.get('reason','')}\n"
            f"The action has been sent through the safety firewall. If it becomes pending, approve it explicitly."
        )

    async def _choose_action(self, task: GuiTask) -> Dict[str, Any]:
        heuristic = self._heuristic_action(task)
        if heuristic:
            return heuristic
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router is None:
            return {"action": "observe", "reason": "No LLM router available."}
        system = (
            "You are JAV's GUI control cortex. Choose exactly one safe next GUI action. "
            "Return ONLY compact JSON with keys: action, reason, and action-specific fields. "
            "Allowed actions: done, observe, open_url, open_app, click_xy, click_text, type_text, press, hotkey, scroll, wait. "
            "Never type passwords, payment info, private tokens, or irreversible confirmations. "
            "Prefer small reversible steps. If unsure, choose observe or done with reason."
        )
        prompt = self._build_prompt(task)
        try:
            kwargs = {"system": system, "temperature": 0.2, "max_tokens": 900}
            if TaskType is not None:
                raw = await router.generate(prompt, task_type=TaskType.ACTION_PLANNING, **kwargs)
            else:
                raw = await router.generate(prompt, **kwargs)
            parsed = self._parse_json(raw)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning("[V9.7] LLM GUI decision failed: %s", exc)
        return {"action": "observe", "reason": "Could not produce a safe JSON GUI decision."}

    def _heuristic_action(self, task: GuiTask) -> Optional[Dict[str, Any]]:
        # Only handles the first obvious 'open/search' step; after that the LLM or user guides steps.
        if task.steps_done > 0:
            return None
        g = task.goal.lower()
        if any(x in g for x in ["youtube", "ютуб", "ютюб", "музик", "music", "пісн", "песн"]):
            query = self._extract_music_query(task.goal)
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            return {"action": "open_url", "url": url, "reason": f"Open YouTube search for: {query}"}
        if re.search(r"https?://\S+", task.goal):
            url = re.search(r"https?://\S+", task.goal).group(0)  # type: ignore[union-attr]
            return {"action": "open_url", "url": url, "reason": "Open requested URL."}
        if any(x in g for x in ["відкрий браузер", "open browser", "браузер"]):
            return {"action": "open_url", "url": "https://www.google.com", "reason": "Open browser at Google."}
        return None

    def _extract_music_query(self, goal: str) -> str:
        text = goal.strip()
        text = re.sub(r"(?i)джарвіс|jarvis|знайди|найди|find|пошукай|включи|увімкни|play|на\s+ютубі|на\s+youtube|youtube|ютуб|музику|music", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" .,!?:;\"'")
        if not text or len(text) < 3:
            # Generic fallback: intentionally avoids pretending to know private taste.
            return "music mix"
        return text[:120]

    def _sanitize_action(self, task: GuiTask, action: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(action, dict):
            return {"action": "observe", "reason": "Invalid GUI decision type."}
        name = str(action.get("action", "observe")).strip().lower()
        action["action"] = name
        joined = json.dumps(action, ensure_ascii=False).lower()
        if self.block_sensitive and any(x in joined for x in ["password", "пароль", "token", "api key", "credit card", "карта", "оплат", "buy", "purchase"]):
            return {"action": "done", "reason": "Blocked sensitive/financial/credential-related GUI action. Ask for manual user control."}
        return action

    def _map_gui_action(self, task: GuiTask, action: Dict[str, Any]) -> Optional[tuple[str, Dict[str, Any]]]:
        name = str(action.get("action", ""))
        payload: Dict[str, Any] = {"request_id": f"gui_{task.task_id}_{task.steps_done + 1}", "respond": False, "reason": action.get("reason", ""), "goal": task.goal}
        if name == "open_url":
            payload["url"] = str(action.get("url", "")).strip()
            return "open_url", payload if payload["url"] else None
        if name == "open_app":
            payload["app"] = str(action.get("app", "")).strip()
            return "open_app", payload if payload["app"] else None
        if name == "click_xy":
            payload.update({"x": int(float(action.get("x", 0))), "y": int(float(action.get("y", 0)))})
            return "gui_click", payload
        if name == "click_text":
            label = str(action.get("text") or action.get("label") or "").strip().lower()
            el = self._find_ui_element(task.last_observation, label)
            if not el:
                return None
            center = el.get("center") or [0, 0]
            payload.update({"x": int(center[0]), "y": int(center[1]), "matched_text": el.get("text", label)})
            return "gui_click", payload
        if name == "type_text":
            payload["text"] = str(action.get("text", ""))
            return "gui_type_text", payload if payload["text"] else None
        if name == "press":
            payload["key"] = str(action.get("key", "")).strip().lower()
            return "gui_press", payload if payload["key"] else None
        if name == "hotkey":
            keys = action.get("keys", [])
            if isinstance(keys, str):
                keys = [x.strip() for x in keys.split("+") if x.strip()]
            payload["keys"] = [str(x).strip().lower() for x in keys if str(x).strip()]
            return "gui_hotkey", payload if payload["keys"] else None
        if name == "scroll":
            payload["amount"] = int(float(action.get("amount", -5)))
            return "gui_scroll", payload
        if name == "wait":
            payload["seconds"] = float(action.get("seconds", 1.0))
            return "gui_wait", payload
        return None

    def _find_ui_element(self, observation: Dict[str, Any], label: str) -> Optional[Dict[str, Any]]:
        if not label:
            return None
        elements = observation.get("ui_elements", []) or []
        label_l = label.lower()
        best = None
        best_score = 0
        for el in elements:
            txt = str(el.get("text", "")).lower()
            if not txt:
                continue
            score = 0
            if label_l == txt:
                score = 100
            elif label_l in txt or txt in label_l:
                score = 70
            else:
                words = set(label_l.split()) & set(txt.split())
                score = len(words) * 15
            if score > best_score:
                best_score, best = score, el
        return best if best_score >= 30 else None

    def _emit_action(self, action_type: str, payload: Dict[str, Any], task: GuiTask, decision: Dict[str, Any]) -> None:
        if not self.kernel:
            return
        data = {
            "action_type": action_type,
            "payload": payload,
            "request_id": payload.get("request_id"),
            "respond": False,
            "natural_language_request": task.goal,
            "gui_task_id": task.task_id,
            "gui_decision": decision,
            "autonomous_chain": task.mode == "auto",
        }
        self.kernel.event_bus.emit(Event(type="action_request", data=data, source_module=self.module_id), Priority.REALTIME)

    def _compact_observation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "summary": str(data.get("summary", ""))[:700],
            "active_window": data.get("active_window", ""),
            "likely_context": data.get("likely_context", ""),
            "important_blocks": (data.get("important_blocks", []) or [])[:6],
            "ui_elements": (data.get("ui_elements", []) or [])[:12],
            "recommended_actions": (data.get("recommended_actions", []) or [])[:5],
        }

    def _build_prompt(self, task: GuiTask) -> str:
        obs = self._compact_observation(task.last_observation)
        return (
            f"Goal: {task.goal}\n"
            f"Task id: {task.task_id}; mode={task.mode}; step={task.steps_done}/{self.max_steps}\n"
            f"Screen observation JSON:\n{json.dumps(obs, ensure_ascii=False, indent=2)[:6000]}\n\n"
            "Choose ONE next action. Examples:\n"
            '{"action":"open_url","url":"https://www.youtube.com/results?search_query=lofi","reason":"open search results"}\n'
            '{"action":"click_text","text":"Play","reason":"click visible Play button"}\n'
            '{"action":"type_text","text":"search query","reason":"type into focused field"}\n'
            '{"action":"press","key":"enter","reason":"submit focused search"}\n'
            '{"action":"done","reason":"the goal is complete or requires user takeover"}\n'
        )

    def _parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        raw = raw.strip()
        try:
            return json.loads(raw)
        except Exception:
            pass
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None

    def _get_task(self, task_id: str) -> Optional[GuiTask]:
        if task_id and task_id in self.tasks:
            return self.tasks[task_id]
        if self.active_task_id and self.active_task_id in self.tasks:
            return self.tasks[self.active_task_id]
        return None

    def _format_task(self, task: GuiTask) -> str:
        return (
            f"GUI task {task.task_id}\n"
            f"status={task.status} mode={task.mode} steps={task.steps_done}/{self.max_steps}\n"
            f"goal={task.goal}\n"
            f"last_action={json.dumps(task.last_action, ensure_ascii=False)[:900]}"
        )

    async def _respond(self, text: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="response_generated", data={"text": text, "source": "gui_agent/v9.7"}, source_module=self.module_id), Priority.COGNITIVE)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "auto_enabled": self.auto_enabled,
            "max_steps": self.max_steps,
            "step_delay": self.step_delay,
            "require_confirmation": self.require_confirmation,
            "allowed_actions": sorted(self.allowed_actions),
            "active_task_id": self.active_task_id,
            "tasks": [self._format_task(t) for t in list(self.tasks.values())[-8:]],
        })
        return base


def create_module() -> GuiAgentModule:
    return GuiAgentModule()
