"""Tier 1 Essential: Self Model Module (V5)

V5 turns the self model into a mature, persistent model of Jarvis' identity,
capabilities, limits, operating rules, confidence, and current relationship to
its environment. It is intentionally honest: capabilities are described as what
this program can actually do through loaded modules, not as fantasy abilities.

Persists to ~/.jarvis_brain/self_model_v5.json

Emits:
  - self_model_updated       periodic full snapshot
  - self_reflection          short internal reflection when state changes
  - capability_model_updated when module inventory/capability map changes

Listens:
  - kernel_started, module_loaded, module_unloaded, module_error
  - response_generated, dialogue_turn_completed
  - goal_achieved, goal_failed, learning_applied
  - emotional_state, screen_parsed, tts_spoken, tts_error
  - self_model_request
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("self_model")

_DEFAULT_SNAPSHOT_INTERVAL = 12.0
_DEFAULT_REFLECTION_INTERVAL = 45.0


class SelfModelModule(CognitiveModule):
    """Persistent identity, capability inventory, limits and self-state."""

    MODULE_DESCRIPTION = "V5 mature self-model — identity, capabilities, limits, confidence, and self-context"
    MODULE_VERSION = "5.0.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="self_model",
            cost={"cpu": 0.06, "gpu": 0.0, "ram": 0.06},
        )
        self.identity_name: str = "Jarvis"
        self.role: str = "persistent personal cognitive assistant"
        self.identity_version: int = 5
        self.communication_style: str = "direct, warm, technically precise, and honest"

        self.purpose: List[str] = [
            "help the user think, plan, build, debug, and remember",
            "coordinate perception, memory, reasoning, voice, and safe actions",
            "remain honest about uncertainty, missing tools, and real limitations",
        ]
        self.operating_principles: List[str] = [
            "never invent memories or capabilities",
            "ask for or require confirmation before risky actions",
            "prefer concrete next steps over vague motivation",
            "keep user projects and long-term context coherent across sessions",
            "treat self-improvement as proposal -> test -> review, not uncontrolled self-modification",
        ]
        self.hard_limits: List[str] = [
            "cannot act outside available modules and permissions",
            "cannot guarantee correctness without tests, logs, or direct evidence",
            "cannot access private files, screen, audio, or network unless the runtime is configured to expose them",
            "does not have human feelings; affective state is a control signal for tone and prioritization",
        ]

        self.capabilities: Dict[str, Dict[str, Any]] = {}
        self.active_interfaces: List[str] = []
        self.known_limitations: List[str] = []
        self.recent_failures: List[Dict[str, Any]] = []
        self.recent_successes: List[Dict[str, Any]] = []
        self.current_environment: Dict[str, Any] = {
            "screen_available": False,
            "voice_available": False,
            "llm_available": "unknown",
            "last_screen_summary": "",
        }

        self.confidence: float = 0.72
        self.reliability: float = 0.62
        self.autonomy_level: float = 0.22
        self.attachment_level: float = 0.5
        self.cognitive_maturity: float = 0.45
        self.self_awareness_notes: List[str] = []

        # Phase 2 — PersonaEvolution: character that grows with the user
        self.persona_name: str = ""                  # empty = use identity_name ("Jarvis")
        self.adapted_style: str = ""                 # e.g. "direct, light sarcasm, no fluff"
        self.persona_evolution_log: List[str] = []   # rolling 5 observations about the relationship
        self.relationship_depth: float = 0.0         # 0-1, grows with every completed turn
        self.shared_references: List[str] = []       # topics/projects mentioned 3+ times

        self._goal_success_count = 0
        self._goal_fail_count = 0
        self._last_snapshot = 0.0
        self._last_reflection = 0.0
        self._last_emotion: Dict[str, Any] = {}
        self._topic_counts: Dict[str, int] = {}      # for shared_references tracking

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        self._load()
        cfg = getattr(getattr(kernel, "config", None), "persona", None)
        if cfg and getattr(cfg, "persona_name", ""):
            self.persona_name = str(cfg.persona_name).strip()

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "kernel_started",
                "module_loaded",
                "module_unloaded",
                "module_error",
                "goal_achieved",
                "goal_failed",
                "learning_applied",
                "emotional_state",
                "response_generated",
                "dialogue_turn_completed",
                "screen_parsed",
                "tts_spoken",
                "tts_error",
                "self_model_request",
                "memory_consolidated",
                "sleep_cycle_completed",
                "consolidation_lesson",
                "dream_narrative",
                "user_profile_updated",   # Phase 2: learn from user profile
                "user_utterance",         # Phase 2: track topic frequency
            ],
        )

    async def on_event(self, event: Event) -> None:
        et = event.type
        if et == "kernel_started":
            self._refresh_capabilities()
            self._emit_snapshot(reason="kernel_started")
        elif et in {"module_loaded", "module_unloaded"}:
            self._refresh_capabilities()
            self._emit_capability_update()
        elif et == "module_error":
            self._record_failure("module_error", event.data)
        elif et == "goal_achieved":
            self._goal_success_count += 1
            self.confidence = min(1.0, self.confidence + 0.012)
            self.reliability = min(1.0, self.reliability + 0.006)
            self._record_success("goal_achieved", event.data)
        elif et == "goal_failed":
            self._goal_fail_count += 1
            self.confidence = max(0.08, self.confidence - 0.015)
            self.reliability = max(0.05, self.reliability - 0.01)
            self._record_failure("goal_failed", event.data)
        elif et == "learning_applied":
            self.cognitive_maturity = min(1.0, self.cognitive_maturity + 0.006)
            self.confidence = min(1.0, self.confidence + 0.004)
            self.self_awareness_notes.append(str(event.data.get("summary") or "learning applied")[:240])
            self.self_awareness_notes = self.self_awareness_notes[-12:]
        elif et == "emotional_state":
            self._last_emotion = dict(event.data or {})
            valence = float(event.data.get("valence", 0.0) or 0.0)
            if valence > 0.3:
                self.attachment_level = min(1.0, self.attachment_level + 0.004)
            elif valence < -0.55:
                self.attachment_level = max(0.0, self.attachment_level - 0.003)
        elif et == "response_generated":
            # A successful generated answer slightly improves operational confidence.
            self.confidence = min(1.0, self.confidence + 0.001)
        elif et == "dialogue_turn_completed":
            self.current_environment["llm_available"] = "yes"
            # Phase 2: deepen relationship with every completed turn
            increment = self._cfg_float("relationship_depth_increment", 0.001)
            self.relationship_depth = min(1.0, self.relationship_depth + increment)
        elif et == "user_utterance":
            # Phase 2: track topic frequency for shared_references
            self._track_topics(str(event.data.get("text", "") or ""))
        elif et == "user_profile_updated":
            # Phase 2: update adapted_style from persona_notes
            notes = str(event.data.get("persona_notes") or "").strip()
            if notes and notes != self.adapted_style:
                self.adapted_style = notes
                log_entry = f"Learned user style: {notes[:120]}"
                self.persona_evolution_log.append(log_entry)
                max_log = self._cfg_int("max_evolution_log", 5)
                self.persona_evolution_log = self.persona_evolution_log[-max_log:]
                logger.debug("[SelfModel] adapted_style updated")
        elif et == "screen_parsed":
            self.current_environment["screen_available"] = True
            summary = event.data.get("summary") or event.data.get("detected_context") or ""
            self.current_environment["last_screen_summary"] = str(summary)[:500]
        elif et == "tts_spoken":
            self.current_environment["voice_available"] = True
        elif et == "tts_error":
            self.current_environment["voice_available"] = False
            self._record_failure("tts_error", event.data)
        elif et == "self_model_request":
            self._emit_snapshot(reason=str(event.data.get("reason") or "requested"), request_id=event.data.get("request_id"))
        elif et in {"memory_consolidated", "sleep_cycle_completed"}:
            self.cognitive_maturity = min(1.0, self.cognitive_maturity + 0.008)
            summary = str(event.data.get("summary") or "memory consolidated")[:320]
            self.self_awareness_notes.append("V6 consolidation: " + summary)
            self.self_awareness_notes = self.self_awareness_notes[-12:]
            self._emit_snapshot(reason="v6_memory_consolidated")
        elif et == "consolidation_lesson":
            self.cognitive_maturity = min(1.0, self.cognitive_maturity + 0.003)
            summary = str(event.data.get("summary") or "lesson")[:260]
            self.self_awareness_notes.append("Lesson: " + summary)
            self.self_awareness_notes = self.self_awareness_notes[-12:]
        elif et == "dream_narrative":
            narrative = str(event.data.get("narrative") or "")[:260]
            if narrative:
                self.self_awareness_notes.append("Dream replay: " + narrative)
                self.self_awareness_notes = self.self_awareness_notes[-12:]

    def update(self, dt: float) -> None:
        now = time.time()
        interval = self._cfg_float("self_snapshot_interval", _DEFAULT_SNAPSHOT_INTERVAL)
        if now - self._last_snapshot >= interval:
            self._emit_snapshot(reason="periodic")
        reflection_interval = self._cfg_float("self_reflection_interval", _DEFAULT_REFLECTION_INTERVAL)
        if now - self._last_reflection >= reflection_interval:
            self._emit_reflection()

    def _cfg_float(self, name: str, default: float) -> float:
        # Check persona config first (relationship_depth_increment lives there)
        cfg_persona = getattr(getattr(self.kernel, "config", None), "persona", None) if self.kernel else None
        if cfg_persona is not None and hasattr(cfg_persona, name):
            return float(getattr(cfg_persona, name, default))
        cfg = getattr(getattr(self.kernel, "config", None), "self_model", None) if self.kernel else None
        return float(getattr(cfg, name, default) if cfg is not None else default)

    def _cfg_int(self, name: str, default: int) -> int:
        cfg_persona = getattr(getattr(self.kernel, "config", None), "persona", None) if self.kernel else None
        if cfg_persona is not None and hasattr(cfg_persona, name):
            return int(getattr(cfg_persona, name, default))
        return default

    def _track_topics(self, text: str) -> None:
        """Count topic keywords to surface shared references."""
        if not text:
            return
        words = re.findall(r'\b[A-ZА-ЯЄІЇa-zа-яєії][A-ZА-ЯЄІЇa-zа-яєії0-9_\-]{2,24}\b', text)
        for w in words:
            self._topic_counts[w] = self._topic_counts.get(w, 0) + 1
            if self._topic_counts[w] >= 3:
                ref = w.strip()
                if ref not in self.shared_references:
                    max_refs = self._cfg_int("max_shared_references", 20)
                    if len(self.shared_references) < max_refs:
                        self.shared_references.append(ref)
                        logger.debug("[SelfModel] Shared reference detected: %s", ref)

    def _refresh_capabilities(self) -> None:
        modules = getattr(self.kernel, "modules", {}) if self.kernel else {}
        capability_map: Dict[str, Dict[str, Any]] = {}
        interfaces: List[str] = []

        mapping = {
            "memory": ("memory", "stores and retrieves dialogue/semantic/episodic context"),
            "llm": ("dialogue", "generates language responses using retrieved memory and LLM router"),
            "screen_parser": ("screen_reading", "captures screen and extracts visible text/context through OCR"),
            "tts": ("voice_output", "speaks responses through Piper or pyttsx3"),
            "audio": ("audio_perception", "audio simulation or microphone-related perception support"),
            "emotion": ("affective_appraisal", "tracks affective tone for prioritization and style"),
            "monologue": ("internal_monologue", "maintains reflective focus, questions, and inner narrative"),
            "world_model": ("world_model", "tracks environment, projects, patterns, and causal beliefs"),
            "planner": ("planning", "creates and tracks plans/goals"),
            "dream": ("dream_consolidation", "offline memory consolidation/simulation"),
        }
        for module_id, module in modules.items():
            key, desc = mapping.get(module_id, (module_id, getattr(module, "MODULE_DESCRIPTION", module_id)))
            capability_map[key] = {
                "module_id": module_id,
                "description": desc,
                "enabled": bool(getattr(module, "enabled", True)),
                "version": getattr(module, "MODULE_VERSION", "unknown"),
            }
        if "screen_reading" in capability_map:
            interfaces.append("screen")
        if "voice_output" in capability_map or "audio_perception" in capability_map:
            interfaces.append("voice")
        if "dialogue" in capability_map:
            interfaces.append("chat")
        self.capabilities = capability_map
        self.active_interfaces = sorted(set(interfaces))
        self.known_limitations = self._derive_limitations()

    def _derive_limitations(self) -> List[str]:
        limits = list(self.hard_limits)
        if "dialogue" not in self.capabilities:
            limits.append("dialogue module is not loaded")
        if "screen_reading" not in self.capabilities:
            limits.append("screen reading module is not loaded")
        if "voice_output" not in self.capabilities:
            limits.append("voice output module is not loaded")
        if "world_model" not in self.capabilities:
            limits.append("world model module is not loaded")
        return limits[:12]

    def _build_snapshot(self) -> Dict[str, Any]:
        total = max(1, self._goal_success_count + self._goal_fail_count)
        return {
            "schema": "self_model_v5",
            "identity_name": self.identity_name,
            "role": self.role,
            "identity_version": self.identity_version,
            "communication_style": self.communication_style,
            "purpose": list(self.purpose),
            "operating_principles": list(self.operating_principles),
            "hard_limits": list(self.hard_limits),
            "known_limitations": list(self.known_limitations),
            "capabilities": self.capabilities,
            "active_interfaces": list(self.active_interfaces),
            "confidence": round(self.confidence, 3),
            "reliability": round(self.reliability, 3),
            "autonomy_level": round(self.autonomy_level, 3),
            "attachment_level": round(self.attachment_level, 3),
            "cognitive_maturity": round(self.cognitive_maturity, 3),
            "goal_success_rate": round(self._goal_success_count / total, 3),
            "goal_counts": {"success": self._goal_success_count, "failure": self._goal_fail_count},
            "current_environment": dict(self.current_environment),
            "recent_failures": list(self.recent_failures[-5:]),
            "recent_successes": list(self.recent_successes[-5:]),
            "self_awareness_notes": list(self.self_awareness_notes[-8:]),
            "affective_snapshot": {k: self._last_emotion.get(k) for k in ("emotion", "mood", "confidence", "cognitive_load")},
            # Phase 2 — PersonaEvolution
            "persona_name": self.persona_name,
            "adapted_style": self.adapted_style,
            "persona_evolution_log": list(self.persona_evolution_log),
            "relationship_depth": round(self.relationship_depth, 4),
            "shared_references": list(self.shared_references),
            "timestamp": time.time(),
        }

    def _emit_snapshot(self, reason: str = "periodic", request_id: Any = None) -> None:
        if not self.kernel:
            return
        self._last_snapshot = time.time()
        snap = self._build_snapshot()
        snap["reason"] = reason
        if request_id is not None:
            snap["request_id"] = request_id
        self.kernel.core_state.patch({"attachment_state": self.attachment_level})
        self.kernel.event_bus.emit(
            Event(type="self_model_updated", data=snap, source_module=self.module_id),
            Priority.BACKGROUND,
        )

    def _emit_capability_update(self) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="capability_model_updated",
                    data={"capabilities": self.capabilities, "active_interfaces": self.active_interfaces},
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )

    def _emit_reflection(self) -> None:
        if not self.kernel:
            return
        self._last_reflection = time.time()
        top_limit = self.known_limitations[0] if self.known_limitations else "no major limitation detected"
        reflection = (
            f"I am {self.identity_name}: confidence={self.confidence:.2f}, "
            f"reliability={self.reliability:.2f}, maturity={self.cognitive_maturity:.2f}. "
            f"Current constraint: {top_limit}."
        )
        self.kernel.event_bus.emit(
            Event(type="self_reflection", data={"text": reflection, "snapshot": self._build_snapshot()}, source_module=self.module_id),
            Priority.BACKGROUND,
        )

    def _record_failure(self, kind: str, data: Dict[str, Any]) -> None:
        self.recent_failures.append({"kind": kind, "data": self._trim_dict(data), "timestamp": time.time()})
        self.recent_failures = self.recent_failures[-12:]

    def _record_success(self, kind: str, data: Dict[str, Any]) -> None:
        self.recent_successes.append({"kind": kind, "data": self._trim_dict(data), "timestamp": time.time()})
        self.recent_successes = self.recent_successes[-12:]

    def _trim_dict(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return str(data)[:300]
        return {str(k): str(v)[:220] for k, v in list(data.items())[:8]}

    def shutdown(self) -> None:
        self._save()

    def _save(self) -> None:
        if self.kernel:
            self.kernel.persistence.save("self_model_v5", self._build_snapshot())
            logger.info("[SelfModelV5] Saved to disk")

    def _load(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("self_model_v5") or self.kernel.persistence.load("self_model")
        if isinstance(data, dict):
            self.identity_name = data.get("identity_name", self.identity_name)
            self.role = data.get("role", self.role)
            self.communication_style = data.get("communication_style", self.communication_style)
            self.identity_version = int(data.get("identity_version", self.identity_version) or self.identity_version)
            self.confidence = float(data.get("confidence", self.confidence) or self.confidence)
            self.reliability = float(data.get("reliability", self.reliability) or self.reliability)
            self.autonomy_level = float(data.get("autonomy_level", self.autonomy_level) or self.autonomy_level)
            self.attachment_level = float(data.get("attachment_level", self.attachment_level) or self.attachment_level)
            self.cognitive_maturity = float(data.get("cognitive_maturity", self.cognitive_maturity) or self.cognitive_maturity)
            self.current_environment.update(data.get("current_environment") or {})
            self.self_awareness_notes = list(data.get("self_awareness_notes") or self.self_awareness_notes)[-12:]
            # Phase 2 — PersonaEvolution
            self.persona_name = str(data.get("persona_name") or self.persona_name)
            self.adapted_style = str(data.get("adapted_style") or self.adapted_style)
            self.persona_evolution_log = list(data.get("persona_evolution_log") or self.persona_evolution_log)[-5:]
            self.relationship_depth = float(data.get("relationship_depth") or self.relationship_depth)
            self.shared_references = list(data.get("shared_references") or self.shared_references)[:20]
            logger.info(f"[SelfModelV5] Loaded {self.identity_name} v{self.identity_version} depth={self.relationship_depth:.3f}")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(self._build_snapshot())
        return base


def create_module() -> SelfModelModule:
    return SelfModelModule()
