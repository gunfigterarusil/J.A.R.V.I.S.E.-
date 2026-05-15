"""Tier 3 Reasoning: Internal Monologue Module — V4 deep monologue.

The monologue is now more than random idle phrases. It keeps a small internal
thread of appraisal, uncertainties, active goals, screen observations, and
recent dialogue. It emits both compact thoughts and a richer monologue state
that the web UI / memory / future sleep system can use.

Emits:
  - internal_monologue
  - monologue_state

Listens:
  - wm_updated, emotional_state, response_style_hint, goal_activated,
    goal_achieved, goal_failed, user_utterance, response_generated,
    screen_parsed, screen_error, theory_generated, imagination_complete,
    idle_detected, context_request
"""
from __future__ import annotations

import logging
import random
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("monologue")

_IDLE_PHRASES = [
    "Holding a quiet baseline and waiting for the next useful signal.",
    "Rechecking recent context so the next answer can be more coherent.",
    "No urgent input; keeping attention available without inventing tasks.",
    "Letting the recent dialogue settle into memory.",
]

_EMOTION_LINES = {
    "joy": "There is a positive signal here; keep momentum without getting sloppy.",
    "sadness": "The tone is low; respond carefully and avoid forcing optimism.",
    "anger": "Tension is present; lower the heat and focus on the next fix.",
    "fear": "Uncertainty is high; be cautious and verify before acting.",
    "surprise": "Unexpected information appeared; pause and re-evaluate assumptions.",
    "anticipation": "The direction is opening; prepare the next step clearly.",
    "trust": "The interaction feels stable; be direct and useful.",
    "curiosity": "Curiosity is active; explore, but keep the answer grounded.",
    "focus": "Cognitive load is high; structure the response step by step.",
    "frustration": "Friction is present; reduce complexity and give a concrete path.",
    "neutral": "Stay balanced and practical.",
}


class MonologueModule(CognitiveModule):
    """Generates richer internal self-narration and exposes monologue state."""

    MODULE_DESCRIPTION = "V4 deep monologue — context-aware self narration with affect, goals, uncertainty"
    MODULE_VERSION = "2.0.0"

    def __init__(self) -> None:
        super().__init__(module_id="monologue", cost={"cpu": 0.06, "gpu": 0.0, "ram": 0.04})
        self.buffer: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._last_emit = 0.0
        self._interval = 6.0
        self._current_affect: Dict[str, Any] = {"emotion": "neutral", "mood": "steady", "response_style": "calm-direct"}
        self._style_hint: str = "calm-direct"
        self._active_goals: Deque[str] = deque(maxlen=8)
        self._recent_dialogue: Deque[Dict[str, str]] = deque(maxlen=8)
        self._wm_snapshot: List[Any] = []
        self._latest_theory: Optional[str] = None
        self._latest_screen: Optional[str] = None
        self._open_questions: Deque[str] = deque(maxlen=8)
        self._focus_stack: Deque[str] = deque(maxlen=8)
        self._last_user_text: str = ""
        self._last_assistant_text: str = ""

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(getattr(kernel, "config", None), "monologue", None)
        if cfg is not None:
            self._interval = float(getattr(cfg, "interval", self._interval))
        self._load_state()
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "wm_updated", "emotional_state", "response_style_hint", "goal_activated",
                "goal_achieved", "goal_failed", "idle_detected", "kernel_started",
                "theory_generated", "imagination_complete", "user_utterance",
                "response_generated", "screen_parsed", "screen_error", "context_request",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "wm_updated":
            self._wm_snapshot = event.data.get("snapshot", []) or []
        elif event.type == "emotional_state":
            self._current_affect = dict(event.data or {})
            self._style_hint = self._current_affect.get("response_style", self._style_hint)
        elif event.type == "response_style_hint":
            self._style_hint = str(event.data.get("style", self._style_hint))
            affect = event.data.get("affect")
            if isinstance(affect, dict):
                self._current_affect.update(affect)
        elif event.type == "goal_activated":
            desc = event.data.get("description") or event.data.get("goal") or event.data.get("title") or ""
            self._remember_goal(str(desc))
            self._emit_monologue(reason="goal", priority=Priority.COGNITIVE)
        elif event.type == "goal_achieved":
            desc = event.data.get("description") or event.data.get("goal") or "a goal"
            self._focus_stack.append(f"Completed: {str(desc)[:120]}")
            self._emit_monologue(reason="goal_achieved", priority=Priority.COGNITIVE)
        elif event.type == "goal_failed":
            desc = event.data.get("description") or event.data.get("goal") or "a goal"
            self._open_questions.append(f"Why did {str(desc)[:90]} fail, and what is the safer retry?")
            self._emit_monologue(reason="goal_failed", priority=Priority.COGNITIVE)
        elif event.type == "idle_detected" or event.type == "kernel_started":
            self._emit_monologue(reason="idle", introspective=True)
        elif event.type == "theory_generated":
            stmt = event.data.get("statement", event.data.get("theory", ""))
            if stmt:
                self._latest_theory = str(stmt)[:180]
        elif event.type == "imagination_complete":
            theories = event.data.get("theories", []) or []
            if theories and isinstance(theories[0], dict):
                best = theories[0].get("statement", theories[0].get("theory", ""))
                if best:
                    self._latest_theory = f"Best current theory: {str(best)[:160]}"
        elif event.type == "user_utterance":
            text = str(event.data.get("text", "") or "").strip()
            self._last_user_text = text
            if text:
                self._recent_dialogue.append({"role": "user", "text": text[:500]})
                if "?" in text or any(w in text.lower() for w in ("як", "чому", "що", "why", "how", "what")):
                    self._open_questions.append(text[:180])
                self._focus_stack.append(f"User intent: {text[:140]}")
                self._emit_monologue(reason="user_input", priority=Priority.COGNITIVE)
        elif event.type == "response_generated":
            text = str(event.data.get("text", "") or "").strip()
            self._last_assistant_text = text
            if text:
                self._recent_dialogue.append({"role": "assistant", "text": text[:500]})
                self._focus_stack.append(f"Answered: {text[:120]}")
        elif event.type == "screen_parsed":
            summary = str(event.data.get("summary") or "")
            important = event.data.get("important_blocks") or []
            self._latest_screen = summary[:220] if summary else self._compact(important)[:220]
            if important:
                self._open_questions.append("Screen contains notable blocks; explain or fix the highest-impact one.")
            self._emit_monologue(reason="screen", priority=Priority.COGNITIVE)
        elif event.type == "screen_error":
            self._latest_screen = f"Screen reading failed: {event.data.get('error', 'unknown error')}"
            self._open_questions.append("Why did screen reading fail, and what dependency or permission is missing?")
            self._emit_monologue(reason="screen_error", priority=Priority.COGNITIVE)
        elif event.type == "context_request":
            self._emit_state()

    def update(self, dt: float) -> None:
        now = time.time()
        if now - self._last_emit >= self._interval:
            self._emit_monologue(reason="heartbeat")

    def _remember_goal(self, desc: str) -> None:
        desc = desc.strip()
        if desc and desc not in self._active_goals:
            self._active_goals.append(desc[:180])

    def _emit_monologue(self, reason: str = "heartbeat", introspective: bool = False, priority: Priority = Priority.BACKGROUND) -> None:
        self._last_emit = time.time()
        text = self._compose(reason=reason, introspective=introspective)
        item = {
            "text": text,
            "reason": reason,
            "emotion": self._current_affect.get("emotion", "neutral"),
            "mood": self._current_affect.get("mood", "steady"),
            "style": self._style_hint,
            "timestamp": time.time(),
        }
        self.buffer.append(item)
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="internal_monologue", data=item, source_module=self.module_id), priority)
            self._emit_state()
            logger.debug(f"[Monologue] {text}")

    def _compose(self, reason: str, introspective: bool) -> str:
        emotion = str(self._current_affect.get("emotion", "neutral"))
        mood = str(self._current_affect.get("mood", "steady"))
        style = str(self._style_hint or "calm-direct")
        parts: List[str] = []

        if reason == "user_input" and self._last_user_text:
            parts.append(f"The user is steering the project: {self._last_user_text[:150]}")
        elif reason == "screen" and self._latest_screen:
            parts.append(f"Visual context entered working thought: {self._latest_screen}")
        elif reason == "goal_failed":
            parts.append("A goal failed; convert friction into a safer next step.")
        elif introspective:
            parts.append(random.choice(_IDLE_PHRASES))

        if self._active_goals:
            parts.append(f"Active aim: {self._active_goals[-1]}")
        elif self._focus_stack:
            parts.append(f"Focus: {self._focus_stack[-1]}")

        parts.append(f"Affect: {emotion}/{mood}; response style should be {style}.")
        parts.append(_EMOTION_LINES.get(emotion, _EMOTION_LINES["neutral"]))

        if self._open_questions:
            parts.append(f"Open question: {self._open_questions[-1]}")
        if self._latest_theory:
            parts.append(self._latest_theory)
            self._latest_theory = None
        if self._wm_snapshot:
            wm_item = self._compact(self._wm_snapshot[-1])
            if wm_item:
                parts.append(f"Working memory keeps: {wm_item[:140]}")

        # Keep the monologue readable and not too huge.
        return " | ".join([p for p in parts if p])[:900]

    def _emit_state(self) -> None:
        if not self.kernel:
            return
        self.kernel.event_bus.emit(
            Event(
                type="monologue_state",
                data={
                    "latest": self.buffer[-1] if self.buffer else None,
                    "buffer": list(self.buffer)[-10:],
                    "active_goals": list(self._active_goals),
                    "open_questions": list(self._open_questions),
                    "focus_stack": list(self._focus_stack)[-6:],
                    "affect": dict(self._current_affect),
                    "style_hint": self._style_hint,
                },
                source_module=self.module_id,
            ),
            Priority.BACKGROUND,
        )

    def _compact(self, value: Any) -> str:
        if isinstance(value, list):
            return "; ".join(self._compact(v) for v in value[:3])
        if isinstance(value, dict):
            data = value.get("data", value.get("item", value.get("experience", value)))
            if data is not value:
                return self._compact(data)
            for key in ("text", "summary", "raw_text", "description", "title"):
                if key in value and value[key]:
                    return str(value[key]).replace("\n", " ").strip()
        return str(value).replace("\n", " ").strip()

    def _load_state(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("monologue_state_v4")
        if isinstance(data, dict):
            for item in data.get("buffer", [])[-self.buffer.maxlen:]:
                if isinstance(item, dict) and item.get("text"):
                    self.buffer.append(item)
            for goal in data.get("active_goals", [])[-8:]:
                self._active_goals.append(str(goal))
            for q in data.get("open_questions", [])[-8:]:
                self._open_questions.append(str(q))
            for f in data.get("focus_stack", [])[-8:]:
                self._focus_stack.append(str(f))
            logger.info(f"[Monologue] Loaded {len(self.buffer)} V4 monologue item(s)")

    def shutdown(self) -> None:
        if self.kernel:
            self.kernel.persistence.save(
                "monologue_state_v4",
                {
                    "buffer": list(self.buffer),
                    "active_goals": list(self._active_goals),
                    "open_questions": list(self._open_questions),
                    "focus_stack": list(self._focus_stack),
                },
            )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "buffer_size": len(self.buffer),
            "latest": self.buffer[-1] if self.buffer else None,
            "current_emotion": self._current_affect.get("emotion", "neutral"),
            "mood": self._current_affect.get("mood", "steady"),
            "style_hint": self._style_hint,
            "active_goals": list(self._active_goals),
            "open_questions": list(self._open_questions)[-4:],
        })
        return base


def create_module() -> MonologueModule:
    return MonologueModule()
