"""Tier 1: Emotion Module — V4 affective appraisal layer.

This module keeps a richer emotional state than the old VAD-only version.
It still uses safe, bounded heuristics — not clinical claims — but it now gives
other modules a usable affective context for dialogue, monologue, memory tags,
and dashboard introspection.

Emits:
- emotion_changed        when the active emotion/state shifts enough
- emotional_state        periodic full affective profile
- emotional_tag          lightweight tag for memory/attention
- response_style_hint    guidance for the dialogue cortex

Listens:
- hormone_levels, sensory_input, memory_retrieved, user_utterance,
  response_generated, screen_parsed, screen_error, goal_achieved, goal_failed,
  action_denied, action_approved
"""
from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("emotion")

EMOTION_VAD_MAP: Dict[str, Dict[str, List[float]]] = {
    "joy": {"valence": [0.55, 1.0], "arousal": [0.35, 1.0], "dominance": [0.25, 1.0]},
    "sadness": {"valence": [-1.0, -0.25], "arousal": [0.0, 0.45], "dominance": [-1.0, 0.15]},
    "anger": {"valence": [-1.0, -0.2], "arousal": [0.65, 1.0], "dominance": [0.25, 1.0]},
    "fear": {"valence": [-1.0, -0.2], "arousal": [0.55, 1.0], "dominance": [-1.0, 0.15]},
    "surprise": {"valence": [-0.15, 0.45], "arousal": [0.55, 1.0], "dominance": [-0.1, 0.55]},
    "disgust": {"valence": [-0.85, -0.25], "arousal": [0.35, 0.8], "dominance": [-0.2, 0.8]},
    "anticipation": {"valence": [0.1, 0.75], "arousal": [0.45, 0.95], "dominance": [0.05, 0.75]},
    "trust": {"valence": [0.35, 1.0], "arousal": [0.15, 0.75], "dominance": [0.15, 1.0]},
    "curiosity": {"valence": [0.1, 0.7], "arousal": [0.35, 0.9], "dominance": [0.0, 0.65]},
    "focus": {"valence": [0.0, 0.55], "arousal": [0.25, 0.75], "dominance": [0.25, 1.0]},
    "relief": {"valence": [0.25, 0.85], "arousal": [-0.15, 0.45], "dominance": [0.1, 0.8]},
    "neutral": {"valence": [-0.2, 0.2], "arousal": [-0.2, 0.3], "dominance": [-0.2, 0.3]},
}

HORMONE_EMO_WEIGHTS: Dict[str, Dict[str, float]] = {
    "dopamine": {"valence": 0.45, "arousal": 0.25, "dominance": 0.15},
    "cortisol": {"valence": -0.55, "arousal": 0.45, "dominance": -0.30},
    "oxytocin": {"valence": 0.40, "arousal": -0.05, "dominance": 0.10},
    "serotonin": {"valence": 0.25, "arousal": -0.12, "dominance": 0.12},
    "adrenaline": {"valence": -0.15, "arousal": 0.75, "dominance": -0.20},
}

_POSITIVE_WORDS = {
    "good", "great", "nice", "thanks", "thank", "cool", "done", "works", "fixed",
    "добре", "круто", "дякую", "готово", "працює", "погнали", "супер", "красава",
    "норм", "нормально", "відмінно", "отлично", "спасибо",
}
_NEGATIVE_WORDS = {
    "bad", "error", "failed", "fail", "problem", "broken", "bug", "wrong", "crash",
    "помилка", "помилки", "не працює", "зламав", "баг", "проблема", "хрінь", "фігня",
    "ошибка", "не работает", "сломалось",
}
_URGENCY_WORDS = {
    "urgent", "now", "quick", "fast", "негайно", "швидко", "терміново", "срочно", "быстро", "зараз",
}
_CURIOUS_WORDS = {
    "why", "how", "what", "як", "чому", "що", "навіщо", "поясни", "давай", "можеш", "можна",
}


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _norm01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class AffectiveState:
    def __init__(self) -> None:
        self.emotion = "neutral"
        self.mood = "steady"
        self.valence = 0.0
        self.arousal = 0.0
        self.dominance = 0.0
        self.curiosity = 0.30
        self.frustration = 0.0
        self.confidence = 0.55
        self.social_warmth = 0.55
        self.cognitive_load = 0.20
        self.intensity = 0.0
        self.triggers: List[str] = []
        self.response_style = "calm-direct"
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "emotion": self.emotion,
            "mood": self.mood,
            "valence": self.valence,
            "arousal": self.arousal,
            "dominance": self.dominance,
            "curiosity": self.curiosity,
            "frustration": self.frustration,
            "confidence": self.confidence,
            "social_warmth": self.social_warmth,
            "cognitive_load": self.cognitive_load,
            "intensity": self.intensity,
            "triggers": list(self.triggers or [])[-8:],
            "response_style": self.response_style,
            "updated_at": self.updated_at,
        }


class EmotionModule(CognitiveModule):
    """Tier 1 emotion engine with V4 appraisal + response style hints."""

    MODULE_DESCRIPTION = "V4 affective appraisal — rich emotional state, mood drift, response style hints"
    MODULE_VERSION = "2.0.0"

    def __init__(self) -> None:
        super().__init__(module_id="emotion_module", cost={"cpu": 0.14, "gpu": 0.0, "ram": 0.08})
        self._kernel = None
        self.state = AffectiveState()
        self._mood_valence = 0.0
        self._mood_arousal = 0.0
        self._mood_dominance = 0.0
        self._last_signature = ""
        self._last_state_emit = 0.0
        self._state_emit_interval = 4.0
        self._decay_strength = 0.985

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        self._kernel = kernel
        cfg = getattr(getattr(kernel, "config", None), "emotion", None)
        if cfg is not None:
            self._state_emit_interval = float(getattr(cfg, "state_emit_interval", self._state_emit_interval))
            self._decay_strength = float(getattr(cfg, "decay_strength", self._decay_strength))
        self._load_state()
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "hormone_levels", "sensory_input", "memory_retrieved", "user_utterance",
                "response_generated", "screen_parsed", "screen_error", "goal_achieved", "goal_failed",
                "action_denied", "action_approved", "tts_error", "tts_spoken",
            ],
        )

    async def on_event(self, event: Event) -> None:
        dv, da, dd = 0.0, 0.0, 0.0
        curiosity = 0.0
        frustration = 0.0
        confidence = 0.0
        warmth = 0.0
        load = 0.0
        triggers: List[str] = []

        if event.type == "hormone_levels":
            dv, da, dd = self._compute_vad_from_hormones(event.data)
            triggers.append("hormonal_shift")
        elif event.type == "sensory_input":
            dv, da, dd = self._compute_vad_from_sensory(event.data)
            load += min(0.15, abs(da) * 0.2)
            triggers.append("sensory_input")
        elif event.type == "memory_retrieved":
            dv, da, dd = self._compute_vad_from_memory(event.data)
            confidence += 0.04 if self._has_relevant_memory(event.data) else -0.02
            triggers.append("memory_context")
        elif event.type == "user_utterance":
            vals = self._appraise_text(str(event.data.get("text", "") or ""))
            dv, da, dd = vals["valence"], vals["arousal"], vals["dominance"]
            curiosity += vals["curiosity"]
            frustration += vals["frustration"]
            warmth += vals["warmth"]
            load += vals["load"]
            triggers.extend(vals["triggers"])
        elif event.type == "response_generated":
            confidence += 0.03
            load -= 0.03
            triggers.append("answered")
        elif event.type == "screen_parsed":
            important = event.data.get("important_blocks") or []
            if important:
                dv -= 0.05
                da += 0.12
                curiosity += 0.10
                load += min(0.20, len(important) * 0.04)
                triggers.append("screen_issue_detected")
            else:
                curiosity += 0.04
                triggers.append("screen_read")
        elif event.type == "screen_error":
            dv -= 0.12
            da += 0.08
            frustration += 0.10
            confidence -= 0.05
            triggers.append("screen_error")
        elif event.type == "goal_achieved":
            dv += 0.35
            da += 0.12
            dd += 0.10
            confidence += 0.08
            triggers.append("goal_achieved")
        elif event.type == "goal_failed":
            dv -= 0.30
            da += 0.15
            dd -= 0.10
            frustration += 0.15
            confidence -= 0.08
            triggers.append("goal_failed")
        elif event.type == "action_denied":
            dv -= 0.08
            da += 0.08
            dd -= 0.05
            frustration += 0.10
            triggers.append("action_denied")
        elif event.type == "action_approved":
            dv += 0.05
            dd += 0.08
            confidence += 0.04
            triggers.append("action_approved")
        elif event.type == "tts_error":
            dv -= 0.05
            frustration += 0.06
            triggers.append("voice_output_issue")
        elif event.type == "tts_spoken":
            warmth += 0.02
            triggers.append("voice_output_ok")

        self._apply_delta(dv, da, dd, curiosity, frustration, confidence, warmth, load, triggers)
        self._maybe_emit_state(force=self._changed_enough())

    def update(self, dt: float) -> None:
        # Natural settling toward neutral but preserve slow mood.
        decay = self._decay_strength
        self.state.valence *= decay
        self.state.arousal *= decay
        self.state.dominance *= decay
        self.state.frustration *= 0.992
        self.state.cognitive_load *= 0.994
        self.state.curiosity = _norm01(self.state.curiosity * 0.996 + 0.0015)
        self.state.confidence = _norm01(self.state.confidence * 0.998 + 0.001)
        self._update_labels()

        self._mood_valence += (self.state.valence - self._mood_valence) * 0.006
        self._mood_arousal += (self.state.arousal - self._mood_arousal) * 0.006
        self._mood_dominance += (self.state.dominance - self._mood_dominance) * 0.006

        now = time.time()
        if now - self._last_state_emit >= self._state_emit_interval:
            self._maybe_emit_state(force=True)

    def _apply_delta(
        self,
        dv: float,
        da: float,
        dd: float,
        curiosity: float,
        frustration: float,
        confidence: float,
        warmth: float,
        load: float,
        triggers: List[str],
    ) -> None:
        self.state.valence = _clamp(self.state.valence * 0.82 + dv * 0.34)
        self.state.arousal = _clamp(self.state.arousal * 0.82 + da * 0.34)
        self.state.dominance = _clamp(self.state.dominance * 0.84 + dd * 0.30)
        self.state.curiosity = _norm01(self.state.curiosity + curiosity)
        self.state.frustration = _norm01(self.state.frustration + frustration)
        self.state.confidence = _norm01(self.state.confidence + confidence)
        self.state.social_warmth = _norm01(self.state.social_warmth + warmth)
        self.state.cognitive_load = _norm01(self.state.cognitive_load + load)
        if triggers:
            current = list(self.state.triggers or [])
            current.extend([t for t in triggers if t])
            self.state.triggers = current[-12:]
        self.state.updated_at = time.time()
        self._update_labels()

    def _update_labels(self) -> None:
        self.state.emotion = self._dominant_emotion()
        self.state.intensity = _norm01(
            (abs(self.state.valence) + abs(self.state.arousal) + abs(self.state.dominance)) / 3.0
            + self.state.frustration * 0.20
            + self.state.curiosity * 0.10
        )
        self.state.mood = self._mood_label()
        self.state.response_style = self._response_style()

    def _compute_vad_from_hormones(self, data: Dict[str, Any]) -> Tuple[float, float, float]:
        valence = arousal = dominance = 0.0
        hormones = data if isinstance(data, dict) else {}
        for hormone, level in hormones.items():
            if hormone in HORMONE_EMO_WEIGHTS:
                try:
                    level_f = float(level)
                except Exception:
                    continue
                valence += HORMONE_EMO_WEIGHTS[hormone]["valence"] * level_f
                arousal += HORMONE_EMO_WEIGHTS[hormone]["arousal"] * level_f
                dominance += HORMONE_EMO_WEIGHTS[hormone]["dominance"] * level_f
        return _clamp(valence), _clamp(arousal), _clamp(dominance)

    def _compute_vad_from_sensory(self, data: Dict[str, Any]) -> Tuple[float, float, float]:
        intensity = float(data.get("intensity", 0.0) or 0.0)
        valence_hint = float(data.get("valence_hint", 0.0) or 0.0)
        return _clamp(valence_hint * intensity), _clamp(intensity * 0.35), _clamp(intensity * 0.12)

    def _compute_vad_from_memory(self, data: Dict[str, Any]) -> Tuple[float, float, float]:
        valence = arousal = 0.0
        for key in ("episodic_recalls", "semantic_matches", "stm_recent"):
            for item in list(data.get(key) or [])[:6]:
                text = str(item).lower()
                if any(w in text for w in _POSITIVE_WORDS):
                    valence += 0.025
                if any(w in text for w in _NEGATIVE_WORDS):
                    valence -= 0.025
                    arousal += 0.025
        return _clamp(valence), _clamp(arousal), 0.0

    def _appraise_text(self, text: str) -> Dict[str, Any]:
        lower = text.lower()
        words = set(re.findall(r"[\w'’їієґа-яА-ЯёЁ]+", lower, flags=re.UNICODE))
        valence = arousal = dominance = 0.0
        curiosity = frustration = warmth = load = 0.0
        triggers: List[str] = []

        pos = sum(1 for w in _POSITIVE_WORDS if w in lower or w in words)
        neg = sum(1 for w in _NEGATIVE_WORDS if w in lower or w in words)
        urg = sum(1 for w in _URGENCY_WORDS if w in lower or w in words)
        cur = sum(1 for w in _CURIOUS_WORDS if w in lower or w in words)

        if pos:
            valence += min(0.22, 0.05 * pos)
            warmth += min(0.08, 0.02 * pos)
            triggers.append("positive_user_signal")
        if neg:
            valence -= min(0.28, 0.06 * neg)
            arousal += min(0.22, 0.04 * neg)
            frustration += min(0.18, 0.04 * neg)
            triggers.append("problem_signal")
        if urg:
            arousal += min(0.24, 0.06 * urg)
            load += min(0.15, 0.03 * urg)
            triggers.append("urgency_signal")
        if cur or "?" in text:
            curiosity += min(0.16, 0.04 * max(cur, 1))
            arousal += 0.03
            triggers.append("curiosity_signal")
        if len(text) > 800:
            load += 0.10
            arousal += 0.04
            triggers.append("large_context")
        if any(token in lower for token in ("дякую", "thanks", "спасибо")):
            warmth += 0.06
            valence += 0.06
            triggers.append("social_warmth")
        if any(token in lower for token in ("давай", "погнали", "робим", "почнем", "let's")):
            curiosity += 0.08
            dominance += 0.05
            triggers.append("collaboration_drive")

        return {
            "valence": _clamp(valence), "arousal": _clamp(arousal), "dominance": _clamp(dominance),
            "curiosity": curiosity, "frustration": frustration, "warmth": warmth, "load": load,
            "triggers": triggers or ["user_input"],
        }

    def _has_relevant_memory(self, data: Dict[str, Any]) -> bool:
        return any(data.get(k) for k in ("wm_snapshot", "stm_recent", "episodic_recalls", "semantic_matches"))

    def _dominant_emotion(self) -> str:
        # Special higher-level labels layered over VAD.
        if self.state.frustration > 0.55 and self.state.arousal > 0.25:
            return "frustration"
        if self.state.curiosity > 0.62 and self.state.valence >= -0.20:
            return "curiosity"
        if self.state.cognitive_load > 0.70:
            return "focus"

        best = "neutral"
        best_score = -1.0
        for emotion, ranges in EMOTION_VAD_MAP.items():
            val_mid = sum(ranges["valence"]) / 2.0
            aro_mid = sum(ranges["arousal"]) / 2.0
            dom_mid = sum(ranges["dominance"]) / 2.0
            dist = math.sqrt(
                (self.state.valence - val_mid) ** 2
                + (self.state.arousal - aro_mid) ** 2
                + (self.state.dominance - dom_mid) ** 2
            )
            score = 1.0 / (1.0 + dist)
            if score > best_score:
                best_score = score
                best = emotion
        return best

    def _mood_label(self) -> str:
        if self._mood_valence > 0.18 and self._mood_arousal < 0.45:
            return "warm-steady"
        if self._mood_valence > 0.12 and self._mood_arousal >= 0.45:
            return "energized"
        if self._mood_valence < -0.16 and self._mood_arousal >= 0.40:
            return "strained"
        if self._mood_valence < -0.14:
            return "low"
        if self._mood_arousal > 0.55:
            return "alert"
        return "steady"

    def _response_style(self) -> str:
        if self.state.frustration > 0.45:
            return "calm-problem-solving"
        if self.state.cognitive_load > 0.62:
            return "structured-stepwise"
        if self.state.curiosity > 0.60:
            return "curious-analytical"
        if self.state.social_warmth > 0.68:
            return "warm-direct"
        if self.state.arousal > 0.60:
            return "brief-decisive"
        return "calm-direct"

    def _changed_enough(self) -> bool:
        sig = f"{self.state.emotion}:{self.state.mood}:{round(self.state.valence,2)}:{round(self.state.arousal,2)}:{round(self.state.frustration,2)}"
        changed = sig != self._last_signature
        self._last_signature = sig
        return changed

    def _maybe_emit_state(self, force: bool = False) -> None:
        if not self.kernel:
            return
        now = time.time()
        if not force and now - self._last_state_emit < self._state_emit_interval:
            return
        self._last_state_emit = now
        data = self.state.to_dict()
        self.kernel.event_bus.emit(Event(type="emotional_state", data=data, source_module=self.module_id), Priority.BACKGROUND)
        self.kernel.event_bus.emit(Event(type="response_style_hint", data={"style": self.state.response_style, "affect": data}, source_module=self.module_id), Priority.BACKGROUND)
        self.kernel.event_bus.emit(
            Event(
                type="emotional_tag",
                data={
                    "tag": self.state.emotion,
                    "mood": self.state.mood,
                    "valence": self.state.valence,
                    "arousal": self.state.arousal,
                    "intensity": self.state.intensity,
                    "triggers": list(self.state.triggers or [])[-5:],
                },
                source_module=self.module_id,
            ),
            Priority.COGNITIVE,
        )
        if force:
            self.kernel.event_bus.emit(Event(type="emotion_changed", data=data, source_module=self.module_id), Priority.COGNITIVE)

    def _load_state(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("affective_state_v4")
        if isinstance(data, dict):
            for key in self.state.to_dict().keys():
                if key in data and key != "triggers":
                    try:
                        setattr(self.state, key, data[key])
                    except Exception:
                        pass
            self.state.triggers = list(data.get("triggers") or [])[-12:]
            self._mood_valence = float(data.get("mood_valence", self._mood_valence) or 0.0)
            self._mood_arousal = float(data.get("mood_arousal", self._mood_arousal) or 0.0)
            self._mood_dominance = float(data.get("mood_dominance", self._mood_dominance) or 0.0)
            logger.info("[Emotion] Loaded V4 affective state")

    def shutdown(self) -> None:
        if self.kernel:
            data = self.state.to_dict()
            data.update({
                "mood_valence": self._mood_valence,
                "mood_arousal": self._mood_arousal,
                "mood_dominance": self._mood_dominance,
            })
            self.kernel.persistence.save("affective_state_v4", data)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "emotion": self.state.emotion,
            "mood": self.state.mood,
            "valence": round(self.state.valence, 3),
            "arousal": round(self.state.arousal, 3),
            "dominance": round(self.state.dominance, 3),
            "curiosity": round(self.state.curiosity, 3),
            "frustration": round(self.state.frustration, 3),
            "confidence": round(self.state.confidence, 3),
            "social_warmth": round(self.state.social_warmth, 3),
            "cognitive_load": round(self.state.cognitive_load, 3),
            "response_style": self.state.response_style,
            "triggers": list(self.state.triggers or [])[-6:],
        })
        return base


def create_module() -> EmotionModule:
    return EmotionModule()
