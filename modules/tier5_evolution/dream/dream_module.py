"""Tier 5 Evolution: V6 Sleep / Dream / Memory Consolidation.

V6 turns the old random dream stub into an offline consolidation layer:
- collects recent dialogue, thoughts, screen observations and model events;
- can run automatically during idle/low-energy periods or manually by command;
- builds compact sleep reports, lessons, open loops and dream replay narratives;
- persists consolidation history to ~/.jarvis_brain/;
- emits events for memory/world/self-model modules.

This is intentionally safe: it does not modify code or execute actions. It only
summarises experience and emits bounded cognitive events.
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter, deque
from typing import Any, Deque, Dict, List, Tuple

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("dream")


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9_\-]{3,}")


class DreamModule(CognitiveModule):
    """V6 offline memory replay and consolidation module."""

    MODULE_DESCRIPTION = "V6 sleep/dream replay, lesson extraction and memory consolidation"
    MODULE_VERSION = "6.0.0"

    def __init__(self) -> None:
        super().__init__(module_id="dream", cost={"cpu": 0.08, "gpu": 0.0, "ram": 0.08})
        self._recent_events: Deque[Dict[str, Any]] = deque(maxlen=240)
        self._dialogue_pairs: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._open_loops: Deque[str] = deque(maxlen=40)
        self._lessons: Deque[Dict[str, Any]] = deque(maxlen=120)
        self._dreams: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._reports: Deque[Dict[str, Any]] = deque(maxlen=50)
        self._last_consolidation = 0.0
        self._last_dream = 0.0
        self._last_event_time = time.time()
        self._sleep_active = False
        self._last_report: Dict[str, Any] = {}

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        self._load()
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "kernel_started",
                "user_utterance",
                "response_generated",
                "dialogue_turn_completed",
                "thought_generated",
                "internal_monologue",
                "screen_parsed",
                "goal_achieved",
                "goal_failed",
                "action_denied",
                "safety_violation",
                "tts_error",
                "module_error",
                "memory_stored",
                "dream_request",
                "sleep_cycle_requested",
                "memory_consolidation_requested",
            ],
        )

    async def on_event(self, event: Event) -> None:
        et = event.type
        if et in {"dream_request", "sleep_cycle_requested", "memory_consolidation_requested"}:
            reason = str(event.data.get("reason") or et)
            force = bool(event.data.get("force", True))
            self._run_sleep_cycle(reason=reason, force=force, requested_by=event.source_module or "event")
            return

        self._last_event_time = time.time()
        self._remember_event(event)

        if et == "dialogue_turn_completed":
            self._dialogue_pairs.append({
                "timestamp": event.timestamp,
                "user": str(event.data.get("user_text", ""))[:1200],
                "assistant": str(event.data.get("assistant_text", ""))[:1600],
                "mode": event.data.get("mode", ""),
            })
            self._extract_open_loops(str(event.data.get("user_text", "")), str(event.data.get("assistant_text", "")))
        elif et in {"goal_failed", "module_error", "tts_error", "action_denied", "safety_violation"}:
            self._open_loops.append(self._event_to_sentence(event))
        elif et == "kernel_started":
            self._emit_sleep_state("awake", reason="kernel_started")

    async def tick(self, dt: float) -> None:
        self.update(dt)

    def update(self, dt: float) -> None:
        if not self.kernel:
            return
        cfg = self._cfg()
        if not self._cfg_bool("enabled", True):
            return

        now = time.time()
        idle_for = now - self._last_event_time
        energy = float(getattr(getattr(self.kernel, "core_state", None), "energy_level", 0.85) or 0.85)
        interval = self._cfg_float("auto_interval", 900.0)
        idle_threshold = self._cfg_float("idle_threshold", 90.0)
        energy_threshold = self._cfg_float("energy_threshold", 0.38)

        should_auto = bool(getattr(cfg, "auto_enabled", True))
        due = (now - self._last_consolidation) >= interval
        idle_or_tired = idle_for >= idle_threshold or energy <= energy_threshold
        if should_auto and due and idle_or_tired and len(self._recent_events) >= 5:
            self._run_sleep_cycle(reason="auto_idle_or_low_energy", force=False, requested_by="dream_tick")

    def _remember_event(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"value": str(event.data)}
        self._recent_events.append({
            "id": event._id,
            "type": event.type,
            "source": event.source_module,
            "timestamp": event.timestamp,
            "data": self._compact_data(data, limit=1400),
        })

    def _run_sleep_cycle(self, reason: str, force: bool = False, requested_by: str = "") -> Dict[str, Any]:
        now = time.time()
        min_gap = self._cfg_float("manual_min_gap", 3.0)
        if not force and now - self._last_consolidation < min_gap:
            return self._last_report

        self._sleep_active = True
        self._emit_sleep_state("sleeping", reason=reason)

        events = list(self._recent_events)[-self._cfg_int("max_replay_events", 80):]
        dialogues = list(self._dialogue_pairs)[-self._cfg_int("max_dialogue_pairs", 24):]
        themes = self._extract_themes(events, dialogues)
        lessons = self._extract_lessons(events, dialogues, themes)
        dream = self._build_dream_replay(events, dialogues, themes, lessons)
        report = self._build_report(reason, requested_by, events, dialogues, themes, lessons, dream)

        for lesson in lessons:
            self._lessons.append(lesson)
        self._dreams.append(dream)
        self._reports.append(report)
        self._last_report = report
        self._last_consolidation = now
        self._last_dream = now
        self._sleep_active = False
        self._save()
        self._emit_results(report, dream, lessons)
        self._emit_sleep_state("awake", reason="cycle_complete")
        logger.info("[Dream V6] sleep cycle complete: %s lesson(s), %s theme(s)", len(lessons), len(themes))
        return report

    def _extract_themes(self, events: List[Dict[str, Any]], dialogues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stop = {
            "the", "and", "for", "with", "that", "this", "from", "have", "what", "when", "then", "into",
            "тобі", "мені", "треба", "буде", "може", "давай", "добре", "зробим", "зробити", "далі",
            "що", "як", "для", "але", "цей", "він", "вона", "вони", "його", "поки", "після", "через",
            "это", "как", "что", "для", "или", "если", "надо", "будет", "можно", "сделать",
        }
        counter: Counter[str] = Counter()
        for ev in events:
            text = self._flatten(ev.get("data", {}))
            counter.update(w.lower() for w in _WORD_RE.findall(text) if w.lower() not in stop)
        for turn in dialogues:
            text = f"{turn.get('user', '')} {turn.get('assistant', '')}"
            counter.update(w.lower() for w in _WORD_RE.findall(text) if w.lower() not in stop)
        themes = []
        for word, count in counter.most_common(12):
            if count >= 2:
                themes.append({"theme": word, "weight": count})
        return themes[:8]

    def _extract_lessons(
        self,
        events: List[Dict[str, Any]],
        dialogues: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        lessons: List[Dict[str, Any]] = []
        event_types = Counter(ev.get("type", "unknown") for ev in events)
        error_events = [ev for ev in events if ev.get("type") in {"module_error", "tts_error", "goal_failed", "action_denied", "safety_violation"}]
        user_turns = [d.get("user", "") for d in dialogues if d.get("user")]

        if dialogues:
            lessons.append({
                "type": "dialogue_summary",
                "confidence": 0.72,
                "summary": self._summarize_dialogues(dialogues),
                "evidence_count": len(dialogues),
            })
        if themes:
            lessons.append({
                "type": "theme_summary",
                "confidence": 0.68,
                "summary": "Recent recurring themes: " + ", ".join(t["theme"] for t in themes[:6]),
                "themes": themes[:6],
            })
        if error_events:
            lessons.append({
                "type": "stability_lesson",
                "confidence": 0.78,
                "summary": f"There were {len(error_events)} reliability/safety events; keep failures visible and prefer graceful fallback.",
                "events": [self._event_to_sentence_dict(ev) for ev in error_events[-5:]],
            })
        if any("пам" in t.lower() or "memory" in t.lower() for t in user_turns):
            lessons.append({
                "type": "user_preference",
                "confidence": 0.64,
                "summary": "User is actively prioritising persistent memory and consolidation quality.",
            })
        if any("голос" in t.lower() or "voice" in t.lower() or "tts" in t.lower() for t in user_turns):
            lessons.append({
                "type": "user_preference",
                "confidence": 0.66,
                "summary": "Voice dialogue remains important; preserve Piper first with pyttsx3 fallback.",
            })
        if event_types:
            lessons.append({
                "type": "runtime_pattern",
                "confidence": 0.61,
                "summary": "Runtime event mix: " + ", ".join(f"{k}:{v}" for k, v in event_types.most_common(6)),
            })

        # Deduplicate by summary against recent lessons.
        existing = {str(l.get("summary", "")).lower() for l in self._lessons}
        unique = []
        for lesson in lessons:
            key = str(lesson.get("summary", "")).lower()
            if key and key not in existing:
                unique.append(lesson)
                existing.add(key)
        return unique[: self._cfg_int("max_lessons_per_cycle", 8)]

    def _build_dream_replay(
        self,
        events: List[Dict[str, Any]],
        dialogues: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        lessons: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fragments: List[str] = []
        if dialogues:
            for turn in dialogues[-3:]:
                user = str(turn.get("user", "")).strip()
                if user:
                    fragments.append(f"User focus: {user[:180]}")
        for ev in events[-6:]:
            if ev.get("type") in {"screen_parsed", "goal_failed", "tts_error", "safety_violation", "internal_monologue"}:
                fragments.append(self._event_to_sentence_dict(ev))
        if not fragments and events:
            fragments = [self._event_to_sentence_dict(ev) for ev in events[-4:]]

        theme_text = ", ".join(t.get("theme", "") for t in themes[:5]) or "continuity"
        lesson_text = "; ".join(str(l.get("summary", ""))[:180] for l in lessons[:3]) or "no strong lesson yet"
        narrative = (
            f"A replay links recent fragments around {theme_text}. "
            f"The strongest consolidation lesson is: {lesson_text}. "
            "The system should carry this forward as context, not as absolute truth."
        )
        return {
            "timestamp": time.time(),
            "narrative": narrative,
            "themes": themes[:6],
            "fragments": fragments[:8],
            "intensity": min(1.0, 0.25 + 0.08 * len(fragments) + 0.05 * len(lessons)),
        }

    def _build_report(
        self,
        reason: str,
        requested_by: str,
        events: List[Dict[str, Any]],
        dialogues: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        lessons: List[Dict[str, Any]],
        dream: Dict[str, Any],
    ) -> Dict[str, Any]:
        open_loops = list(self._open_loops)[-10:]
        summary = self._make_report_summary(events, dialogues, themes, lessons, open_loops)
        return {
            "timestamp": time.time(),
            "reason": reason,
            "requested_by": requested_by,
            "summary": summary,
            "events_replayed": len(events),
            "dialogue_turns_replayed": len(dialogues),
            "themes": themes,
            "lessons": lessons,
            "open_loops": open_loops,
            "dream": dream,
            "status": "consolidated",
        }

    def _make_report_summary(
        self,
        events: List[Dict[str, Any]],
        dialogues: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        lessons: List[Dict[str, Any]],
        open_loops: List[str],
    ) -> str:
        parts = [f"Replayed {len(events)} events and {len(dialogues)} dialogue turns."]
        if themes:
            parts.append("Main themes: " + ", ".join(t["theme"] for t in themes[:5]) + ".")
        if lessons:
            parts.append("Lessons: " + " ".join(str(l.get("summary", ""))[:220] for l in lessons[:3]))
        if open_loops:
            parts.append(f"Open loops remaining: {len(open_loops)}.")
        return " ".join(parts)

    def _emit_results(self, report: Dict[str, Any], dream: Dict[str, Any], lessons: List[Dict[str, Any]]) -> None:
        if not self.kernel:
            return
        bus = self.kernel.event_bus
        bus.emit(Event(type="dream_narrative", data=dream, source_module=self.module_id), Priority.BACKGROUND)
        bus.emit(Event(type="memory_consolidated", data=report, source_module=self.module_id), Priority.COGNITIVE)
        bus.emit(Event(type="sleep_cycle_completed", data=report, source_module=self.module_id), Priority.COGNITIVE)
        for lesson in lessons:
            bus.emit(Event(type="consolidation_lesson", data=lesson, source_module=self.module_id), Priority.BACKGROUND)
            # Also make the lesson visible to the existing memory module without new direct APIs.
            bus.emit(Event(type="thought_generated", data={"text": "Consolidation lesson: " + str(lesson.get("summary", "")), "importance": 0.72}, source_module=self.module_id), Priority.BACKGROUND)
        if lessons:
            bus.emit(Event(type="learning_applied", data={"summary": report.get("summary", ""), "lesson_count": len(lessons)}, source_module=self.module_id), Priority.BACKGROUND)

    def _emit_sleep_state(self, state: str, reason: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="sleep_state_changed",
                    data={
                        "state": state,
                        "reason": reason,
                        "sleep_active": self._sleep_active,
                        "last_consolidation": self._last_consolidation,
                    },
                    source_module=self.module_id,
                ),
                Priority.BACKGROUND,
            )

    def _extract_open_loops(self, user_text: str, assistant_text: str) -> None:
        combined = f"{user_text}\n{assistant_text}".lower()
        markers = ["далі", "next", "todo", "потрібно", "need", "потім", "planned", "заплан", "open loop"]
        if any(m in combined for m in markers):
            text = user_text.strip() or assistant_text.strip()
            if text:
                self._open_loops.append(text[:280])

    def _summarize_dialogues(self, dialogues: List[Dict[str, Any]]) -> str:
        if not dialogues:
            return "No dialogue turns available for consolidation."
        first = dialogues[0].get("user", "")[:160]
        last = dialogues[-1].get("user", "")[:220]
        return f"Dialogue moved from '{first}' toward '{last}', with {len(dialogues)} consolidated turn(s)."

    def _event_to_sentence(self, event: Event) -> str:
        return f"{event.type}: {self._flatten(event.data)[:260]}"

    def _event_to_sentence_dict(self, ev: Dict[str, Any]) -> str:
        return f"{ev.get('type')}: {self._flatten(ev.get('data', {}))[:260]}"

    def _compact_data(self, value: Any, limit: int = 1000) -> Any:
        if isinstance(value, dict):
            return {str(k): self._compact_data(v, max(120, limit // max(1, len(value)))) for k, v in list(value.items())[:16]}
        if isinstance(value, list):
            return [self._compact_data(v, max(120, limit // max(1, len(value)))) for v in value[:10]]
        text = str(value)
        return text[:limit]

    def _flatten(self, value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(f"{k}: {self._flatten(v)}" for k, v in value.items())
        if isinstance(value, list):
            return " ".join(self._flatten(v) for v in value)
        return str(value)

    def _cfg(self) -> Any:
        return getattr(getattr(self.kernel, "config", None), "sleep", None) if self.kernel else None

    def _cfg_float(self, name: str, default: float) -> float:
        cfg = self._cfg()
        return float(getattr(cfg, name, default) if cfg is not None else default)

    def _cfg_int(self, name: str, default: int) -> int:
        cfg = self._cfg()
        return int(getattr(cfg, name, default) if cfg is not None else default)

    def _cfg_bool(self, name: str, default: bool) -> bool:
        cfg = self._cfg()
        return bool(getattr(cfg, name, default) if cfg is not None else default)

    def _load(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("dream_v6_state")
        if not isinstance(data, dict):
            return
        for attr, key in (("_lessons", "lessons"), ("_dreams", "dreams"), ("_reports", "reports"), ("_open_loops", "open_loops")):
            values = data.get(key)
            if isinstance(values, list):
                dq = getattr(self, attr)
                dq.clear()
                dq.extend(values[-dq.maxlen:])
        self._last_consolidation = float(data.get("last_consolidation", 0.0) or 0.0)
        self._last_dream = float(data.get("last_dream", 0.0) or 0.0)
        self._last_report = data.get("last_report") if isinstance(data.get("last_report"), dict) else {}

    def _save(self) -> None:
        if not self.kernel:
            return
        self.kernel.persistence.save(
            "dream_v6_state",
            {
                "last_consolidation": self._last_consolidation,
                "last_dream": self._last_dream,
                "last_report": self._last_report,
                "lessons": list(self._lessons),
                "dreams": list(self._dreams),
                "reports": list(self._reports),
                "open_loops": list(self._open_loops),
            },
        )

    def shutdown(self) -> None:
        self._save()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "v6_sleep_active": self._sleep_active,
            "last_consolidation": self._last_consolidation,
            "last_dream": self._last_dream,
            "recent_events": len(self._recent_events),
            "dialogue_pairs": len(self._dialogue_pairs),
            "lessons": len(self._lessons),
            "dreams": len(self._dreams),
            "open_loops": list(self._open_loops)[-5:],
            "last_report": self._last_report,
        })
        return base


def create_module():
    return DreamModule()
