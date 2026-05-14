"""Tier 3 Reasoning: World Model Module (V5)

V5 stores a structured, persistent model of the operating world:
  - active projects and their state
  - environment observations from screen/voice/dialogue/events
  - recurring patterns and causal beliefs
  - user intent trends
  - unresolved open loops

Persists to ~/.jarvis_brain/world_model_v5.json

Emits:
  - world_model_updated
  - world_context
  - pattern_detected
  - project_state_updated

Listens:
  - kernel_started, user_utterance, dialogue_turn_completed, response_generated
  - screen_parsed, memory_stored, goal_achieved, goal_failed
  - action_approved, action_denied, tts_error, capability_model_updated
  - world_model_request
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("world_model")

_PATTERN_THRESHOLD = 3
_DEFAULT_SNAPSHOT_INTERVAL = 10.0

_PROJECT_HINTS = {
    "jarvis": ["jarvis", "jav", "brain", "асистент", "джарвіс", "ядро", "мозок"],
    "voice": ["voice", "голос", "tts", "stt", "piper", "pyttsx3", "whisper", "мікрофон"],
    "screen": ["screen", "ocr", "екран", "скрін", "read-screen", "tesseract"],
    "memory": ["memory", "пам'ять", "память", "rag", "контекст"],
    "automation": ["automation", "автоматиза", "pc", "комп", "дії", "actions"],
}


class WorldModelModule(CognitiveModule):
    """Structured environment/project/pattern model."""

    MODULE_DESCRIPTION = "V5 world model — projects, environment, patterns, causal beliefs, and open loops"
    MODULE_VERSION = "5.0.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="world_model",
            cost={"cpu": 0.10, "gpu": 0.0, "ram": 0.12},
        )
        self.environment: Dict[str, Any] = {
            "runtime": "local_python_kernel",
            "screen": {"available": False, "last_summary": "", "last_errors": []},
            "voice": {"available": False, "last_error": ""},
            "llm": {"available": "unknown", "last_mode": ""},
            "safety": {"last_denial": "", "pending": []},
        }
        self.projects: Dict[str, Dict[str, Any]] = {
            "jarvis_core": {
                "name": "JAV / Jarvis Brain Core",
                "status": "active",
                "stage": "V5 world model + mature self-model",
                "description": "personal cognitive assistant with dialogue, memory, voice, screen reading, affect, and self/world model",
                "last_update": time.time(),
                "open_loops": ["stabilize V5 context injection", "prepare V6 sleep/dream memory consolidation"],
                "confidence": 0.64,
            }
        }
        self.user_intents: Dict[str, int] = {}
        self.patterns: Dict[str, Dict[str, Any]] = {}
        self.causal_beliefs: Dict[str, Dict[str, Any]] = {}
        self.open_loops: List[Dict[str, Any]] = []
        self.timeline: List[Dict[str, Any]] = []
        self.capability_context: Dict[str, Any] = {}
        self._last_snapshot = 0.0

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        self._load()
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "kernel_started",
                "user_utterance",
                "dialogue_turn_completed",
                "response_generated",
                "screen_parsed",
                "memory_stored",
                "goal_achieved",
                "goal_failed",
                "action_approved",
                "action_denied",
                "safety_violation",
                "tts_spoken",
                "tts_error",
                "capability_model_updated",
                "world_model_request",
            ],
        )

    async def on_event(self, event: Event) -> None:
        et = event.type
        if et == "kernel_started":
            self._record_timeline("kernel_started", {"modules": list(getattr(self.kernel, "modules", {}).keys())[:40]})
            self._emit_context(reason="kernel_started")
        elif et == "user_utterance":
            text = str(event.data.get("text", "") or "")
            self._observe_user_text(text)
            self._record_timeline("user_utterance", {"text": text[:500], "input_mode": event.data.get("input_mode")})
        elif et == "dialogue_turn_completed":
            self.environment["llm"]["available"] = "yes"
            self.environment["llm"]["last_mode"] = event.data.get("mode", "")
            self._record_timeline("dialogue_turn_completed", {"user": str(event.data.get("user_text", ""))[:220], "mode": event.data.get("mode")})
        elif et == "response_generated":
            self.environment["llm"]["available"] = "yes"
        elif et == "screen_parsed":
            self.environment["screen"]["available"] = True
            self.environment["screen"]["last_summary"] = str(event.data.get("summary") or event.data.get("detected_context") or "")[:800]
            self.environment["screen"]["last_errors"] = list(event.data.get("important_blocks") or [])[:5]
            self._record_timeline("screen_parsed", {"summary": self.environment["screen"]["last_summary"]})
        elif et == "goal_achieved":
            self._update_causal("goal effort", "can produce success", +1)
            self._update_project_from_goal(event.data, success=True)
        elif et == "goal_failed":
            self._update_causal("goal effort", "can fail and needs diagnosis", +1)
            self._update_project_from_goal(event.data, success=False)
        elif et == "action_approved":
            self._update_causal("safety approval", "allows action execution", +1)
        elif et in {"action_denied", "safety_violation"}:
            reason = event.data.get("reason") or event.data.get("rule") or "unknown"
            self.environment["safety"]["last_denial"] = str(reason)[:300]
            self._update_causal("unsafe or unapproved action", "is blocked by safety layer", +1)
        elif et == "tts_spoken":
            self.environment["voice"]["available"] = True
        elif et == "tts_error":
            self.environment["voice"]["available"] = False
            self.environment["voice"]["last_error"] = str(event.data)[:500]
        elif et == "capability_model_updated":
            self.capability_context = dict(event.data or {})
        elif et == "world_model_request":
            self._emit_context(reason=str(event.data.get("reason") or "requested"), request_id=event.data.get("request_id"))

    def update(self, dt: float) -> None:
        now = time.time()
        interval = self._cfg_float("world_snapshot_interval", _DEFAULT_SNAPSHOT_INTERVAL)
        if now - self._last_snapshot >= interval:
            self._emit_context(reason="periodic")

    def _cfg_float(self, name: str, default: float) -> float:
        cfg = getattr(getattr(self.kernel, "config", None), "world_model", None) if self.kernel else None
        return float(getattr(cfg, name, default) if cfg is not None else default)

    def _observe_user_text(self, text: str) -> None:
        if not text:
            return
        lowered = text.lower()
        intent = self._classify_intent(lowered)
        self.user_intents[intent] = self.user_intents.get(intent, 0) + 1
        self._observe_pattern(f"intent:{intent}", outcome="utterance")

        project_key = self._detect_project(lowered)
        if project_key:
            project = self.projects.setdefault(project_key, {
                "name": project_key,
                "status": "active",
                "stage": "unknown",
                "description": "inferred from user dialogue",
                "last_update": 0.0,
                "open_loops": [],
                "confidence": 0.4,
            })
            project["last_update"] = time.time()
            project["confidence"] = min(1.0, float(project.get("confidence", 0.4)) + 0.03)
            if intent in {"build", "improve", "fix", "next_step"}:
                loop = self._extract_open_loop(text, intent)
                if loop:
                    loops = list(project.get("open_loops") or [])
                    if loop not in loops:
                        loops.append(loop)
                    project["open_loops"] = loops[-8:]
                    self._add_open_loop(loop, project_key, source="user_utterance")
            self._emit_project_update(project_key, project)

        # Roadmap version tracking: V0..V8
        for match in re.findall(r"\b[vв](\d+)\b", lowered, flags=re.IGNORECASE):
            stage = f"V{match}"
            core = self.projects.setdefault("jarvis_core", self.projects.get("jarvis_core", {}))
            core["stage"] = stage
            core["last_update"] = time.time()

    def _classify_intent(self, lowered: str) -> str:
        if any(w in lowered for w in ["зробим", "робим", "додай", "реаліз", "build", "implement", "create"]):
            return "build"
        if any(w in lowered for w in ["покращ", "улучш", "improve", "upgrade"]):
            return "improve"
        if any(w in lowered for w in ["помилка", "error", "fix", "виправ", "не працю"]):
            return "fix"
        if any(w in lowered for w in ["далі", "наступ", "next"]):
            return "next_step"
        if any(w in lowered for w in ["що", "как", "чи", "?", "how", "why"]):
            return "question"
        return "conversation"

    def _detect_project(self, lowered: str) -> str:
        for key, hints in _PROJECT_HINTS.items():
            if any(h in lowered for h in hints):
                return "jarvis_core" if key in {"jarvis", "voice", "screen", "memory", "automation"} else key
        return "jarvis_core"

    def _extract_open_loop(self, text: str, intent: str) -> str:
        clean = " ".join(text.strip().split())[:180]
        if not clean:
            return ""
        return f"{intent}: {clean}"

    def _update_project_from_goal(self, data: Dict[str, Any], success: bool) -> None:
        desc = str(data.get("description") or data.get("title") or "goal")[:220]
        project = self.projects.setdefault("jarvis_core", {
            "name": "JAV / Jarvis Brain Core",
            "status": "active",
            "stage": "unknown",
            "description": "personal cognitive assistant",
            "last_update": time.time(),
            "open_loops": [],
            "confidence": 0.5,
        })
        project["last_update"] = time.time()
        project["confidence"] = max(0.0, min(1.0, float(project.get("confidence", 0.5)) + (0.04 if success else -0.03)))
        if success:
            project["last_success"] = desc
        else:
            project["last_failure"] = desc
            self._add_open_loop(f"diagnose failed goal: {desc}", "jarvis_core", source="goal_failed")
        self._emit_project_update("jarvis_core", project)

    def _observe_pattern(self, key: str, outcome: str) -> None:
        entry = self.patterns.setdefault(key, {"frequency": 0, "last_seen": 0.0, "outcomes": {}, "confidence": 0.0})
        entry["frequency"] += 1
        entry["last_seen"] = time.time()
        entry["outcomes"][outcome] = entry["outcomes"].get(outcome, 0) + 1
        entry["confidence"] = min(1.0, entry["frequency"] / 10.0)
        if entry["frequency"] == _PATTERN_THRESHOLD and self.kernel:
            self.kernel.event_bus.emit(
                Event(type="pattern_detected", data={"key": key, "entry": entry}, source_module=self.module_id),
                Priority.BACKGROUND,
            )

    def _update_causal(self, cause: str, effect: str, evidence_delta: int) -> None:
        key = f"{cause}->{effect}"
        belief = self.causal_beliefs.setdefault(key, {"cause": cause, "effect": effect, "evidence": 0, "confidence": 0.0, "last_seen": 0.0})
        belief["evidence"] += evidence_delta
        belief["confidence"] = min(1.0, max(0.0, belief["evidence"] / 8.0))
        belief["last_seen"] = time.time()

    def _add_open_loop(self, text: str, project: str, source: str) -> None:
        item = {"text": text[:240], "project": project, "source": source, "status": "open", "timestamp": time.time()}
        if not any(x.get("text") == item["text"] for x in self.open_loops):
            self.open_loops.append(item)
        self.open_loops = self.open_loops[-25:]

    def _record_timeline(self, kind: str, data: Dict[str, Any]) -> None:
        self.timeline.append({"kind": kind, "data": data, "timestamp": time.time()})
        self.timeline = self.timeline[-80:]

    def _build_context(self) -> Dict[str, Any]:
        top_patterns = sorted(self.patterns.items(), key=lambda x: x[1].get("frequency", 0), reverse=True)[:8]
        top_beliefs = sorted(self.causal_beliefs.values(), key=lambda x: x.get("confidence", 0), reverse=True)[:6]
        active_projects = {k: v for k, v in self.projects.items() if v.get("status") == "active"}
        return {
            "schema": "world_model_v5",
            "environment": self.environment,
            "active_projects": active_projects,
            "user_intents": dict(sorted(self.user_intents.items(), key=lambda x: x[1], reverse=True)[:8]),
            "top_patterns": [{"key": k, **v} for k, v in top_patterns],
            "causal_beliefs": top_beliefs,
            "open_loops": list(self.open_loops[-10:]),
            "recent_timeline": list(self.timeline[-10:]),
            "capability_context": self.capability_context,
            "timestamp": time.time(),
        }

    def _emit_context(self, reason: str = "periodic", request_id: Any = None) -> None:
        if not self.kernel:
            return
        self._last_snapshot = time.time()
        ctx = self._build_context()
        ctx["reason"] = reason
        if request_id is not None:
            ctx["request_id"] = request_id
        self.kernel.event_bus.emit(
            Event(type="world_context", data=ctx, source_module=self.module_id),
            Priority.BACKGROUND,
        )
        self.kernel.event_bus.emit(
            Event(type="world_model_updated", data=ctx, source_module=self.module_id),
            Priority.BACKGROUND,
        )

    def _emit_project_update(self, project_key: str, project: Dict[str, Any]) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(type="project_state_updated", data={"project_key": project_key, "project": project}, source_module=self.module_id),
                Priority.BACKGROUND,
            )

    def shutdown(self) -> None:
        self._save()

    def _save(self) -> None:
        if self.kernel:
            self.kernel.persistence.save("world_model_v5", {
                "environment": self.environment,
                "projects": self.projects,
                "user_intents": self.user_intents,
                "patterns": self.patterns,
                "causal_beliefs": self.causal_beliefs,
                "open_loops": self.open_loops,
                "timeline": self.timeline[-80:],
                "capability_context": self.capability_context,
            })
            logger.info("[WorldModelV5] Saved to disk")

    def _load(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("world_model_v5") or self.kernel.persistence.load("world_model")
        if isinstance(data, dict):
            if "patterns" in data or "projects" in data:
                self.environment.update(data.get("environment") or {})
                self.projects.update(data.get("projects") or {})
                self.user_intents.update(data.get("user_intents") or {})
                self.patterns.update(data.get("patterns") or {})
                self.causal_beliefs.update(data.get("causal_beliefs") or {})
                self.open_loops = list(data.get("open_loops") or self.open_loops)[-25:]
                self.timeline = list(data.get("timeline") or self.timeline)[-80:]
                self.capability_context.update(data.get("capability_context") or {})
            else:
                # migrate old simple pattern map
                self.patterns.update(data)
            logger.info(f"[WorldModelV5] Loaded {len(self.patterns)} pattern(s), {len(self.projects)} project(s)")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        ctx = self._build_context()
        base.update({
            "project_count": len(self.projects),
            "active_projects": list(ctx["active_projects"].keys()),
            "pattern_count": len(self.patterns),
            "open_loop_count": len(self.open_loops),
            "top_intents": ctx["user_intents"],
            "environment": self.environment,
        })
        return base


def create_module() -> WorldModelModule:
    return WorldModelModule()
