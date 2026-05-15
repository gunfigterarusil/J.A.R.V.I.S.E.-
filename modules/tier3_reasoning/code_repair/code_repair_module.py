"""V9 Project Repair Agent — cognitive code repair loop.

This module turns requests such as "виправ помилки в проєкті" into a
multi-stage, auditable repair workflow. It is intentionally not a blind
"LLM writes files" bridge. The workflow mirrors the rest of the brain:

  perception/diagnostics -> memory retrieval -> self/world context -> planning
  -> LLM reasoning -> local validation -> safety review -> proposal -> apply

Actual file writes are delegated to the V7 action executor via action_request,
so sandbox/permission/audit checks always remain in control.
"""
from __future__ import annotations

import asyncio
import json
import logging
import py_compile
import re
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority
from core.llm_router import TaskType

logger = logging.getLogger("code_repair.v9")


class DiagnosticIssue:
    def __init__(self, path: str, type: str, line: int = 0, message: str = "", snippet: str = "") -> None:
        self.path = path
        self.type = type
        self.line = line
        self.message = message
        self.snippet = snippet

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "type": self.type, "line": self.line, "message": self.message, "snippet": self.snippet}


class RepairProposal:
    def __init__(
        self,
        proposal_id: str,
        request_id: str,
        target: str,
        status: str = "draft",
        summary: str = "",
        reasoning: str = "",
        changed_files: Optional[List[Dict[str, Any]]] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        created_at: Optional[float] = None,
        safety_notes: Optional[List[str]] = None,
    ) -> None:
        self.proposal_id = proposal_id
        self.request_id = request_id
        self.target = target
        self.status = status
        self.summary = summary
        self.reasoning = reasoning
        self.changed_files = changed_files or []
        self.diagnostics = diagnostics or {}
        self.created_at = time.time() if created_at is None else float(created_at)
        self.safety_notes = safety_notes or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "request_id": self.request_id,
            "target": self.target,
            "status": self.status,
            "summary": self.summary,
            "reasoning": self.reasoning,
            "changed_files": self.changed_files,
            "diagnostics": self.diagnostics,
            "created_at": self.created_at,
            "safety_notes": self.safety_notes,
        }


class CodeRepairModule(CognitiveModule):
    MODULE_DESCRIPTION = "V9 cognitive project repair agent with LLM planning and V7 safety-gated application"
    MODULE_VERSION = "0.9.0"

    def __init__(self) -> None:
        super().__init__(module_id="code_repair", cost={"cpu": 0.35, "gpu": 0.10, "ram": 0.12})
        self.enabled = True
        self.workspace = Path("~/jarvis_workspace").expanduser().resolve()
        self.max_files = 160
        self.max_file_chars = 18000
        self.auto_apply = False
        self.require_llm_for_patch = True
        self.proposals: Dict[str, RepairProposal] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._state_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "actions", None)
        self.workspace = Path(getattr(cfg, "workspace_path", "~/jarvis_workspace") or "~/jarvis_workspace").expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

        rcfg = getattr(kernel.config, "code_repair", None)
        ncfg = getattr(kernel.config, "natural_actions", None)
        self.enabled = bool(getattr(rcfg, "enabled", getattr(ncfg, "repair_agent_enabled", True)))
        self.max_files = int(getattr(rcfg, "max_files", 160))
        self.max_file_chars = int(getattr(rcfg, "max_file_chars", 18000))
        self.auto_apply = bool(getattr(rcfg, "auto_apply", False))
        self.require_llm_for_patch = bool(getattr(rcfg, "require_llm_for_patch", True))

        persistence_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        self._state_path = persistence_dir / "code_repair_v9" / "proposals.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "code_repair_requested",
                "code_repair_apply_requested",
                "memory_retrieved",
                "action_result",
            ],
        )
        self._stage("startup", "V9 repair agent ready", {"workspace": str(self.workspace), "enabled": self.enabled})

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        if event.type == "code_repair_requested":
            await self._start_repair(event)
        elif event.type == "memory_retrieved":
            await self._handle_memory(event)
        elif event.type == "code_repair_apply_requested":
            await self._apply_proposal(event)
        elif event.type == "action_result":
            await self._handle_action_result(event)

    # ------------------------------------------------------------------
    # Main workflow
    # ------------------------------------------------------------------
    async def _start_repair(self, event: Event) -> None:
        request_id = str(event.data.get("request_id") or f"repair_{int(time.time() * 1000)}")
        raw_path = str(event.data.get("path") or ".").strip()
        target = self._resolve(raw_path)
        if not self._inside_workspace(target):
            self._respond(f"V9 repair denied: target is outside workspace: {target}")
            return

        session = {
            "request_id": request_id,
            "parent_event_id": event._id,
            "target": target,
            "user_request": event.data.get("request_text") or event.data.get("text") or event.data.get("natural_language_request") or "",
            "started_at": time.time(),
            "memory": {},
            "self": {},
            "world": {},
            "diagnostics": {},
            "proposal": None,
        }
        self._sessions[request_id] = session

        self._stage("perception", "Scanning project files and errors", {"request_id": request_id, "target": self._display(target)})

        # Ask other cognitive modules for context. We also read cached snapshots directly below, but these
        # events keep the whole brain involved and refresh state for future turns.
        self._emit("memory_request", {
            "query_type": "dialogue_context",
            "query_text": f"code repair project errors fixes {session['user_request']} {self._display(target)}",
            "top_k": 8,
            "request_id": f"{request_id}:memory",
        }, Priority.COGNITIVE)
        self._emit("self_model_request", {"reason": "code_repair_v9", "request_id": request_id}, Priority.COGNITIVE)
        self._emit("world_model_request", {"reason": "code_repair_v9", "request_id": request_id}, Priority.COGNITIVE)
        self._emit("context_request", {"reason": "code_repair_v9", "request_id": request_id}, Priority.COGNITIVE)
        self._emit("thought_generated", {"text": f"Repair focus: inspect {self._display(target)} before proposing changes.", "source": self.module_id}, Priority.COGNITIVE)

        # Capture direct snapshots so the workflow does not depend on every module responding synchronously.
        session["self"] = self._module_snapshot("self_model")
        session["world"] = self._module_snapshot("world_model")
        session["emotion"] = self._module_snapshot("emotion")
        session["monologue"] = self._module_snapshot("monologue")

        diagnostics = await asyncio.to_thread(self._diagnose_project, target)
        session["diagnostics"] = diagnostics
        self._emit("code_repair_diagnostic", diagnostics, Priority.COGNITIVE)
        self._stage("planning", "Diagnostics complete; building repair plan", {"request_id": request_id, "issues": len(diagnostics.get("issues", []))})

        proposal = await self._build_proposal(session)
        session["proposal"] = proposal
        self.proposals[proposal.proposal_id] = proposal
        self._save_state()

        self._emit("code_repair_proposal_ready", proposal.to_dict(), Priority.COGNITIVE)
        self._respond(self._format_proposal(proposal))

        if self.auto_apply and proposal.status == "ready":
            self._respond("CODE_REPAIR_AUTO_APPLY=true is enabled. Applying proposal through V7 safety gate.")
            await self._apply_proposal(Event(type="code_repair_apply_requested", data={"proposal_id": proposal.proposal_id}, source_module=self.module_id))

    async def _handle_memory(self, event: Event) -> None:
        request_id = str(event.data.get("request_id", ""))
        if not request_id.endswith(":memory"):
            return
        base_id = request_id.split(":", 1)[0]
        session = self._sessions.get(base_id)
        if session is not None:
            session["memory"] = dict(event.data or {})
            self._stage("memory", "Relevant memory retrieved for repair", {"request_id": base_id})

    async def _build_proposal(self, session: Dict[str, Any]) -> RepairProposal:
        diagnostics = session["diagnostics"]
        request_id = session["request_id"]
        target = session["target"]
        proposal_id = f"rp{int(time.time() * 1000)}"
        issues = diagnostics.get("issues", [])

        if not issues:
            return RepairProposal(
                proposal_id=proposal_id,
                request_id=request_id,
                target=self._display(target),
                status="plan_only",
                summary="No compile-breaking Python errors were found. I created a maintenance plan instead of editing files.",
                reasoning=self._build_no_issue_plan(diagnostics),
                diagnostics=diagnostics,
                safety_notes=["No file writes proposed because no concrete compile error was detected."],
            )

        self._stage("llm_reasoning", "Asking LLM how to repair the highest-confidence issue", {"request_id": request_id})
        candidate_files = self._load_candidate_files(target, issues)
        llm_result = await self._ask_llm_for_patch(session, candidate_files)
        changed_files = llm_result.get("changed_files") or []
        reasoning = llm_result.get("reasoning") or llm_result.get("raw") or ""
        summary = llm_result.get("summary") or "Generated repair proposal."

        validated_files: List[Dict[str, Any]] = []
        for item in changed_files:
            rel = str(item.get("path") or "").strip()
            content = item.get("content")
            if not rel or content is None:
                continue
            resolved = self._resolve(rel)
            if not self._inside_workspace(resolved):
                continue
            validation = self._validate_file_content(resolved, str(content))
            item = {"path": self._display(resolved), "content": str(content), "reason": str(item.get("reason", "")), "validation": validation}
            validated_files.append(item)

        if not validated_files:
            return RepairProposal(
                proposal_id=proposal_id,
                request_id=request_id,
                target=self._display(target),
                status="plan_only",
                summary="Diagnostics found issues, but no safe validated patch was generated. LLM reasoning is available as a repair plan.",
                reasoning=reasoning or self._fallback_reasoning(diagnostics),
                diagnostics=diagnostics,
                safety_notes=["No file writes proposed because generated patch was empty or failed validation."],
            )

        all_valid = all((f.get("validation") or {}).get("ok") for f in validated_files)
        status = "ready" if all_valid else "plan_only"
        notes = [
            "Patch application is delegated to V7 action_request/write_file.",
            "Raise safety to L4 and approve pending write actions if requested.",
        ]
        if not all_valid:
            notes.append("One or more changed files did not validate cleanly; proposal is plan-only.")

        return RepairProposal(
            proposal_id=proposal_id,
            request_id=request_id,
            target=self._display(target),
            status=status,
            summary=summary,
            reasoning=reasoning,
            changed_files=validated_files,
            diagnostics=diagnostics,
            safety_notes=notes,
        )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def _diagnose_project(self, target: Path) -> Dict[str, Any]:
        py_files = self._collect_python_files(target)
        issues: List[DiagnosticIssue] = []
        markers: List[Dict[str, Any]] = []
        for p in py_files:
            compile_issue = self._compile_file(p)
            if compile_issue:
                issues.append(compile_issue)
            markers.extend(self._scan_markers(p))
            if len(issues) >= 30:
                break
        result = {
            "ok": len(issues) == 0,
            "target": self._display(target),
            "python_files": len(py_files),
            "issues": [x.to_dict() for x in issues],
            "markers": markers[:40],
            "timestamp": time.time(),
            "repair_model": "V9 cognitive repair",
        }
        return result

    def _collect_python_files(self, target: Path) -> List[Path]:
        ignore = {".venv", "venv", "__pycache__", ".git", "dist", "build", ".mypy_cache", ".pytest_cache"}
        files: List[Path] = []
        if target.is_file() and target.suffix == ".py":
            return [target]
        if target.is_dir():
            for p in target.rglob("*.py"):
                if any(part in ignore for part in p.parts):
                    continue
                files.append(p)
                if len(files) >= self.max_files:
                    break
        return files

    def _compile_file(self, p: Path) -> Optional[DiagnosticIssue]:
        try:
            py_compile.compile(str(p), doraise=True)
            return None
        except py_compile.PyCompileError as exc:
            msg = str(exc)
            line = 0
            m = re.search(r"line (\d+)", msg)
            if m:
                line = int(m.group(1))
            return DiagnosticIssue(path=self._display(p), type="compile_error", line=line, message=msg[-1600:], snippet=self._snippet(p, line))
        except Exception as exc:
            return DiagnosticIssue(path=self._display(p), type=type(exc).__name__, message=str(exc), snippet="")

    def _scan_markers(self, p: Path) -> List[Dict[str, Any]]:
        markers = ["fixme", "todo fix", "traceback", "modulenotfounderror", "importerror", "syntaxerror", "exception", "xxx"]
        out: List[Dict[str, Any]] = []
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return out
        low = txt.lower()
        for marker in markers:
            start = 0
            while True:
                idx = low.find(marker, start)
                if idx < 0:
                    break
                line = txt[:idx].count("\n") + 1
                out.append({"path": self._display(p), "marker": marker, "line": line, "snippet": txt[max(0, idx-100):idx+220].replace("\n", " ")})
                if len(out) >= 3:
                    return out
                start = idx + len(marker)
        return out

    def _snippet(self, p: Path, line: int, radius: int = 3) -> str:
        if line <= 0:
            return ""
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return ""
        start = max(1, line - radius)
        end = min(len(lines), line + radius)
        rows = []
        for n in range(start, end + 1):
            prefix = ">" if n == line else " "
            rows.append(f"{prefix}{n}: {lines[n-1]}")
        return "\n".join(rows)

    def _load_candidate_files(self, target: Path, issues: List[Dict[str, Any]]) -> Dict[str, str]:
        paths: List[Path] = []
        for issue in issues[:6]:
            rel = issue.get("path")
            if rel:
                p = self._resolve(str(rel))
                if p.is_file() and p not in paths:
                    paths.append(p)
        if not paths and target.is_file():
            paths.append(target)
        data: Dict[str, str] = {}
        for p in paths[:4]:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            data[self._display(p)] = txt[:self.max_file_chars]
        return data

    # ------------------------------------------------------------------
    # LLM repair reasoning
    # ------------------------------------------------------------------
    async def _ask_llm_for_patch(self, session: Dict[str, Any], candidate_files: Dict[str, str]) -> Dict[str, Any]:
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router is None:
            return {"summary": "No LLM router available.", "reasoning": self._fallback_reasoning(session["diagnostics"]), "changed_files": []}
        system = (
            "You are the repair cortex inside a modular Jarvis-like assistant. "
            "You do not execute actions directly. You analyze diagnostics and propose minimal safe file changes. "
            "Return ONLY valid JSON. No Markdown. No commentary outside JSON."
        )
        prompt = self._build_repair_prompt(session, candidate_files)
        try:
            raw = await router.generate(prompt, task_type=TaskType.CODE_REPAIR, system=system, temperature=0.2, max_tokens=4096)
        except Exception as exc:
            return {"summary": f"LLM error: {exc}", "reasoning": self._fallback_reasoning(session["diagnostics"]), "changed_files": []}
        parsed = self._parse_llm_json(raw)
        if not parsed:
            return {"summary": "LLM returned non-JSON repair reasoning.", "reasoning": raw[:4000], "raw": raw, "changed_files": []}
        return parsed

    def _build_repair_prompt(self, session: Dict[str, Any], candidate_files: Dict[str, str]) -> str:
        diagnostics = session["diagnostics"]
        ctx = {
            "user_request": session.get("user_request", ""),
            "target": self._display(session["target"]),
            "diagnostics": diagnostics,
            "memory_context": self._compact(session.get("memory", {}), 2500),
            "self_model": self._compact(session.get("self", {}), 1800),
            "world_model": self._compact(session.get("world", {}), 1800),
            "emotion_state": self._compact(session.get("emotion", {}), 800),
            "monologue_state": self._compact(session.get("monologue", {}), 800),
            "candidate_files": candidate_files,
        }
        schema = {
            "summary": "short human-readable repair summary",
            "reasoning": "why this fix is correct and minimal",
            "changed_files": [
                {"path": "relative/path.py", "reason": "why changed", "content": "FULL corrected file content"}
            ],
            "tests_to_run": ["python -m compileall -q ."],
            "confidence": 0.0,
        }
        return (
            "Analyze this Python project repair request. Use all context, but make the smallest safe fix.\n"
            "Important constraints:\n"
            "- Only propose changes for files included in candidate_files.\n"
            "- Return FULL corrected file content for each changed file.\n"
            "- If there is not enough evidence, return changed_files as [] and provide a plan.\n"
            "- Do not invent files. Do not remove unrelated features.\n"
            f"Required JSON schema example: {json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Repair context JSON:\n{json.dumps(ctx, ensure_ascii=False, default=str)[:26000]}"
        )

    def _parse_llm_json(self, raw: str) -> Optional[Dict[str, Any]]:
        text = (raw or "").strip()
        if text.startswith("[NullProvider]"):
            return None
        # Strip common fenced block wrappers if a provider ignores the instruction.
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None

    def _validate_file_content(self, original_path: Path, content: str) -> Dict[str, Any]:
        if original_path.suffix != ".py":
            return {"ok": True, "note": "non-python file; syntax validation skipped"}
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / original_path.name
            tmp.write_text(content, encoding="utf-8")
            try:
                py_compile.compile(str(tmp), doraise=True)
                return {"ok": True, "check": "py_compile"}
            except py_compile.PyCompileError as exc:
                return {"ok": False, "check": "py_compile", "error": str(exc)[-1200:]}
            except Exception as exc:
                return {"ok": False, "check": "py_compile", "error": str(exc)}

    # ------------------------------------------------------------------
    # Apply workflow
    # ------------------------------------------------------------------
    async def _apply_proposal(self, event: Event) -> None:
        proposal_id = str(event.data.get("proposal_id") or event.data.get("id") or "").strip()
        if not proposal_id:
            # Use latest ready proposal as a convenience.
            ready = [p for p in self.proposals.values() if p.status == "ready"]
            ready.sort(key=lambda p: p.created_at, reverse=True)
            proposal = ready[0] if ready else None
        else:
            proposal = self.proposals.get(proposal_id)
        if proposal is None:
            self._respond("No ready repair proposal found. Say `виправ помилки в .` first, then `застосуй ремонт <proposal_id>`.")
            return
        if proposal.status != "ready":
            self._respond(f"Proposal {proposal.proposal_id} is not apply-ready; status={proposal.status}. Reasoning:\n{proposal.reasoning[:1200]}")
            return
        if not proposal.changed_files:
            self._respond(f"Proposal {proposal.proposal_id} has no changed files.")
            return

        self._stage("safety_review", "Submitting repair writes to V7 safety layer", {"proposal_id": proposal.proposal_id, "files": [f.get("path") for f in proposal.changed_files]})
        self._respond(
            f"Applying proposal {proposal.proposal_id} through V7 safety. If writes are denied, set safety to L4. If confirmation is requested, approve the pending id."
        )
        for item in proposal.changed_files:
            path = str(item.get("path"))
            content = str(item.get("content", ""))
            self._emit_action("write_file", {"path": path, "content": content, "request_id": f"{proposal.proposal_id}:{path}", "repair_proposal_id": proposal.proposal_id})
        proposal.status = "applied"
        self._save_state()

    async def _handle_action_result(self, event: Event) -> None:
        rid = str(event.data.get("request_id", ""))
        if not rid.startswith("rp"):
            return
        self._emit("code_repair_apply_result", dict(event.data), Priority.COGNITIVE)

    def _emit_action(self, action_type: str, payload: Dict[str, Any]) -> None:
        if not self.kernel:
            return
        top_path = payload.get("path") or payload.get("cwd")
        resolved_path = None
        if top_path:
            p = self._resolve(str(top_path))
            resolved_path = str(p)
        self.kernel.event_bus.emit(
            Event(
                type="action_request",
                data={
                    "action_type": action_type,
                    "payload": payload,
                    "path": resolved_path,
                    "request_id": payload.get("request_id"),
                    "respond": True,
                    "source_workflow": "code_repair_v9",
                    "autonomous_chain": False,
                },
                source_module=self.module_id,
            ),
            Priority.REALTIME,
        )

    # ------------------------------------------------------------------
    # Formatting / helpers
    # ------------------------------------------------------------------
    def _format_proposal(self, proposal: RepairProposal) -> str:
        diag = proposal.diagnostics or {}
        issue_count = len(diag.get("issues", []))
        marker_count = len(diag.get("markers", []))
        lines = [
            f"V9 repair proposal `{proposal.proposal_id}` is {proposal.status}.",
            f"Target: {proposal.target}",
            f"Diagnostics: {diag.get('python_files', 0)} Python file(s), {issue_count} compile issue(s), {marker_count} marker(s).",
            f"Summary: {proposal.summary}",
        ]
        if proposal.changed_files:
            lines.append("Proposed changed files:")
            for f in proposal.changed_files:
                v = f.get("validation", {})
                lines.append(f"- {f.get('path')} — validation ok={v.get('ok')} — {f.get('reason', '')[:180]}")
            lines.append(f"To apply: say `застосуй ремонт {proposal.proposal_id}` or `apply repair {proposal.proposal_id}`.")
        else:
            lines.append("No direct patch was generated. Repair reasoning/plan:")
            lines.append(proposal.reasoning[:1800])
        if proposal.safety_notes:
            lines.append("Safety notes: " + "; ".join(proposal.safety_notes))
        return "\n".join(lines)

    def _fallback_reasoning(self, diagnostics: Dict[str, Any]) -> str:
        issues = diagnostics.get("issues", [])
        if not issues:
            return "No compile errors found. Run tests or provide the exact error/log to enable targeted repair."
        rows = []
        for issue in issues[:5]:
            rows.append(f"- {issue.get('path')}:{issue.get('line')} {issue.get('type')}: {issue.get('message', '')[:500]}")
        return "Detected compile issues. Read the listed files, fix the line-level syntax/import problem, then run compileall again.\n" + "\n".join(rows)

    def _build_no_issue_plan(self, diagnostics: Dict[str, Any]) -> str:
        markers = diagnostics.get("markers", [])[:8]
        if not markers:
            return "No compile errors or obvious error markers were detected. For deeper repair, provide a traceback, failing test output, or allow running tests."
        rows = ["No compile errors, but I found possible markers to inspect:"]
        for m in markers:
            rows.append(f"- {m.get('path')}:{m.get('line')} marker={m.get('marker')} — {m.get('snippet','')[:220]}")
        return "\n".join(rows)

    def _stage(self, stage: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = {"stage": stage, "message": message, "timestamp": time.time(), **(data or {})}
        self._emit("code_repair_stage", payload, Priority.COGNITIVE)
        self._emit("thought_generated", {"text": f"[code_repair:{stage}] {message}", "source": self.module_id, **(data or {})}, Priority.COGNITIVE)

    def _emit(self, event_type: str, data: Dict[str, Any], priority: Priority = Priority.COGNITIVE) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type=event_type, data=data, source_module=self.module_id), priority)

    def _respond(self, text: str) -> None:
        self._emit("response_generated", {"text": text, "source": "code_repair/v9", "importance": 0.75}, Priority.COGNITIVE)

    def _module_snapshot(self, module_id: str) -> Dict[str, Any]:
        try:
            mod = self.kernel.modules.get(module_id) if self.kernel else None
            if mod and hasattr(mod, "to_dict"):
                return mod.to_dict()
        except Exception:
            pass
        return {}

    def _resolve(self, raw: str) -> Path:
        p = Path(raw or ".").expanduser()
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()

    def _inside_workspace(self, p: Path) -> bool:
        try:
            p.resolve().relative_to(self.workspace)
            return True
        except Exception:
            return p.resolve() == self.workspace

    def _display(self, p: Path) -> str:
        try:
            rel = str(p.resolve().relative_to(self.workspace))
            return rel or "."
        except Exception:
            return str(p)

    def _compact(self, value: Any, limit: int) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
        return text[:limit]

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            data = {pid: prop.to_dict() for pid, prop in self.proposals.items()}
            self._state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save repair state: %s", exc)

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            for pid, item in raw.items():
                self.proposals[pid] = RepairProposal(**item)
        except Exception as exc:
            logger.warning("Could not load repair state: %s", exc)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "workspace": str(self.workspace),
            "max_files": self.max_files,
            "max_file_chars": self.max_file_chars,
            "auto_apply": self.auto_apply,
            "proposal_count": len(self.proposals),
            "latest_proposals": [p.to_dict() for p in sorted(self.proposals.values(), key=lambda x: x.created_at, reverse=True)[:5]],
            "workflow": ["perception", "memory", "self/world", "planning", "llm_reasoning", "validation", "safety", "proposal", "apply"],
        })
        return base


def create_module() -> CodeRepairModule:
    return CodeRepairModule()
