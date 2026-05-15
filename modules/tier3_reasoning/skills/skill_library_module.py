"""V14 Skill Learning + Knowledge Graph.

This module gives JAV a procedural skill library and a lightweight knowledge
graph. It does not fine-tune an LLM; it learns by turning successful actions,
web-learning results, repair/task reports and manual instructions into reusable
procedures and linked facts.

Flow:
  task/web/repair/action result -> skill candidate -> skill_library
  sourced semantic memory -> knowledge graph triple
  user asks for skill/knowledge -> relevant skills/facts -> response
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _slug(text: str, fallback: str = "skill") -> str:
    base = re.sub(r"[^a-zA-Z0-9а-яА-ЯіїєґІЇЄҐ_ -]+", "", _norm(text).lower())
    base = re.sub(r"\s+", "_", base).strip("_")[:64]
    return base or f"{fallback}_{int(time.time())}"


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\wа-яА-ЯіїєґІЇЄҐ]{3,}", str(text or "").lower())}


def _score(query: str, *texts: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    hay = _tokens("\n".join(texts))
    if not hay:
        return 0.0
    inter = len(q & hay)
    return inter / math.sqrt(max(1, len(q)) * max(1, len(hay)))


class SkillLibraryModule(CognitiveModule):
    MODULE_ID = "skill_library"
    MODULE_DESCRIPTION = "V14 procedural skill learning and lightweight knowledge graph"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(self.MODULE_ID, cost={"cpu": 0.08, "gpu": 0.0, "ram": 0.05})
        self.enabled = True
        self.auto_learn = True
        self.min_confidence = 0.55
        self.max_skills = 1000
        self.max_graph_edges = 5000
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.graph: List[Dict[str, Any]] = []
        self._state_path: Optional[Path] = None
        self._last_save = 0.0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "skills", None)
        self.enabled = bool(getattr(cfg, "enabled", True)) if cfg else True
        self.auto_learn = bool(getattr(cfg, "auto_learn", True)) if cfg else True
        self.min_confidence = float(getattr(cfg, "min_confidence", 0.55)) if cfg else 0.55
        self.max_skills = int(getattr(cfg, "max_skills", 1000)) if cfg else 1000
        self.max_graph_edges = int(getattr(cfg, "max_graph_edges", 5000)) if cfg else 5000
        data_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = data_dir / "skills_knowledge_v14.json"
        self._load_state()
        kernel.event_bus.register_consumer(self.module_id, [
            "skill_store_requested",
            "skill_search_requested",
            "skill_status_requested",
            "skill_list_requested",
            "skill_get_requested",
            "knowledge_graph_status_requested",
            "knowledge_query_requested",
            "knowledge_store_requested",
            "task_chain_completed",
            "task_chain_report_ready",
            "code_repair_proposal_ready",
            "code_repair_applied",
            "web_learning_completed",
            "web_fetch_completed",
            "action_result",
            "memory_stored",
            "sleep_cycle_completed",
            "kernel_started",
        ])
        self._emit("skill_library_ready", {
            "version": self.MODULE_VERSION,
            "skills": len(self.skills),
            "graph_edges": len(self.graph),
            "auto_learn": self.auto_learn,
        })

    async def tick(self, dt: float) -> None:
        if not self.enabled:
            return
        if time.time() - self._last_save > 60:
            self._save_state()

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        et = event.type
        data = event.data or {}
        if et == "skill_store_requested":
            skill = self._skill_from_payload(data)
            self._upsert_skill(skill)
            self._respond(f"Skill stored: {skill['name']} ({skill['id']})\nSteps: {len(skill.get('steps', []))}")
        elif et in {"skill_search_requested", "skill_get_requested"}:
            query = str(data.get("query") or data.get("name") or data.get("skill") or "")
            self._respond(self._format_skill_search(query, top_k=int(data.get("top_k", 6) or 6)))
        elif et in {"skill_status_requested", "skill_list_requested"}:
            self._respond(self._format_status())
        elif et == "knowledge_store_requested":
            edge = self._edge_from_payload(data)
            if edge:
                self._add_edge(edge)
                self._respond(f"Knowledge edge stored: {edge['subject']} —{edge['predicate']}→ {edge['object']}")
        elif et in {"knowledge_query_requested", "knowledge_graph_status_requested"}:
            query = str(data.get("query") or data.get("subject") or "")
            self._respond(self._format_knowledge(query=query, top_k=int(data.get("top_k", 8) or 8)))
        elif self.auto_learn:
            await self._learn_from_event(event)

    async def _learn_from_event(self, event: Event) -> None:
        et = event.type
        data = event.data or {}
        if et == "web_learning_completed":
            topic = str(data.get("topic") or data.get("query") or "web research")
            summary = _norm(data.get("summary") or data.get("answer") or data.get("text") or "")
            sources = data.get("sources") or data.get("source_urls") or []
            if summary:
                self._add_edge({
                    "subject": topic,
                    "predicate": "researched",
                    "object": summary[:1500],
                    "confidence": float(data.get("confidence", 0.72) or 0.72),
                    "source": "web_learning",
                    "evidence": sources,
                })
                self._maybe_store_semantic(topic, "researched", summary[:2000], confidence=float(data.get("confidence", 0.72) or 0.72))
        elif et in {"task_chain_completed", "task_chain_report_ready"}:
            goal = str(data.get("goal") or data.get("task") or data.get("title") or "completed task")
            steps = self._extract_steps(data)
            if steps:
                skill = {
                    "id": _slug(goal, "task_skill"),
                    "name": f"How to handle: {goal[:80]}",
                    "description": f"Learned from completed task: {goal}",
                    "triggers": self._infer_triggers(goal),
                    "steps": steps[:12],
                    "confidence": float(data.get("confidence", 0.66) or 0.66),
                    "source": et,
                    "created_at": time.time(),
                    "updated_at": time.time(),
                    "uses": 0,
                    "successes": 1,
                    "failures": 0,
                    "evidence": {"event": et, "task_id": data.get("task_id") or data.get("id")},
                }
                self._upsert_skill(skill)
        elif et in {"code_repair_applied", "code_repair_proposal_ready"}:
            title = str(data.get("title") or data.get("request_text") or data.get("path") or "code repair")
            steps = [
                "Diagnose compile/runtime errors and collect traceback context.",
                "Read the smallest relevant set of files inside the workspace.",
                "Ask the code model for a minimal patch with explanation.",
                "Validate the patch locally before applying it.",
                "Apply changes through safe write actions and rerun checks.",
            ]
            skill = {
                "id": _slug(f"repair {title}", "repair_skill"),
                "name": f"Repair workflow: {title[:80]}",
                "description": "Learned/updated from V9 code repair events.",
                "triggers": ["error", "traceback", "exception", "compile", "repair", "fix"],
                "steps": steps,
                "confidence": 0.72 if et == "code_repair_applied" else 0.60,
                "source": et,
                "created_at": time.time(),
                "updated_at": time.time(),
                "uses": 0,
                "successes": 1 if et == "code_repair_applied" else 0,
                "failures": 0,
                "evidence": {"event": et, "proposal_id": data.get("proposal_id")},
            }
            self._upsert_skill(skill)
        elif et == "action_result":
            if data.get("status") in {"ok", "success", True} or data.get("success") is True:
                action_type = str(data.get("action_type") or data.get("type") or "action")
                if action_type in {"run_command", "search_files", "read_file", "write_file"}:
                    skill = {
                        "id": _slug(f"use action {action_type}", "action_skill"),
                        "name": f"Use action: {action_type}",
                        "description": "Observed successful safe action execution.",
                        "triggers": [action_type, action_type.replace("_", " ")],
                        "steps": [f"Request safe action `{action_type}` with a clear payload.", "Wait for V7 safety approval/result.", "Verify the result before continuing."],
                        "confidence": 0.58,
                        "source": "action_result",
                        "created_at": time.time(),
                        "updated_at": time.time(),
                        "uses": 0,
                        "successes": 1,
                        "failures": 0,
                        "evidence": {"request_id": data.get("request_id")},
                    }
                    self._upsert_skill(skill)
        elif et == "sleep_cycle_completed":
            summary = _norm(data.get("summary") or "")
            for lesson in data.get("lessons") or []:
                text = _norm(lesson if isinstance(lesson, str) else lesson.get("text") or lesson.get("lesson") or "")
                if text:
                    self._add_edge({"subject": "sleep_consolidation", "predicate": "learned", "object": text, "confidence": 0.65, "source": et, "evidence": summary[:600]})

    def _skill_from_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = _norm(data.get("name") or data.get("skill_name") or data.get("title") or "Untitled skill")
        steps = data.get("steps") or []
        if isinstance(steps, str):
            steps = [s.strip(" -\t") for s in re.split(r"\n+|;", steps) if s.strip()]
        triggers = data.get("triggers") or self._infer_triggers(name)
        if isinstance(triggers, str):
            triggers = [x.strip() for x in triggers.split(",") if x.strip()]
        return {
            "id": str(data.get("id") or _slug(name, "skill")),
            "name": name,
            "description": _norm(data.get("description") or data.get("summary") or ""),
            "triggers": triggers[:20],
            "steps": [str(s).strip() for s in steps if str(s).strip()][:30],
            "confidence": float(data.get("confidence", 0.7) or 0.7),
            "source": str(data.get("source") or "manual"),
            "created_at": float(data.get("created_at", time.time()) or time.time()),
            "updated_at": time.time(),
            "uses": int(data.get("uses", 0) or 0),
            "successes": int(data.get("successes", 0) or 0),
            "failures": int(data.get("failures", 0) or 0),
            "evidence": data.get("evidence") or {},
        }

    def _edge_from_payload(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        subject = _norm(data.get("subject") or data.get("source") or "")
        predicate = _norm(data.get("predicate") or data.get("relation") or "related_to")
        obj = _norm(data.get("object") or data.get("target") or data.get("text") or "")
        if not subject or not obj:
            return None
        return {
            "id": f"kg_{int(time.time()*1000)}_{len(self.graph)}",
            "subject": subject[:240],
            "predicate": predicate[:80],
            "object": obj[:2000],
            "confidence": float(data.get("confidence", 0.7) or 0.7),
            "source": str(data.get("source") or "manual"),
            "evidence": data.get("evidence") or data.get("sources") or "",
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def _upsert_skill(self, skill: Dict[str, Any]) -> None:
        sid = str(skill.get("id") or _slug(skill.get("name", "skill")))
        old = self.skills.get(sid)
        now = time.time()
        if old:
            old["name"] = skill.get("name") or old.get("name")
            old["description"] = skill.get("description") or old.get("description", "")
            old_steps = list(old.get("steps") or [])
            for step in skill.get("steps") or []:
                if step not in old_steps:
                    old_steps.append(step)
            old["steps"] = old_steps[:30]
            old_triggers = list(old.get("triggers") or [])
            for tr in skill.get("triggers") or []:
                if tr not in old_triggers:
                    old_triggers.append(tr)
            old["triggers"] = old_triggers[:20]
            old["confidence"] = max(float(old.get("confidence", 0.5)), float(skill.get("confidence", 0.5)))
            old["updated_at"] = now
            old["successes"] = int(old.get("successes", 0)) + int(skill.get("successes", 0))
            old["failures"] = int(old.get("failures", 0)) + int(skill.get("failures", 0))
            old["source"] = skill.get("source") or old.get("source")
        else:
            skill["id"] = sid
            skill.setdefault("created_at", now)
            skill["updated_at"] = now
            self.skills[sid] = skill
        if len(self.skills) > self.max_skills:
            ordered = sorted(self.skills.items(), key=lambda kv: (float(kv[1].get("confidence", 0.0)), float(kv[1].get("updated_at", 0.0))))
            for sid, _ in ordered[: max(0, len(self.skills) - self.max_skills)]:
                self.skills.pop(sid, None)
        self._maybe_store_semantic(skill.get("name", sid), "procedure", "\n".join(skill.get("steps") or []), confidence=float(skill.get("confidence", 0.7)))
        self._save_state()

    def _add_edge(self, edge: Dict[str, Any]) -> None:
        # Merge very similar subject/predicate/object prefixes to avoid noisy duplicates.
        key = (edge.get("subject", "").lower(), edge.get("predicate", "").lower(), edge.get("object", "")[:200].lower())
        for existing in self.graph:
            ekey = (existing.get("subject", "").lower(), existing.get("predicate", "").lower(), existing.get("object", "")[:200].lower())
            if ekey == key:
                existing["confidence"] = max(float(existing.get("confidence", 0.5)), float(edge.get("confidence", 0.5)))
                existing["updated_at"] = time.time()
                return
        edge.setdefault("id", f"kg_{int(time.time()*1000)}_{len(self.graph)}")
        edge.setdefault("created_at", time.time())
        edge["updated_at"] = time.time()
        self.graph.append(edge)
        if len(self.graph) > self.max_graph_edges:
            self.graph = sorted(self.graph, key=lambda e: (float(e.get("confidence", 0.0)), float(e.get("updated_at", 0.0))))[-self.max_graph_edges:]
        self._save_state()

    def _search_skills(self, query: str, top_k: int = 6) -> List[Dict[str, Any]]:
        rows: List[Tuple[float, Dict[str, Any]]] = []
        for skill in self.skills.values():
            text = " ".join([skill.get("name", ""), skill.get("description", ""), " ".join(skill.get("triggers") or []), " ".join(skill.get("steps") or [])])
            score = _score(query, text)
            if not query.strip():
                score = float(skill.get("confidence", 0.5)) * 0.2 + min(0.8, int(skill.get("successes", 0)) * 0.05)
            if score > 0 or not query.strip():
                rows.append((score + float(skill.get("confidence", 0.5)) * 0.08, skill))
        rows.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in rows[:top_k]]

    def _search_graph(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        rows: List[Tuple[float, Dict[str, Any]]] = []
        for edge in self.graph:
            score = _score(query, edge.get("subject", ""), edge.get("predicate", ""), edge.get("object", ""))
            if not query.strip():
                score = float(edge.get("confidence", 0.5)) * 0.1
            if score > 0 or not query.strip():
                rows.append((score + float(edge.get("confidence", 0.5)) * 0.05, edge))
        rows.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in rows[:top_k]]

    def _format_skill_search(self, query: str, top_k: int = 6) -> str:
        matches = self._search_skills(query, top_k=top_k)
        if not matches:
            return f"No matching skills found for: {query!r}. I can learn one from a completed task or you can store it manually."
        lines = [f"Skill matches for: {query or 'all skills'}"]
        for s in matches:
            steps = s.get("steps") or []
            lines.append(f"\n- {s.get('name')} [{s.get('id')}] confidence={round(float(s.get('confidence', 0.0)), 2)}")
            if s.get("description"):
                lines.append(f"  {s.get('description')[:240]}")
            for i, step in enumerate(steps[:5], 1):
                lines.append(f"  {i}. {step}")
        return "\n".join(lines)

    def _format_knowledge(self, query: str = "", top_k: int = 8) -> str:
        if not query and self.graph:
            matches = sorted(self.graph, key=lambda e: float(e.get("updated_at", 0.0)), reverse=True)[:top_k]
        else:
            matches = self._search_graph(query, top_k=top_k)
        if not matches:
            return f"Knowledge graph has {len(self.graph)} edges, but no match for: {query!r}."
        lines = [f"Knowledge graph matches for: {query or 'recent knowledge'}"]
        for e in matches:
            lines.append(f"- {e.get('subject')} —{e.get('predicate')}→ {str(e.get('object'))[:260]} (conf={round(float(e.get('confidence', 0.0)), 2)}, source={e.get('source')})")
        return "\n".join(lines)

    def _format_status(self) -> str:
        top = sorted(self.skills.values(), key=lambda s: (float(s.get("confidence", 0.0)), float(s.get("updated_at", 0.0))), reverse=True)[:6]
        lines = [
            "V14 Skill Library + Knowledge Graph",
            f"enabled={self.enabled}, auto_learn={self.auto_learn}",
            f"skills={len(self.skills)}/{self.max_skills}, graph_edges={len(self.graph)}/{self.max_graph_edges}",
            f"storage={self._state_path}",
        ]
        if top:
            lines.append("Top/recent skills:")
            for s in top:
                lines.append(f"- {s.get('name')} [{s.get('id')}] confidence={round(float(s.get('confidence', 0.0)), 2)} steps={len(s.get('steps') or [])}")
        return "\n".join(lines)

    def _extract_steps(self, data: Dict[str, Any]) -> List[str]:
        steps: List[str] = []
        for key in ("steps", "completed_steps", "plan"):
            val = data.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        txt = item.get("title") or item.get("task") or item.get("description") or item.get("result")
                    else:
                        txt = item
                    if txt:
                        steps.append(_norm(txt))
        report = str(data.get("report") or data.get("summary") or "")
        if not steps and report:
            for line in report.splitlines():
                line = line.strip(" -\t")
                if 8 <= len(line) <= 240 and any(w in line.lower() for w in ["check", "read", "run", "verify", "search", "перев", "знай", "проч"]):
                    steps.append(line)
        return steps[:20]

    def _infer_triggers(self, text: str) -> List[str]:
        toks = list(_tokens(text))[:10]
        extras = []
        l = text.lower()
        if any(w in l for w in ["error", "помил", "traceback", "exception"]):
            extras.extend(["error", "debug", "repair"])
        if any(w in l for w in ["web", "інтернет", "research", "вивчи"]):
            extras.extend(["web research", "learn"])
        return list(dict.fromkeys(extras + toks))[:12]

    def _maybe_store_semantic(self, subject: str, predicate: str, obj: str, confidence: float = 0.7) -> None:
        if not self.kernel or not obj or confidence < self.min_confidence:
            return
        self.kernel.event_bus.emit(
            Event(type="semantic_memory_store_requested", data={
                "subject": subject[:200],
                "predicate": predicate[:80],
                "object": obj[:3000],
                "confidence": confidence,
                "importance": max(0.7, confidence),
                "source": "skill_library_v14",
            }, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    def _respond(self, text: str) -> None:
        if not self.kernel:
            return
        self.kernel.event_bus.emit(
            Event(type="response_generated", data={"text": text, "source": "skill_library_v14"}, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type=event_type, data=data, source_module=self.module_id), Priority.COGNITIVE)

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            skills = data.get("skills") or {}
            if isinstance(skills, list):
                skills = {str(s.get("id") or _slug(s.get("name", "skill"))): s for s in skills if isinstance(s, dict)}
            self.skills = {str(k): v for k, v in skills.items() if isinstance(v, dict)}
            self.graph = [e for e in (data.get("graph") or []) if isinstance(e, dict)]
        except Exception:
            self.skills = {}
            self.graph = []

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": self.MODULE_VERSION, "updated_at": time.time(), "skills": self.skills, "graph": self.graph[-self.max_graph_edges:]}
            self._state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._last_save = time.time()
        except Exception:
            pass

    def shutdown(self) -> None:
        self._save_state()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "auto_learn": self.auto_learn,
            "skills_count": len(self.skills),
            "knowledge_edges": len(self.graph),
            "storage": str(self._state_path or ""),
            "top_skills": [s.get("name") for s in sorted(self.skills.values(), key=lambda x: float(x.get("updated_at", 0.0)), reverse=True)[:8]],
        })
        return base


def create_module() -> SkillLibraryModule:
    return SkillLibraryModule()
