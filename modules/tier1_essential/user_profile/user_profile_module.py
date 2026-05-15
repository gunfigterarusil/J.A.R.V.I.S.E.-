"""Tier 1 Essential: UserProfileEngine (Phase 2 — Character)

Learns who the user is through natural conversation:
  - Extracts name from first-mention patterns
  - Detects preferred language (uk / ru / en) from Cyrillic/Latin ratio
  - Tracks communication style metrics (formality, verbosity, technical level, humor)
  - Discovers interests and active projects from repeated topics
  - Generates plain-language persona_notes via LLM analysis (every N conversations)
  - Tracks relationship milestones and depth

All data is local: ~/.jarvis_brain/user_profile.json
Data can be copied to USB — no cloud, no lock-in.

Emits:
  user_profile_updated  — when any profile field changes (batched, max 1/turn)

Listens:
  user_utterance         — each user message (source of all learning)
  dialogue_turn_completed — increments conversation counter, triggers persona_notes update
  world_model_updated    — pulls user_intents for interests
  memory_retrieved       — pulls social_profile for initial seeding
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("user_profile")

# ── Name extraction ────────────────────────────────────────────────────────────
_NAME_RE = re.compile(
    r'(?:мене\s+звуть|мене\s+звати|мене\s+кличуть|я\s*[-—]\s*|my\s+name\s+is|i\'?m\s+called|call\s+me|меня\s+зовут)\s+'
    r'([А-ЯІЄЇ][а-яієї]{1,19}|[A-Z][a-z]{1,19})',
    re.IGNORECASE,
)

# ── Language detection ─────────────────────────────────────────────────────────
_UK_MARKERS = re.compile(r'[іїє]', re.IGNORECASE)   # letters unique to Ukrainian
_CYRILLIC = re.compile(r'[а-яёА-ЯЁіїєІЇЄ]')
_LATIN = re.compile(r'[a-zA-Z]')

# ── Style signals ──────────────────────────────────────────────────────────────
_FORMAL_RE = re.compile(r'\b(будь\s+ласка|пожалуйста|please|could\s+you|would\s+you|вибачте|пробачте)\b', re.I)
_HUMOR_RE = re.compile(r'[😂🤣😄😁:D;)xD]|(?:хаха|хехе|lol|lmao|kek)', re.I)
_QUESTION_RE = re.compile(r'\?')
_CODE_RE = re.compile(r'`|```|def |class |import |function\s*\(|const |let |var ', re.I)

# ── Shared reference extraction ────────────────────────────────────────────────
_PROJECT_CONTEXT_RE = re.compile(
    r'\b(проект|project|задача|task|репо|repo|система|system|бот|bot|сервер|server)\s+'
    r'([A-ZА-ЯЄІЇa-zа-яєії][A-ZА-ЯЄІЇa-zа-яєії0-9_\-]{1,24})',
    re.IGNORECASE,
)


def _detect_language(text: str) -> Optional[str]:
    """Detect language from a single utterance. Returns 'uk', 'ru', or 'en'."""
    words = text.split()
    if not words:
        return None
    cyrillic = sum(1 for w in words if _CYRILLIC.search(w))
    latin = sum(1 for w in words if _LATIN.search(w))
    if cyrillic == 0 and latin == 0:
        return None
    if cyrillic / max(1, cyrillic + latin) > 0.5:
        uk_markers = len(_UK_MARKERS.findall(text))
        return "uk" if uk_markers > 0 else "ru"
    return "en"


def _score_formality(text: str) -> float:
    """Return 0..1 formality signal from a single message."""
    if not text:
        return 0.5
    score = 0.5
    if _FORMAL_RE.search(text):
        score += 0.25
    if text[0:1].islower() and len(text) < 40:
        score -= 0.15
    return max(0.0, min(1.0, score))


def _score_verbosity(text: str) -> float:
    """0=very short, 1=very long."""
    n = len(text.strip())
    if n < 30:
        return 0.1
    if n < 80:
        return 0.3
    if n < 200:
        return 0.55
    return min(1.0, 0.55 + (n - 200) / 1000)


def _score_technical(text: str) -> float:
    """0=casual, 1=technical."""
    if _CODE_RE.search(text):
        return 0.85
    technical_words = len(re.findall(
        r'\b(api|sdk|backend|frontend|database|функція|функция|метод|модуль|module|алгоритм|algorithm|мікросервіс|docker|kubernetes|git|npm|pip)\b',
        text, re.I
    ))
    return min(1.0, technical_words * 0.2)


def _score_humor(text: str) -> float:
    """0=serious, 1=humor welcomed."""
    return 0.9 if _HUMOR_RE.search(text) else 0.1


def _ema(old: float, new: float, alpha: float = 0.15) -> float:
    """Exponential moving average for gradual style metric update."""
    return old * (1.0 - alpha) + new * alpha


class UserProfileModule(CognitiveModule):
    """Learns and persists a user profile that shapes JAV's adaptive character."""

    MODULE_DESCRIPTION = "Phase 2 UserProfileEngine — learns user name, language, style, and interests"
    MODULE_VERSION = "2.0.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="user_profile",
            cost={"cpu": 0.04, "gpu": 0.0, "ram": 0.04},
        )
        # ── Profile data ─────────────────────────────────────────────────
        self.name: str = ""
        self.preferred_language: str = "uk"
        self.communication: Dict[str, float] = {
            "formality": 0.4,
            "verbosity": 0.4,
            "technical_level": 0.3,
            "humor_appreciation": 0.2,
        }
        self.interests: List[str] = []
        self.active_projects: List[str] = []
        self.persona_notes: str = ""
        self.relationship: Dict[str, Any] = {
            "total_conversations": 0,
            "total_messages": 0,
            "first_session_ts": 0.0,
            "known_since_days": 0,
            "milestones": [],
        }

        # ── Runtime state ────────────────────────────────────────────────
        self._language_votes: Dict[str, int] = {"uk": 0, "ru": 0, "en": 0}
        self._turn_messages: List[str] = []   # messages in current turn (for persona_notes)
        self._recent_messages: List[str] = []  # rolling window for persona_notes LLM call
        self._dirty: bool = False
        self._persona_notes_requested: bool = False
        self._notes_request_turn_id: str = ""
        self._cfg_enabled: bool = True
        self._cfg_auto_extract: bool = True
        self._cfg_notes_every: int = 5
        self._last_emit_ts: float = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(getattr(kernel, "config", None), "persona", None)
        if cfg:
            self._cfg_enabled = bool(getattr(cfg, "enabled", True))
            self._cfg_auto_extract = bool(getattr(cfg, "auto_extract_name", True))
            self._cfg_notes_every = int(getattr(cfg, "persona_notes_update_every", 5))
            # Override persona_name from config (rarely needed)
            forced_name = str(getattr(cfg, "persona_name", "") or "").strip()
            if forced_name and not self.name:
                self.name = forced_name

        self._load()

        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "user_utterance",
                "dialogue_turn_completed",
                "world_model_updated",
                "memory_retrieved",
                "response_generated",    # for persona_notes async result
            ],
        )

        if not self._cfg_enabled:
            logger.info("[UserProfile] Disabled via config.")

    def shutdown(self) -> None:
        self._save()

    # ─────────────────────────────────────────────────────────────────────────
    # Event handling
    # ─────────────────────────────────────────────────────────────────────────

    async def on_event(self, event: Event) -> None:
        if not self._cfg_enabled:
            return
        et = event.type

        if et == "user_utterance":
            text = str(event.data.get("text", "") or "").strip()
            if text:
                self._process_utterance(text)

        elif et == "dialogue_turn_completed":
            self._on_turn_completed(event.data)

        elif et == "world_model_updated":
            self._pull_interests_from_world(event.data)

        elif et == "memory_retrieved":
            profile = event.data.get("social_profile")
            if isinstance(profile, dict) and profile:
                self._seed_from_social_profile(profile)

        elif et == "response_generated":
            # Persona-notes LLM call result arrives here if it was routed through
            # the normal response pipeline with a special marker.
            if event.data.get("_persona_notes_update") and event.data.get("_request_id") == self._notes_request_turn_id:
                notes = str(event.data.get("text", "") or "").strip()
                if notes and notes != self.persona_notes:
                    self.persona_notes = notes[:500]
                    logger.info("[UserProfile] persona_notes updated: %s", notes[:80])
                    self._dirty = True
                    self._emit_updated()
                self._persona_notes_requested = False

    # ─────────────────────────────────────────────────────────────────────────
    # Core learning
    # ─────────────────────────────────────────────────────────────────────────

    def _process_utterance(self, text: str) -> None:
        changed = False

        # Name extraction (only if not yet known)
        if self._cfg_auto_extract and not self.name:
            m = _NAME_RE.search(text)
            if m:
                candidate = m.group(1).strip().capitalize()
                if len(candidate) >= 2:
                    self.name = candidate
                    logger.info("[UserProfile] Extracted name: %s", self.name)
                    changed = True
                    self._add_milestone("first_name_learned", f"name={self.name}")

        # Language detection (vote system)
        lang = _detect_language(text)
        if lang:
            self._language_votes[lang] = self._language_votes.get(lang, 0) + 1
            total_votes = sum(self._language_votes.values())
            best = max(self._language_votes, key=self._language_votes.get)
            if total_votes >= 3 and best != self.preferred_language:
                self.preferred_language = best
                logger.debug("[UserProfile] Language → %s", self.preferred_language)
                changed = True

        # Style metrics (exponential moving average)
        self.communication["formality"] = _ema(self.communication["formality"], _score_formality(text))
        self.communication["verbosity"] = _ema(self.communication["verbosity"], _score_verbosity(text))
        self.communication["technical_level"] = _ema(self.communication["technical_level"], _score_technical(text))
        self.communication["humor_appreciation"] = _ema(self.communication["humor_appreciation"], _score_humor(text))

        # Project/topic extraction from natural mentions
        for m in _PROJECT_CONTEXT_RE.finditer(text):
            ref = m.group(2).strip()
            if ref and ref not in self.active_projects and len(self.active_projects) < 12:
                self.active_projects.append(ref)
                changed = True

        # Accumulate for persona_notes
        self._recent_messages.append(text)
        self._recent_messages = self._recent_messages[-40:]

        self.relationship["total_messages"] = self.relationship.get("total_messages", 0) + 1
        if changed:
            self._dirty = True

    def _on_turn_completed(self, data: Dict[str, Any]) -> None:
        convs = self.relationship.get("total_conversations", 0) + 1
        self.relationship["total_conversations"] = convs

        # First session timestamp
        if not self.relationship.get("first_session_ts"):
            self.relationship["first_session_ts"] = time.time()

        # Update known_since_days
        first_ts = float(self.relationship.get("first_session_ts") or time.time())
        self.relationship["known_since_days"] = int((time.time() - first_ts) / 86400)

        # Milestone: 1st, 10th, 50th, 100th conversation
        for n in (1, 10, 50, 100, 500):
            if convs == n:
                self._add_milestone(f"conversation_{n}", f"conversations={n}")

        self._dirty = True
        self._save()
        self._emit_updated()

        # Trigger persona_notes LLM analysis every N conversations
        if convs > 0 and convs % self._cfg_notes_every == 0 and not self._persona_notes_requested:
            self._request_persona_notes_update(str(data.get("turn_id", "")))

    def _pull_interests_from_world(self, data: Dict[str, Any]) -> None:
        intents = data.get("user_intents") or {}
        if not isinstance(intents, dict):
            return
        for intent_key in list(intents.keys())[:8]:
            clean = str(intent_key).replace("_", " ").strip()
            if clean and clean not in self.interests and len(self.interests) < 20:
                self.interests.append(clean)
                self._dirty = True

    def _seed_from_social_profile(self, profile: Dict[str, Any]) -> None:
        if not self.name and profile.get("name"):
            self.name = str(profile["name"]).strip().capitalize()
            logger.info("[UserProfile] Name seeded from social_profile: %s", self.name)
            self._dirty = True
        if profile.get("interests"):
            for item in list(profile["interests"])[:8]:
                if item and item not in self.interests:
                    self.interests.append(str(item)[:60])

    def _add_milestone(self, event_name: str, note: str = "") -> None:
        milestones = self.relationship.setdefault("milestones", [])
        milestones.append({
            "event": event_name,
            "note": note,
            "ts": time.time(),
        })
        self.relationship["milestones"] = milestones[-20:]
        logger.info("[UserProfile] Milestone: %s (%s)", event_name, note)

    # ─────────────────────────────────────────────────────────────────────────
    # Persona-notes LLM analysis (async, non-blocking)
    # ─────────────────────────────────────────────────────────────────────────

    def _request_persona_notes_update(self, turn_id: str) -> None:
        if not self.kernel or not self._recent_messages:
            return
        recent = self._recent_messages[-10:]
        msgs_text = "\n".join(f"- {m[:200]}" for m in recent)
        prompt = (
            "Analyze these recent messages from a user and describe their communication "
            "style in 1-2 concise sentences. Focus on: formality, tone, typical length, "
            "use of humor, technical level. Do not mention the user by name. "
            "Answer in Ukrainian.\n\nMessages:\n" + msgs_text
        )
        request_id = f"persona_notes_{turn_id}_{int(time.time())}"
        self._notes_request_turn_id = request_id
        self._persona_notes_requested = True

        self.kernel.event_bus.emit(
            Event(
                type="user_utterance",
                data={
                    "text": prompt,
                    "_skip_voice": True,
                    "_persona_notes_request": True,
                    "_request_id": request_id,
                },
                source_module=self.module_id,
            ),
            Priority.BACKGROUND,
        )
        logger.debug("[UserProfile] Requested persona_notes update (request_id=%s)", request_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Emit
    # ─────────────────────────────────────────────────────────────────────────

    def _emit_updated(self) -> None:
        if not self.kernel:
            return
        now = time.time()
        if now - self._last_emit_ts < 1.0:
            return
        self._last_emit_ts = now
        self.kernel.event_bus.emit(
            Event(
                type="user_profile_updated",
                data=self._build_snapshot(),
                source_module=self.module_id,
            ),
            Priority.BACKGROUND,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Snapshot / persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _build_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "user_profile_v2",
            "name": self.name,
            "preferred_language": self.preferred_language,
            "communication": dict(self.communication),
            "interests": list(self.interests),
            "active_projects": list(self.active_projects),
            "persona_notes": self.persona_notes,
            "relationship": dict(self.relationship),
            "language_votes": dict(self._language_votes),
            "timestamp": time.time(),
        }

    def _save(self) -> None:
        if self.kernel:
            self.kernel.persistence.save("user_profile_v2", self._build_snapshot())
            self._dirty = False

    def _load(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("user_profile_v2") or self.kernel.persistence.load("user_profile")
        if not isinstance(data, dict):
            return
        self.name = str(data.get("name") or "").strip()
        self.preferred_language = str(data.get("preferred_language") or "uk")
        if isinstance(data.get("communication"), dict):
            self.communication.update({
                k: float(v) for k, v in data["communication"].items()
                if k in self.communication and isinstance(v, (int, float))
            })
        self.interests = list(data.get("interests") or [])[:20]
        self.active_projects = list(data.get("active_projects") or [])[:12]
        self.persona_notes = str(data.get("persona_notes") or "")
        if isinstance(data.get("relationship"), dict):
            self.relationship.update(data["relationship"])
        if isinstance(data.get("language_votes"), dict):
            self._language_votes.update(data["language_votes"])
        logger.info(
            "[UserProfile] Loaded — name=%r lang=%s conversations=%d",
            self.name,
            self.preferred_language,
            self.relationship.get("total_conversations", 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(self._build_snapshot())
        return base


def create_module() -> UserProfileModule:
    return UserProfileModule()
