"""V9.4 Autonomous Task Chains.

Turns a broad request such as "розберися з цією задачею" into a safe,
auditable chain of steps. The module does not bypass the rest of the brain:

  user request -> task chain -> memory/self/world context -> planner/LLM
  -> step events/actions -> safety/executor -> observations -> next step/report

The default mode is controlled autonomy: it can plan and execute low-risk
steps, but file writes, shell commands and repair application still go through
V7 safety gates and approval when required.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority
from core.llm_router import TaskType

logger = logging.getLogger("task_chains.v9_4")


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
    ) -> None:
        self.id = id
        self.title = title
        self.kind = kind
        self.payload = payload or {}
        self.status = status
        self.result = result
        self.started_at = started_at
        self.finished_at = finished_at

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
            "notes": self.notes[-20:],
        }


class TaskChainModule(CognitiveModule):
    MODULE_DESCRIPTION = "V9.4 controlled autonomous task chains with memory/planner/LLM/safety integration"
    MODULE_VERSION = "0.4.0"

    def __init__(self) -> None:
        super().__init__(module_id="task_chains", cost={"cpu": 0.22, "gpu": 0.08, "ram": 0.10})
        self.enabled = True
        self.auto_step_default = False
        self.max_steps = 8
        self.step_timeout = 90.0
        self.chains: Dict[str, TaskChain] = {}
        self._waiting: Dict[str, Dict[str, Any]] = {}
        self._state_path: Optional[Path] = None

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "task_chains", None)
        self.enabled = bool(getattr(cfg, "enabled", True))
        self.auto_step_default = bool(getattr(cfg, "auto_step_default", False))
        self.max_steps = int(getattr(cfg, "max_steps", 8))
        self.step_timeout = float(getattr(cfg, "step_timeout_seconds", 90.0))

        persistence_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        self._state_path = persistence_dir / "task_chains_v9_4.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "task_chain_requested",
                "task_chain_status_requested",
                "task_chain_step_requested",
                "task_chain_cancel_requested",
                "task_chain_resume_requested",
                "memory_retrieved",
                "screen_parsed",
                "web_search_completed",
                "web_learning_completed",
                "web_fetch_completed",
                "code_repair_proposal_ready",
                "code_repair_diagnostic",
                "action_result",
                "action_denied",
                "action_pending_confirmation",
                "sleep_cycle_completed",
                "response_generated",
            ],
        )
        self._emit("task_chain_module_ready", {"enabled": self.enabled, "auto_default": self.auto_step_default})

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        if event.type == "task_chain_requested":
            await self._start_chain(event)
        elif event.type == "task_chain_status_requested":
            self._respond(self._format_status(event.data.get("task_id")))
        elif event.type == "task_chain_step_requested":
            await self._run_next(event.data.get("task_id"), manual=True)
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

        self._emit("memory_request", {
            "query_type": "dialogue_context",
            "query_text": f"task chain plan context: {goal}",
            "top_k": 8,
            "request_id": f"{task_id}:memory",
        })
        self._emit("self_model_request", {"reason": "task_chain_v9_4", "request_id": task_id})
        self._emit("world_model_request", {"reason": "task_chain_v9_4", "request_id": task_id})
        self._emit("thought_generated", {"text": f"Task chain created: {goal}", "source": self.module_id})

        steps = await self._make_plan(goal, chain.context)
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

    async def _run_next(self, task_id: Any = None, manual: bool = False) -> None:
        chain = self._select_chain(task_id)
        if not chain:
            self._respond("No task chain found. Start one with /task <goal> or say 'розберися з ...'.")
            return
        if chain.status in {"done", "failed", "cancelled"}:
            self._respond(f"Task chain {chain.id} is already {chain.status}.")
            return

        next_index = None
        for i, step in enumerate(chain.steps):
            if step.status in {"pending", "failed"}:
                next_index = i
                break
        if next_index is None:
            chain.status = "done"
            chain.updated_at = time.time()
            self._save_state()
            self._emit("task_chain_completed", chain.to_dict())
            self._respond(self._format_final(chain))
            return

        chain.current_step = next_index
        step = chain.steps[next_index]
        step.status = "running"
        step.started_at = time.time()
        chain.status = "running"
        chain.updated_at = time.time()
        self._save_state()
        self._emit("task_chain_step_started", {"task_id": chain.id, "step": step.to_dict()})
        await self._execute_step(chain, step)

        # Synchronous/instant steps mark themselves done. Waiting steps continue after observation events.
        if step.status == "done" and chain.autonomy == "auto":
            await self._run_next(chain.id, manual=False)
        elif step.status == "done":
            self._respond(f"Step done: {step.title}\nNext: use /task-step {chain.id} or say 'продовжуй задачу'.")

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    async def _make_plan(self, goal: str, context: Dict[str, Any]) -> List[TaskStep]:
        # Ask planner/LLM, but always constrain output to known safe step kinds.
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router:
            prompt = (
                "Create a short safe task chain for this local assistant. Return JSON only: "
                "[{\"title\":\"...\",\"kind\":\"think|memory|screen|web_search|web_learn|repair|action|sleep|report\",\"payload\":{...}}].\n"
                "Use action only for list_files/read_file/search_files/create_dir/write_file/run_command payloads. "
                "Risky actions will still require safety approval. Prefer diagnostics before writes.\n\n"
                f"GOAL: {goal}\n"
                f"KNOWN CONTEXT: {json.dumps(context, ensure_ascii=False)[:2500]}"
            )
            try:
                raw = await router.generate(prompt, task_type=TaskType.ACTION_PLANNING, system="You are JAV task planner. Return compact JSON only.")
                parsed = self._parse_llm_steps(raw)
                if parsed:
                    return parsed[: self.max_steps]
            except Exception as exc:
                logger.warning("LLM task planning failed: %s", exc)
        return self._fallback_plan(goal)

    def _parse_llm_steps(self, raw: str) -> List[TaskStep]:
        raw = raw.strip()
        m = re.search(r"\[[\s\S]*\]", raw)
        if m:
            raw = m.group(0)
        try:
            items = json.loads(raw)
        except Exception:
            return []
        steps: List[TaskStep] = []
        allowed = {"think", "memory", "screen", "web_search", "web_learn", "repair", "action", "sleep", "report"}
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "think").strip()
            if kind not in allowed:
                kind = "think"
            title = str(item.get("title") or f"Step {i}").strip()
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            steps.append(TaskStep(id=f"s{i}", title=title, kind=kind, payload=payload))
        return steps

    def _fallback_plan(self, goal: str) -> List[TaskStep]:
        lower = goal.lower()
        steps: List[TaskStep] = [TaskStep(id="s1", title="Recall relevant context from long-term memory", kind="memory", payload={"query": goal})]
        if any(x in lower for x in ["екран", "screen", "що тут", "помилка на екрані"]):
            steps.append(TaskStep(id="s2", title="Read the current screen", kind="screen"))
        if any(x in lower for x in ["інтернет", "web", "вивчи", "досліди", "пошукай"]):
            steps.append(TaskStep(id="s3", title="Research the topic on the web", kind="web_learn", payload={"topic": goal}))
        if any(x in lower for x in ["виправ", "помил", "bug", "error", "код", "project", "проєкт", "проект"]):
            target = "."
            matches = re.findall(r"(?:\s|^)(?:в|у|in)\s+([^,.!?]+)", goal, flags=re.IGNORECASE)
            if matches:
                target = matches[-1].strip().strip('"\'') or "."
            steps.append(TaskStep(id="s4", title=f"Run V9 project repair diagnostics for {target}", kind="repair", payload={"path": target}))
        if len(steps) == 1:
            steps.append(TaskStep(id="s2", title="Analyze the goal and make a practical answer", kind="think"))
        steps.append(TaskStep(id=f"s{len(steps)+1}", title="Consolidate useful findings", kind="sleep"))
        steps.append(TaskStep(id=f"s{len(steps)+1}", title="Report result and next safe action", kind="report"))
        # Re-number stable IDs.
        for i, step in enumerate(steps, start=1):
            step.id = f"s{i}"
        return steps[: self.max_steps]

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------
    async def _execute_step(self, chain: TaskChain, step: TaskStep) -> None:
        try:
            if step.kind == "memory":
                query = step.payload.get("query") or chain.goal
                self._wait_for(chain, step, "memory_retrieved", request_id=f"{chain.id}:{step.id}:memory")
                self._emit("memory_request", {"query_type": "dialogue_context", "query_text": query, "top_k": 8, "request_id": f"{chain.id}:{step.id}:memory"})
                return
            if step.kind == "screen":
                self._wait_for(chain, step, "screen_parsed", request_id=f"{chain.id}:{step.id}:screen")
                self._emit("screen_capture_requested", {"request_id": f"{chain.id}:{step.id}:screen", "reason": "task_chain", "respond": False}, Priority.REALTIME)
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
            if step.kind == "action":
                action_type = str(step.payload.get("action_type") or step.payload.get("type") or "").strip()
                payload = step.payload.get("payload") if isinstance(step.payload.get("payload"), dict) else dict(step.payload)
                payload.pop("action_type", None); payload.pop("type", None)
                if not action_type:
                    step.status = "failed"; step.result = "No action_type in step payload."; self._finish_step(chain, step); return
                request_id = f"{chain.id}:{step.id}:action"
                payload["request_id"] = request_id
                self._wait_for(chain, step, "action_result", request_id=request_id)
                self._emit_action(action_type, payload, chain, step)
                return
            if step.kind == "sleep":
                self._wait_for(chain, step, "sleep_cycle_completed", request_id=f"{chain.id}:{step.id}:sleep")
                self._emit("sleep_cycle_requested", {"reason": "task_chain", "request_id": f"{chain.id}:{step.id}:sleep", "force": True, "respond": False})
                return
            if step.kind == "report":
                step.result = self._make_report(chain)
                step.status = "done"; step.finished_at = time.time(); self._finish_step(chain, step); self._respond(step.result); return
            # think fallback.
            step.result = await self._think(chain, step)
            step.status = "done"; step.finished_at = time.time(); self._finish_step(chain, step)
        except Exception as exc:
            step.status = "failed"
            step.result = f"Step failed: {exc}"
            self._finish_step(chain, step)

    async def _think(self, chain: TaskChain, step: TaskStep) -> str:
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router:
            prompt = f"Task goal: {chain.goal}\nCurrent step: {step.title}\nKnown notes: {chain.notes[-8:]}\nGive a concise next insight/action."
            try:
                return await router.generate(prompt, task_type=TaskType.COMPLEX_REASONING, system="You are JAV internal task-chain reasoning cortex.")
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
            data={"action_type": action_type, "payload": payload, "path": resolved_path, "request_id": payload.get("request_id"), "respond": False, "task_chain_id": chain.id},
            source_module=self.module_id,
        ), Priority.REALTIME)

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
        # Match by explicit request_id when available, otherwise by event type and a recent waiting step.
        request_id = str(event.data.get("request_id") or "")
        candidates: List[str] = []
        if request_id and request_id in self._waiting:
            candidates.append(request_id)
        for key, wait in list(self._waiting.items()):
            if wait.get("event_type") == event.type and key not in candidates:
                # For broad completion events without request_id, take the oldest compatible wait.
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
        step.status = "done"
        step.finished_at = time.time()
        step.result = self._summarize_event(event)
        self._finish_step(chain, step)
        if chain.autonomy == "auto" and chain.status not in {"failed", "cancelled", "done"}:
            await self._run_next(chain.id, manual=False)
        elif chain.status not in {"done", "failed", "cancelled"}:
            self._respond(f"Task chain {chain.id}: step {step.id} done — {step.title}\nResult: {step.result}\nNext: /task-step {chain.id}")

    def _finish_step(self, chain: TaskChain, step: TaskStep) -> None:
        chain.updated_at = time.time()
        if step.result:
            chain.notes.append(f"{step.id} {step.title}: {step.result[:700]}")
        self._emit("task_chain_step_completed", {"task_id": chain.id, "step": step.to_dict()})
        if all(s.status in {"done", "skipped"} for s in chain.steps):
            chain.status = "done"
            self._emit("task_chain_completed", chain.to_dict())
        elif any(s.status == "failed" for s in chain.steps):
            chain.status = "failed"
        else:
            chain.status = "running" if chain.autonomy == "auto" else "planned"
        self._save_state()

    # ------------------------------------------------------------------
    # Formatting / helpers
    # ------------------------------------------------------------------
    def _snapshot_context(self, goal: str) -> Dict[str, Any]:
        context: Dict[str, Any] = {"goal": goal}
        if not self.kernel:
            return context
        for name in ("self_model", "world_model", "emotion", "monologue"):
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
        # Prefer active recent chains.
        active = [c for c in self.chains.values() if c.status not in {"done", "cancelled"}]
        pool = active or list(self.chains.values())
        return sorted(pool, key=lambda c: c.updated_at, reverse=True)[0]

    def _summarize_event(self, event: Event) -> str:
        data = event.data or {}
        if event.type == "memory_retrieved":
            chunks = data.get("items") or data.get("matches") or data.get("context") or []
            return f"Memory context retrieved ({len(chunks) if hasattr(chunks, '__len__') else 'some'} items)."
        if event.type == "screen_parsed":
            return str(data.get("summary") or data.get("text") or "Screen parsed.")[:900]
        if event.type in {"web_search_completed", "web_learning_completed", "web_fetch_completed"}:
            return str(data.get("summary") or data.get("topic") or data.get("query") or "Web step completed.")[:900]
        if event.type == "code_repair_proposal_ready":
            return f"Repair proposal {data.get('proposal_id')} status={data.get('status')} summary={data.get('summary', '')[:500]}"
        if event.type == "action_result":
            return str(data.get("summary") or data.get("stdout") or data.get("result") or data)[:900]
        if event.type == "sleep_cycle_completed":
            return str(data.get("summary") or "Sleep/consolidation completed.")[:900]
        return str(data)[:900]

    def _format_created(self, chain: TaskChain) -> str:
        lines = [f"Task chain {chain.id} created ({chain.autonomy} mode): {chain.goal}", "Plan:"]
        for i, step in enumerate(chain.steps, start=1):
            lines.append(f"{i}. [{step.kind}] {step.title}")
        if chain.autonomy != "auto":
            lines.append(f"\nRun next step with: /task-step {chain.id}\nOr say: продовжуй задачу")
        return "\n".join(lines)

    def _format_status(self, task_id: Any = None) -> str:
        chain = self._select_chain(task_id)
        if not chain:
            return "No task chains yet."
        lines = [f"Task chain {chain.id}: {chain.status} ({chain.autonomy})", f"Goal: {chain.goal}", "Steps:"]
        for s in chain.steps:
            marker = "→" if chain.steps.index(s) == chain.current_step and chain.status in {"running", "waiting"} else " "
            lines.append(f"{marker} {s.id} {s.status:8} [{s.kind}] {s.title}")
            if s.result:
                lines.append(f"    {s.result[:180]}")
        return "\n".join(lines)

    def _format_final(self, chain: TaskChain) -> str:
        return f"Task chain {chain.id} completed.\n" + self._make_report(chain)

    def _make_report(self, chain: TaskChain) -> str:
        done = [s for s in chain.steps if s.status == "done"]
        failed = [s for s in chain.steps if s.status == "failed"]
        lines = [f"Task report: {chain.goal}", f"Done steps: {len(done)}/{len(chain.steps)}; failed: {len(failed)}"]
        for note in chain.notes[-8:]:
            lines.append(f"- {note}")
        if failed:
            lines.append("Next safe action: review failed step and rerun manually after adjusting safety/settings.")
        else:
            lines.append("Next safe action: review results; approve any pending repair/write proposals manually.")
        return "\n".join(lines)

    def _respond(self, text: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="response_generated", data={"text": text, "source": "task_chains/v9.4"}, source_module=self.module_id), Priority.COGNITIVE)

    def _emit(self, type_: str, data: Dict[str, Any], priority: Priority = Priority.COGNITIVE) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type=type_, data=data, source_module=self.module_id), priority)

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            for item in data.get("chains", [])[-30:]:
                steps = [TaskStep(**s) for s in item.get("steps", [])]
                chain = TaskChain(
                    id=item.get("id"), goal=item.get("goal", ""), status=item.get("status", "planned"),
                    autonomy=item.get("autonomy", "guided"), created_at=item.get("created_at", time.time()),
                    updated_at=item.get("updated_at", time.time()), current_step=item.get("current_step", 0),
                    steps=steps, context=item.get("context", {}), notes=item.get("notes", []),
                )
                if chain.id:
                    self.chains[chain.id] = chain
        except Exception as exc:
            logger.warning("Could not load task chain state: %s", exc)

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            chains = sorted(self.chains.values(), key=lambda c: c.updated_at)[-30:]
            self._state_path.write_text(json.dumps({"chains": [c.to_dict() for c in chains]}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save task chain state: %s", exc)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "auto_step_default": self.auto_step_default,
            "max_steps": self.max_steps,
            "active_chains": len([c for c in self.chains.values() if c.status not in {"done", "cancelled"}]),
            "chains": [c.to_dict() for c in sorted(self.chains.values(), key=lambda c: c.updated_at, reverse=True)[:5]],
        })
        return base


def create_module() -> TaskChainModule:
    return TaskChainModule()
