"""V13 Advanced Task Orchestrator.

This module upgrades the earlier V9.4 task chains into a stronger cognitive
orchestrator for long tasks:

  goal -> context recall -> strategy A/B/C -> steps -> verifier -> retry
  -> rollback guidance -> final report -> memory/sleep consolidation

The orchestrator still never bypasses safety. All file, shell and GUI actions
are emitted as normal events/actions and must pass through the existing safety
layer and approval gates.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority
from core.llm_router import TaskType

logger = logging.getLogger("task_chains.v13")

TERMINAL_STATUSES = {"done", "failed", "cancelled"}
WAITING_EVENTS = {
    "memory_retrieved", "screen_parsed", "web_search_completed", "web_learning_completed",
    "web_fetch_completed", "code_repair_proposal_ready", "code_repair_diagnostic",
    "action_result", "action_denied", "action_pending_confirmation", "sleep_cycle_completed",
    "gui_task_completed", "gui_task_failed", "gui_task_step_verified",
}


class TaskStep:
    def __init__(
        self,
        id: str,
        title: str,
        kind: str = "think",
        payload: Optional[Dict[str, Any]] = None,
        status: str = "pending",
        result: str = "",
        started_at: float = 0.0,
        finished_at: float = 0.0,
        attempts: int = 0,
        max_attempts: int = 2,
        verifier: Optional[Dict[str, Any]] = None,
        rollback: Optional[Dict[str, Any]] = None,
        strategy: str = "A",
    ) -> None:
        self.id = id
        self.title = title
        self.kind = kind
        self.payload = payload or {}
        self.status = status
        self.result = result
        self.started_at = started_at
        self.finished_at = finished_at
        self.attempts = attempts
        self.max_attempts = max_attempts
        self.verifier = verifier or {"type": "llm_or_signal", "success_hint": "step produced a useful result"}
        self.rollback = rollback or {"type": "manual", "hint": "review the step result before applying further changes"}
        self.strategy = strategy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "payload": self.payload,
            "status": self.status,
            "result": self.result,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "verifier": self.verifier,
            "rollback": self.rollback,
            "strategy": self.strategy,
        }


class TaskChain:
    def __init__(
        self,
        id: str,
        goal: str,
        status: str = "planned",
        autonomy: str = "guided",
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
        current_step: int = 0,
        steps: Optional[List[TaskStep]] = None,
        context: Optional[Dict[str, Any]] = None,
        notes: Optional[List[str]] = None,
        strategies: Optional[List[Dict[str, Any]]] = None,
        active_strategy: str = "A",
        verification_log: Optional[List[Dict[str, Any]]] = None,
        failure_log: Optional[List[Dict[str, Any]]] = None,
        rollback_log: Optional[List[Dict[str, Any]]] = None,
        progress_score: float = 0.0,
    ) -> None:
        now = time.time()
        self.id = id
        self.goal = goal
        self.status = status
        self.autonomy = autonomy
        self.created_at = now if created_at is None else created_at
        self.updated_at = now if updated_at is None else updated_at
        self.current_step = current_step
        self.steps = steps or []
        self.context = context or {}
        self.notes = notes or []
        self.strategies = strategies or []
        self.active_strategy = active_strategy
        self.verification_log = verification_log or []
        self.failure_log = failure_log or []
        self.rollback_log = rollback_log or []
        self.progress_score = progress_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "autonomy": self.autonomy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_step": self.current_step,
            "steps": [s.to_dict() for s in self.steps],
            "context": self.context,
            "notes": self.notes[-50:],
            "strategies": self.strategies,
            "active_strategy": self.active_strategy,
            "verification_log": self.verification_log[-50:],
            "failure_log": self.failure_log[-50:],
            "rollback_log": self.rollback_log[-30:],
            "progress_score": self.progress_score,
        }


class TaskChainModule(CognitiveModule):
    MODULE_DESCRIPTION = "V13 advanced task orchestrator with strategies, verification, retry and rollback guidance"
    MODULE_VERSION = "1.0.0"

    def __init__(self) -> None:
        super().__init__(module_id="task_chains", cost={"cpu": 0.28, "gpu": 0.10, "ram": 0.12})
        self.enabled = True
        self.auto_step_default = False
        self.max_steps = 12
        self.step_timeout = 120.0
        self.max_retries_per_step = 2
        self.verifier_enabled = True
        self.rollback_enabled = True
        self.strategy_count = 3
        self.auto_continue_after_safe_step = True
        self.chains: Dict[str, TaskChain] = {}
        self._waiting: Dict[str, Dict[str, Any]] = {}
        self._state_path: Optional[Path] = None

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "task_chains", None)
        self.enabled = bool(getattr(cfg, "enabled", True))
        self.auto_step_default = bool(getattr(cfg, "auto_step_default", False))
        self.max_steps = int(getattr(cfg, "max_steps", 12))
        self.step_timeout = float(getattr(cfg, "step_timeout_seconds", 120.0))
        self.max_retries_per_step = int(getattr(cfg, "max_retries_per_step", 2))
        self.verifier_enabled = bool(getattr(cfg, "verifier_enabled", True))
        self.rollback_enabled = bool(getattr(cfg, "rollback_enabled", True))
        self.strategy_count = int(getattr(cfg, "strategy_count", 3))
        self.auto_continue_after_safe_step = bool(getattr(cfg, "auto_continue_after_safe_step", True))

        persistence_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        self._state_path = persistence_dir / "task_chains_v13.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "task_chain_requested",
                "task_chain_status_requested",
                "task_chain_report_requested",
                "task_chain_step_requested",
                "task_chain_retry_requested",
                "task_chain_cancel_requested",
                "task_chain_resume_requested",
                *sorted(WAITING_EVENTS),
            ],
        )
        self._emit("task_chain_module_ready", {
            "version": self.MODULE_VERSION,
            "enabled": self.enabled,
            "auto_default": self.auto_step_default,
            "verifier_enabled": self.verifier_enabled,
            "rollback_enabled": self.rollback_enabled,
        })

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        if event.type == "task_chain_requested":
            await self._start_chain(event)
        elif event.type == "task_chain_status_requested":
            self._respond(self._format_status(event.data.get("task_id")))
        elif event.type == "task_chain_report_requested":
            self._respond(self._format_report(event.data.get("task_id")))
        elif event.type == "task_chain_step_requested":
            await self._run_next(event.data.get("task_id"), manual=True)
        elif event.type == "task_chain_retry_requested":
            await self._retry(event.data.get("task_id"), event.data.get("step_id"))
        elif event.type == "task_chain_resume_requested":
            await self._resume(event.data.get("task_id"))
        elif event.type == "task_chain_cancel_requested":
            self._cancel(event.data.get("task_id"))
        else:
            await self._handle_observation(event)

    # ------------------------------------------------------------------
    # Chain lifecycle
    # ------------------------------------------------------------------
    async def _start_chain(self, event: Event) -> None:
        goal = str(event.data.get("goal") or event.data.get("text") or event.data.get("request_text") or "").strip()
        if not goal:
            self._respond("Task chain needs a goal. Example: /task розберися з помилками в .")
            return
        task_id = str(event.data.get("task_id") or f"tc{int(time.time() * 1000)}")
        autonomy = str(event.data.get("autonomy") or ("auto" if self.auto_step_default else "guided")).lower()
        if "автоном" in goal.lower() or "auto" in goal.lower():
            autonomy = "auto"

        chain = TaskChain(id=task_id, goal=goal, autonomy="auto" if autonomy == "auto" else "guided")
        chain.context = self._snapshot_context(goal)
        self.chains[task_id] = chain

        # Let other cognitive modules prepare context too. The chain can proceed with a snapshot,
        # and observations will be attached if they arrive later.
        self._emit("memory_request", {"query_type": "dialogue_context", "query_text": f"V13 task planning context: {goal}", "top_k": 10, "request_id": f"{task_id}:memory"})
        self._emit("self_model_request", {"reason": "task_chain_v13", "request_id": task_id})
        self._emit("world_model_request", {"reason": "task_chain_v13", "request_id": task_id})
        self._emit("thought_generated", {"text": f"V13 task orchestrator started: {goal}", "source": self.module_id})

        strategies, steps = await self._make_strategy_and_plan(goal, chain.context)
        chain.strategies = strategies
        chain.active_strategy = strategies[0].get("id", "A") if strategies else "A"
        chain.steps = steps[: self.max_steps]
        if not chain.steps:
            chain.steps = [TaskStep(id="s1", title="Clarify the task and make a safe plan", kind="think")]
        chain.status = "planned"
        chain.updated_at = time.time()
        self._save_state()
        self._emit("task_chain_created", chain.to_dict())
        self._respond(self._format_created(chain))

        if chain.autonomy == "auto":
            await self._run_next(task_id, manual=False)

    async def _resume(self, task_id: Any) -> None:
        chain = self._select_chain(task_id)
        if not chain:
            self._respond("No task chain found to resume.")
            return
        chain.status = "running"
        chain.autonomy = "auto"
        chain.notes.append("Resumed in controlled auto mode.")
        self._respond(f"Resuming task chain {chain.id} in controlled auto mode.")
        await self._run_next(chain.id, manual=False)

    def _cancel(self, task_id: Any) -> None:
        chain = self._select_chain(task_id)
        if not chain:
            self._respond("No task chain found to cancel.")
            return
        chain.status = "cancelled"
        chain.updated_at = time.time()
        self._save_state()
        self._emit("task_chain_cancelled", chain.to_dict())
        self._respond(f"Cancelled task chain {chain.id}: {chain.goal}")

    async def _retry(self, task_id: Any = None, step_id: Any = None) -> None:
        chain = self._select_chain(task_id)
        if not chain:
            self._respond("No task chain found to retry.")
            return
        step = None
        if step_id:
            step = next((s for s in chain.steps if s.id == str(step_id)), None)
        if step is None:
            failed = [s for s in chain.steps if s.status == "failed"]
            step = failed[-1] if failed else (chain.steps[chain.current_step] if chain.steps else None)
        if step is None:
            self._respond("No step available to retry.")
            return
        if step.attempts >= step.max_attempts:
            self._respond(f"Step {step.id} already reached retry limit ({step.attempts}/{step.max_attempts}).")
            return
        step.status = "pending"
        step.result = ""
        chain.status = "running"
        chain.notes.append(f"Retry requested for {step.id}: {step.title}")
        self._save_state()
        await self._run_specific(chain, step)

    async def _run_next(self, task_id: Any = None, manual: bool = False) -> None:
        chain = self._select_chain(task_id)
        if not chain:
            self._respond("No task chain found. Start one with /task <goal> or say 'розберися з ...'.")
            return
        if chain.status in TERMINAL_STATUSES:
            self._respond(f"Task chain {chain.id} is already {chain.status}.")
            return

        timeout_step = self._find_timed_out_step(chain)
        if timeout_step:
            await self._handle_step_failure(chain, timeout_step, f"Step timed out after {self.step_timeout:.0f}s.")
            return

        next_step = next((s for s in chain.steps if s.status in {"pending", "failed"} and s.attempts < s.max_attempts), None)
        if next_step is None:
            if any(s.status == "waiting" for s in chain.steps):
                self._respond(f"Task chain {chain.id} is waiting for an external result/approval.")
                return
            chain.status = "done" if all(s.status in {"done", "skipped"} for s in chain.steps) else "failed"
            chain.updated_at = time.time()
            self._save_state()
            self._emit("task_chain_completed" if chain.status == "done" else "task_chain_failed", chain.to_dict())
            self._respond(self._format_final(chain))
            return
        await self._run_specific(chain, next_step)

    async def _run_specific(self, chain: TaskChain, step: TaskStep) -> None:
        chain.current_step = chain.steps.index(step)
        step.status = "running"
        step.started_at = time.time()
        step.attempts += 1
        chain.status = "running"
        chain.updated_at = time.time()
        self._save_state()
        self._emit("task_chain_step_started", {"task_id": chain.id, "step": step.to_dict()})
        await self._execute_step(chain, step)

        if step.status == "done":
            await self._verify_and_continue(chain, step)
        elif step.status == "waiting":
            return
        elif step.status == "failed":
            await self._handle_step_failure(chain, step, step.result or "Step failed.")

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    async def _make_strategy_and_plan(self, goal: str, context: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[TaskStep]]:
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router:
            prompt = (
                "Create a robust safe task plan for a local Jarvis-like assistant. Return JSON only with this schema:\n"
                "{\"strategies\":[{\"id\":\"A\",\"name\":\"...\",\"why\":\"...\",\"risk\":\"low|medium|high\"}],"
                "\"steps\":[{\"title\":\"...\",\"kind\":\"think|memory|screen|web_search|web_learn|repair|gui|action|sleep|report\","
                "\"payload\":{},\"verifier\":{\"type\":\"signal|llm|manual\",\"success_hint\":\"...\"},"
                "\"rollback\":{\"type\":\"none|manual|undo_action\",\"hint\":\"...\"},\"strategy\":\"A\"}]}\n"
                "Rules: prefer diagnosis before modification; use GUI only for screen/browser/app interaction; use action only for safe list/read/search/write/create_dir/run_command;"
                "risky effects still need safety approval; include a report step at the end; include rollback hints for writes/GUI/shell.\n\n"
                f"GOAL: {goal}\nKNOWN CONTEXT: {json.dumps(context, ensure_ascii=False)[:3500]}"
            )
            try:
                raw = await router.generate(prompt, task_type=TaskType.ACTION_PLANNING, system="You are JAV V13 advanced task orchestrator. Return compact JSON only.")
                strategies, parsed_steps = self._parse_llm_plan(raw)
                if parsed_steps:
                    return strategies or self._fallback_strategies(goal), parsed_steps[: self.max_steps]
            except Exception as exc:
                logger.warning("LLM V13 task planning failed: %s", exc)
        return self._fallback_strategies(goal), self._fallback_plan(goal)

    def _parse_llm_plan(self, raw: str) -> Tuple[List[Dict[str, Any]], List[TaskStep]]:
        raw = raw.strip()
        m_obj = re.search(r"\{[\s\S]*\}", raw)
        m_arr = re.search(r"\[[\s\S]*\]", raw)
        try:
            if m_obj:
                data = json.loads(m_obj.group(0))
                strategies = data.get("strategies") if isinstance(data.get("strategies"), list) else []
                items = data.get("steps") if isinstance(data.get("steps"), list) else []
            elif m_arr:
                strategies = []
                items = json.loads(m_arr.group(0))
            else:
                return [], []
        except Exception:
            return [], []
        allowed = {"think", "memory", "screen", "web_search", "web_learn", "repair", "gui", "action", "sleep", "report"}
        steps: List[TaskStep] = []
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "think").strip()
            if kind not in allowed:
                kind = "think"
            title = str(item.get("title") or f"Step {i}").strip()
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            verifier = item.get("verifier") if isinstance(item.get("verifier"), dict) else None
            rollback = item.get("rollback") if isinstance(item.get("rollback"), dict) else None
            strategy = str(item.get("strategy") or "A")[:3]
            steps.append(TaskStep(id=f"s{i}", title=title, kind=kind, payload=payload, verifier=verifier, rollback=rollback, strategy=strategy, max_attempts=self.max_retries_per_step + 1))
        return strategies[: self.strategy_count], steps

    def _fallback_strategies(self, goal: str) -> List[Dict[str, Any]]:
        return [
            {"id": "A", "name": "Diagnose first", "why": "Collect local context before changing anything.", "risk": "low"},
            {"id": "B", "name": "Research and compare", "why": "Use memory/web if local signals are insufficient.", "risk": "low"},
            {"id": "C", "name": "Safe repair with approval", "why": "Apply changes only after diagnostics and safety gates.", "risk": "medium"},
        ][: self.strategy_count]

    def _fallback_plan(self, goal: str) -> List[TaskStep]:
        lower = goal.lower()
        steps: List[TaskStep] = [TaskStep(id="s1", title="Recall relevant context from long-term memory", kind="memory", payload={"query": goal}, strategy="A")]
        if any(x in lower for x in ["екран", "screen", "що тут", "помилка на екрані", "інтерфейс", "gui"]):
            steps.append(TaskStep(id="s2", title="Understand the current screen/GUI", kind="screen", strategy="A"))
        if any(x in lower for x in ["інтернет", "web", "вивчи", "досліди", "пошукай", "гугл"]):
            steps.append(TaskStep(id=f"s{len(steps)+1}", title="Research the topic on the web", kind="web_learn", payload={"topic": goal}, strategy="B"))
        if any(x in lower for x in ["виправ", "помил", "bug", "error", "код", "project", "проєкт", "проект"]):
            target = self._extract_path(goal)
            steps.append(TaskStep(id=f"s{len(steps)+1}", title=f"Run project repair diagnostics for {target}", kind="repair", payload={"path": target}, strategy="C", rollback={"type": "manual", "hint": "Do not apply patch without approval; keep original files backed up."}))
        if any(x in lower for x in ["натис", "браузер", "youtube", "ютуб", "gui", "екран"]):
            steps.append(TaskStep(id=f"s{len(steps)+1}", title="Run guided GUI task if screen interaction is required", kind="gui", payload={"goal": goal, "mode": "guided"}, strategy="C", rollback={"type": "manual", "hint": "Use screenshot audit and stop if unexpected UI appears."}))
        if len(steps) == 1:
            steps.append(TaskStep(id="s2", title="Analyze the goal and choose the next safe action", kind="think", strategy="A"))
        steps.append(TaskStep(id=f"s{len(steps)+1}", title="Verify result and consolidate useful findings", kind="sleep", strategy="A"))
        steps.append(TaskStep(id=f"s{len(steps)+1}", title="Report outcome, risks, rollback and next safe action", kind="report", strategy="A"))
        for i, step in enumerate(steps, start=1):
            step.id = f"s{i}"
            step.max_attempts = self.max_retries_per_step + 1
        return steps[: self.max_steps]

    def _extract_path(self, text: str) -> str:
        matches = re.findall(r"(?:\s|^)(?:в|у|in)\s+([^,.!?]+)", text, flags=re.IGNORECASE)
        if matches:
            return matches[-1].strip().strip('"\'') or "."
        return "."

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------
    async def _execute_step(self, chain: TaskChain, step: TaskStep) -> None:
        try:
            if step.kind == "memory":
                query = step.payload.get("query") or chain.goal
                self._wait_for(chain, step, "memory_retrieved", request_id=f"{chain.id}:{step.id}:memory")
                self._emit("memory_request", {"query_type": "dialogue_context", "query_text": query, "top_k": 10, "request_id": f"{chain.id}:{step.id}:memory"})
                return
            if step.kind == "screen":
                self._wait_for(chain, step, "screen_parsed", request_id=f"{chain.id}:{step.id}:screen")
                self._emit("screen_understand_requested", {"request_id": f"{chain.id}:{step.id}:screen", "reason": "task_chain_v13", "mode": "gui_understanding", "respond": False}, Priority.REALTIME)
                return
            if step.kind == "web_search":
                query = step.payload.get("query") or chain.goal
                self._wait_for(chain, step, "web_search_completed", request_id=f"{chain.id}:{step.id}:web")
                self._emit("web_search_requested", {"query": query, "request_id": f"{chain.id}:{step.id}:web", "respond": False})
                return
            if step.kind == "web_learn":
                topic = step.payload.get("topic") or chain.goal
                self._wait_for(chain, step, "web_learning_completed", request_id=f"{chain.id}:{step.id}:web")
                self._emit("web_learn_requested", {"topic": topic, "request_id": f"{chain.id}:{step.id}:web", "respond": False})
                return
            if step.kind == "repair":
                path = step.payload.get("path") or "."
                self._wait_for(chain, step, "code_repair_proposal_ready", request_id=f"{chain.id}:{step.id}:repair")
                self._emit("code_repair_requested", {"path": path, "request_id": f"{chain.id}:{step.id}:repair", "request_text": chain.goal})
                return
            if step.kind == "gui":
                goal = step.payload.get("goal") or chain.goal
                mode = step.payload.get("mode") or "guided"
                self._wait_for(chain, step, "gui_task_completed", request_id=f"{chain.id}:{step.id}:gui")
                self._emit("gui_task_requested", {"goal": goal, "mode": mode, "request_id": f"{chain.id}:{step.id}:gui", "respond": False})
                return
            if step.kind == "action":
                action_type = str(step.payload.get("action_type") or step.payload.get("type") or "").strip()
                payload = step.payload.get("payload") if isinstance(step.payload.get("payload"), dict) else dict(step.payload)
                payload.pop("action_type", None); payload.pop("type", None)
                if not action_type:
                    raise ValueError("No action_type in step payload.")
                request_id = f"{chain.id}:{step.id}:action"
                payload["request_id"] = request_id
                self._wait_for(chain, step, "action_result", request_id=request_id)
                self._emit_action(action_type, payload, chain, step)
                return
            if step.kind == "sleep":
                self._wait_for(chain, step, "sleep_cycle_completed", request_id=f"{chain.id}:{step.id}:sleep")
                self._emit("sleep_cycle_requested", {"reason": "task_chain_v13", "request_id": f"{chain.id}:{step.id}:sleep", "force": True, "respond": False})
                return
            if step.kind == "report":
                step.result = self._make_report(chain)
                step.status = "done"; step.finished_at = time.time(); self._finish_step(chain, step); self._respond(step.result); return
            step.result = await self._think(chain, step)
            step.status = "done"; step.finished_at = time.time(); self._finish_step(chain, step)
        except Exception as exc:
            step.status = "failed"
            step.result = f"Step failed: {exc}"
            self._finish_step(chain, step)

    async def _think(self, chain: TaskChain, step: TaskStep) -> str:
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router:
            prompt = (
                f"Task goal: {chain.goal}\nActive strategy: {chain.active_strategy}\n"
                f"Current step: {step.title}\nPrevious notes: {json.dumps(chain.notes[-10:], ensure_ascii=False)}\n"
                "Give a concise insight, next safe action, risk, and verification idea."
            )
            try:
                return await router.generate(prompt, task_type=TaskType.COMPLEX_REASONING, system="You are JAV V13 internal task reasoning cortex.")
            except Exception:
                pass
        return f"Analyzed step: {step.title}. No external action was required."

    def _emit_action(self, action_type: str, payload: Dict[str, Any], chain: TaskChain, step: TaskStep) -> None:
        if not self.kernel:
            return
        top_path = payload.get("path") or payload.get("cwd")
        resolved_path = None
        if top_path:
            raw = Path(str(top_path)).expanduser()
            if not raw.is_absolute():
                workspace = Path(getattr(getattr(self.kernel.config, "actions", None), "workspace_path", "~/jarvis_workspace")).expanduser()
                resolved_path = str((workspace / raw).resolve())
            else:
                resolved_path = str(raw.resolve())
        self.kernel.event_bus.emit(Event(
            type="action_request",
            data={"action_type": action_type, "payload": payload, "path": resolved_path, "request_id": payload.get("request_id"), "respond": False, "task_chain_id": chain.id, "task_step_id": step.id},
            source_module=self.module_id,
        ), Priority.REALTIME)

    # ------------------------------------------------------------------
    # Verification / failure / rollback
    # ------------------------------------------------------------------
    async def _verify_and_continue(self, chain: TaskChain, step: TaskStep) -> None:
        if not self.verifier_enabled or step.kind in {"report"}:
            self._maybe_auto_continue(chain, step)
            return
        passed, reason = await self._verify_step(chain, step)
        chain.verification_log.append({"step_id": step.id, "passed": passed, "reason": reason, "time": time.time()})
        self._emit("task_chain_step_verified", {"task_id": chain.id, "step_id": step.id, "passed": passed, "reason": reason})
        if not passed:
            await self._handle_step_failure(chain, step, f"Verifier failed: {reason}")
            return
        self._update_progress(chain)
        self._save_state()
        self._maybe_auto_continue(chain, step)

    async def _verify_step(self, chain: TaskChain, step: TaskStep) -> Tuple[bool, str]:
        text = (step.result or "").lower()
        if any(x in text for x in ["denied", "error", "failed", "traceback", "exception", "permission denied"]):
            return False, step.result[:500]
        hint = str((step.verifier or {}).get("success_hint") or "useful result")
        if step.kind in {"memory", "screen", "web_search", "web_learn", "repair", "action", "sleep", "gui"} and not step.result:
            return False, "No result was returned by the step."
        # Optional LLM verifier for complex steps.
        if step.kind in {"repair", "gui", "action"}:
            router = getattr(self.kernel, "llm_router", None) if self.kernel else None
            if router:
                prompt = f"Goal: {chain.goal}\nStep: {step.title}\nVerifier hint: {hint}\nResult: {step.result[:2000]}\nReturn PASS or FAIL with one short reason."
                try:
                    raw = await router.generate(prompt, task_type=TaskType.CRITIQUE, system="You verify task step results. Start with PASS or FAIL.")
                    if raw.strip().lower().startswith("fail"):
                        return False, raw.strip()[:500]
                    if raw.strip().lower().startswith("pass"):
                        return True, raw.strip()[:500]
                except Exception:
                    pass
        return True, f"Passed basic verifier: {hint}"

    async def _handle_step_failure(self, chain: TaskChain, step: TaskStep, reason: str) -> None:
        step.status = "failed"
        step.result = reason
        chain.failure_log.append({"step_id": step.id, "reason": reason, "attempts": step.attempts, "time": time.time()})
        rollback = self._rollback_plan(chain, step, reason)
        if rollback:
            chain.rollback_log.append(rollback)
            self._emit("task_chain_rollback_suggested", rollback)
        if step.attempts < step.max_attempts:
            chain.status = "planned" if chain.autonomy == "guided" else "running"
            self._save_state()
            msg = f"Step {step.id} failed attempt {step.attempts}/{step.max_attempts}: {reason}\nRetry available: /task-retry {chain.id} {step.id}"
            if chain.autonomy == "auto" and self.max_retries_per_step > 0:
                self._respond(msg + "\nAuto mode will retry once after adjusting strategy.")
                step.status = "pending"
                await asyncio.sleep(0.2)
                await self._run_specific(chain, step)
            else:
                self._respond(msg)
            return
        chain.status = "failed"
        chain.updated_at = time.time()
        self._save_state()
        self._emit("task_chain_failed", chain.to_dict())
        self._respond(f"Task chain {chain.id} failed at {step.id}: {reason}\nRollback/safer path: {rollback.get('hint') if rollback else 'manual review needed'}")

    def _rollback_plan(self, chain: TaskChain, step: TaskStep, reason: str) -> Dict[str, Any]:
        rb = step.rollback or {}
        hint = rb.get("hint") or "Stop, review previous outputs, and avoid further external effects until user approves."
        if step.kind in {"action", "gui", "repair"}:
            hint = hint + " Use screenshots/logs/proposal IDs to undo manually if needed."
        return {"task_id": chain.id, "step_id": step.id, "type": rb.get("type", "manual"), "hint": hint, "reason": reason, "time": time.time()}

    def _maybe_auto_continue(self, chain: TaskChain, step: TaskStep) -> None:
        if chain.autonomy == "auto" and chain.status not in TERMINAL_STATUSES and self.auto_continue_after_safe_step:
            asyncio.create_task(self._run_next(chain.id, manual=False))
        elif chain.status not in TERMINAL_STATUSES:
            self._respond(f"Task chain {chain.id}: step {step.id} verified — {step.title}\nNext: /task-step {chain.id} або скажи 'продовжуй задачу'.")

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------
    def _wait_for(self, chain: TaskChain, step: TaskStep, event_type: str, request_id: str = "") -> None:
        step.status = "waiting"
        chain.status = "waiting"
        key = request_id or f"{chain.id}:{step.id}:{event_type}"
        self._waiting[key] = {"task_id": chain.id, "step_id": step.id, "event_type": event_type, "started_at": time.time()}
        chain.updated_at = time.time()
        self._save_state()
        self._emit("task_chain_step_waiting", {"task_id": chain.id, "step": step.to_dict(), "waiting_for": event_type, "request_id": key})

    async def _handle_observation(self, event: Event) -> None:
        request_id = str(event.data.get("request_id") or "")
        candidates: List[str] = []
        if request_id and request_id in self._waiting:
            candidates.append(request_id)
        # GUI task may not echo same completion type; match request_id prefix first.
        if request_id:
            for key in list(self._waiting.keys()):
                if key.startswith(request_id) or request_id.startswith(key):
                    if key not in candidates:
                        candidates.append(key)
        for key, wait in list(self._waiting.items()):
            if wait.get("event_type") == event.type and key not in candidates:
                candidates.append(key)
                break
        if not candidates:
            return
        key = candidates[0]
        wait = self._waiting.pop(key, None)
        if not wait:
            return
        chain = self.chains.get(wait["task_id"])
        if not chain:
            return
        step = next((s for s in chain.steps if s.id == wait["step_id"]), None)
        if not step:
            return
        if event.type in {"action_denied", "action_pending_confirmation"}:
            step.status = "waiting" if event.type == "action_pending_confirmation" else "failed"
            step.result = self._summarize_event(event)
            chain.status = "waiting" if step.status == "waiting" else "failed"
            self._save_state()
            self._respond(f"Task chain {chain.id} paused at step {step.id}: {step.result}")
            return
        if event.type in {"gui_task_failed"}:
            await self._handle_step_failure(chain, step, self._summarize_event(event))
            return
        step.status = "done"
        step.finished_at = time.time()
        step.result = self._summarize_event(event)
        self._finish_step(chain, step)
        await self._verify_and_continue(chain, step)

    def _find_timed_out_step(self, chain: TaskChain) -> Optional[TaskStep]:
        now = time.time()
        for s in chain.steps:
            if s.status == "waiting" and s.started_at and now - s.started_at > self.step_timeout:
                return s
        return None

    def _finish_step(self, chain: TaskChain, step: TaskStep) -> None:
        chain.updated_at = time.time()
        if step.result:
            chain.notes.append(f"{step.id} {step.title}: {step.result[:900]}")
        self._update_progress(chain)
        self._emit("task_chain_step_completed", {"task_id": chain.id, "step": step.to_dict(), "progress_score": chain.progress_score})
        if all(s.status in {"done", "skipped"} for s in chain.steps):
            chain.status = "done"
            self._emit("task_chain_completed", chain.to_dict())
        elif any(s.status == "failed" and s.attempts >= s.max_attempts for s in chain.steps):
            chain.status = "failed"
        else:
            chain.status = "running" if chain.autonomy == "auto" else "planned"
        self._save_state()

    # ------------------------------------------------------------------
    # Formatting / helpers
    # ------------------------------------------------------------------
    def _snapshot_context(self, goal: str) -> Dict[str, Any]:
        context: Dict[str, Any] = {"goal": goal, "collected_at": time.time()}
        if not self.kernel:
            return context
        for name in ("self_model", "world_model", "emotion", "monologue", "system_monitor", "proactive"):
            mod = self.kernel.modules.get(name)
            if mod is not None and hasattr(mod, "to_dict"):
                try:
                    context[name] = mod.to_dict()
                except Exception:
                    pass
        return context

    def _select_chain(self, task_id: Any = None) -> Optional[TaskChain]:
        if task_id:
            return self.chains.get(str(task_id).strip())
        if not self.chains:
            return None
        active = [c for c in self.chains.values() if c.status not in {"done", "cancelled"}]
        pool = active or list(self.chains.values())
        return sorted(pool, key=lambda c: c.updated_at, reverse=True)[0]

    def _summarize_event(self, event: Event) -> str:
        data = event.data or {}
        if event.type == "memory_retrieved":
            chunks = data.get("items") or data.get("matches") or data.get("context") or []
            return f"Memory context retrieved ({len(chunks) if hasattr(chunks, '__len__') else 'some'} items)."
        if event.type == "screen_parsed":
            return str(data.get("summary") or data.get("text") or "Screen parsed.")[:1200]
        if event.type in {"web_search_completed", "web_learning_completed", "web_fetch_completed"}:
            return str(data.get("summary") or data.get("topic") or data.get("query") or "Web step completed.")[:1200]
        if event.type == "code_repair_proposal_ready":
            return f"Repair proposal {data.get('proposal_id')} status={data.get('status')} summary={data.get('summary', '')[:800]}"
        if event.type == "action_result":
            return str(data.get("summary") or data.get("stdout") or data.get("result") or data)[:1200]
        if event.type == "sleep_cycle_completed":
            return str(data.get("summary") or "Sleep/consolidation completed.")[:1200]
        if event.type.startswith("gui_task"):
            return str(data.get("summary") or data.get("result") or data.get("message") or data)[:1200]
        return str(data)[:1200]

    def _format_created(self, chain: TaskChain) -> str:
        lines = [f"V13 task chain {chain.id} created ({chain.autonomy} mode): {chain.goal}", "Strategies:"]
        for st in chain.strategies[:3]:
            lines.append(f"- {st.get('id')}: {st.get('name')} — {st.get('why')} [risk={st.get('risk')}]")
        lines.append("Plan:")
        for i, step in enumerate(chain.steps, start=1):
            lines.append(f"{i}. [{step.kind}/{step.strategy}] {step.title} (tries {step.max_attempts})")
        if chain.autonomy != "auto":
            lines.append(f"\nRun next step with: /task-step {chain.id}\nRetry failed step: /task-retry {chain.id} <step_id>\nFull report: /task-report {chain.id}")
        return "\n".join(lines)

    def _format_status(self, task_id: Any = None) -> str:
        chain = self._select_chain(task_id)
        if not chain:
            return "No task chains yet."
        lines = [f"V13 task chain {chain.id}: {chain.status} ({chain.autonomy}) progress={chain.progress_score:.0%}", f"Goal: {chain.goal}", f"Strategy: {chain.active_strategy}", "Steps:"]
        for s in chain.steps:
            marker = "→" if chain.steps.index(s) == chain.current_step and chain.status in {"running", "waiting"} else " "
            lines.append(f"{marker} {s.id} {s.status:8} [{s.kind}/{s.strategy}] {s.title} attempts={s.attempts}/{s.max_attempts}")
            if s.result:
                lines.append(f"    {s.result[:220]}")
        if chain.failure_log:
            lines.append(f"Last failure: {chain.failure_log[-1].get('reason')[:240]}")
        return "\n".join(lines)

    def _format_report(self, task_id: Any = None) -> str:
        chain = self._select_chain(task_id)
        if not chain:
            return "No task chain found for report."
        return self._make_report(chain)

    def _format_final(self, chain: TaskChain) -> str:
        return f"Task chain {chain.id} {chain.status}.\n" + self._make_report(chain)

    def _make_report(self, chain: TaskChain) -> str:
        done = [s for s in chain.steps if s.status == "done"]
        failed = [s for s in chain.steps if s.status == "failed"]
        waiting = [s for s in chain.steps if s.status == "waiting"]
        lines = [
            f"V13 task report: {chain.goal}",
            f"Status: {chain.status}; progress={chain.progress_score:.0%}; done={len(done)}/{len(chain.steps)}; failed={len(failed)}; waiting={len(waiting)}",
            "Strategies:",
        ]
        for st in chain.strategies[:3]:
            lines.append(f"- {st.get('id')}: {st.get('name')} — {st.get('why')} [risk={st.get('risk')}]")
        lines.append("Recent findings:")
        for note in chain.notes[-10:]:
            lines.append(f"- {note}")
        if chain.verification_log:
            last = chain.verification_log[-1]
            lines.append(f"Last verification: passed={last.get('passed')} — {last.get('reason')}")
        if chain.rollback_log:
            rb = chain.rollback_log[-1]
            lines.append(f"Rollback guidance: {rb.get('hint')}")
        if failed:
            lines.append("Next safe action: inspect failed step, use /task-retry, or switch to guided mode after adjusting safety/settings.")
        elif waiting:
            lines.append("Next safe action: approve/deny pending request or wait for external result.")
        else:
            lines.append("Next safe action: review results; approve any pending repair/write proposals manually.")
        return "\n".join(lines)

    def _update_progress(self, chain: TaskChain) -> None:
        if not chain.steps:
            chain.progress_score = 0.0
            return
        done_weight = sum(1.0 for s in chain.steps if s.status == "done")
        half_weight = sum(0.4 for s in chain.steps if s.status == "waiting")
        chain.progress_score = max(0.0, min(1.0, (done_weight + half_weight) / len(chain.steps)))

    def _respond(self, text: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="response_generated", data={"text": text, "source": "task_chains/v13"}, source_module=self.module_id), Priority.COGNITIVE)

    def _emit(self, type_: str, data: Dict[str, Any], priority: Priority = Priority.COGNITIVE) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type=type_, data=data, source_module=self.module_id), priority)

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            for item in data.get("chains", [])[-50:]:
                steps = [TaskStep(**self._clean_step_dict(s)) for s in item.get("steps", [])]
                chain = TaskChain(
                    id=item.get("id"), goal=item.get("goal", ""), status=item.get("status", "planned"),
                    autonomy=item.get("autonomy", "guided"), created_at=item.get("created_at", time.time()),
                    updated_at=item.get("updated_at", time.time()), current_step=item.get("current_step", 0),
                    steps=steps, context=item.get("context", {}), notes=item.get("notes", []),
                    strategies=item.get("strategies", []), active_strategy=item.get("active_strategy", "A"),
                    verification_log=item.get("verification_log", []), failure_log=item.get("failure_log", []),
                    rollback_log=item.get("rollback_log", []), progress_score=float(item.get("progress_score", 0.0)),
                )
                if chain.id:
                    self.chains[chain.id] = chain
        except Exception as exc:
            logger.warning("Could not load V13 task chain state: %s", exc)

    def _clean_step_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"id", "title", "kind", "payload", "status", "result", "started_at", "finished_at", "attempts", "max_attempts", "verifier", "rollback", "strategy"}
        out = {k: v for k, v in dict(data).items() if k in allowed}
        out.setdefault("attempts", 0); out.setdefault("max_attempts", self.max_retries_per_step + 1)
        out.setdefault("verifier", None); out.setdefault("rollback", None); out.setdefault("strategy", "A")
        return out

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            chains = sorted(self.chains.values(), key=lambda c: c.updated_at)[-50:]
            self._state_path.write_text(json.dumps({"version": "V13", "chains": [c.to_dict() for c in chains]}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save V13 task chain state: %s", exc)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "version": self.MODULE_VERSION,
            "auto_step_default": self.auto_step_default,
            "max_steps": self.max_steps,
            "max_retries_per_step": self.max_retries_per_step,
            "verifier_enabled": self.verifier_enabled,
            "rollback_enabled": self.rollback_enabled,
            "active_chains": len([c for c in self.chains.values() if c.status not in {"done", "cancelled"}]),
            "chains": [c.to_dict() for c in sorted(self.chains.values(), key=lambda c: c.updated_at, reverse=True)[:5]],
        })
        return base


def create_module() -> TaskChainModule:
    return TaskChainModule()
