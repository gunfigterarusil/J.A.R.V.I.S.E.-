"""Tier 1: Memory Module

Manages all memory types:
- Short-Term Memory (STM): FIFO queue, max 50 events, 5 sec lifetime
- Working Memory (WM): 7 slots, importance-based eviction
- Episodic Memory: Experience records with importance, emotion tags, decay
- Semantic Memory: Knowledge graph (SPO triples), vector similarity
- Procedural Memory: Skill sequences, success/failure tracking
- Social Memory: User profiles with trust, attachment, humor, conflict history

Emits events:
- "memory_stored" (COGNITIVE)      - new memory committed
- "memory_retrieved" (COGNITIVE)   - memory accessed
- "memory_decayed" (BACKGROUND)    - old memory faded
- "context_ready" (COGNITIVE)      - working memory snapshot
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("memory")  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STM_MAX_SIZE = 50
STM_LIFETIME = 5.0
WM_SLOTS = 7
EPISODIC_DECAY_RATE = 0.02
SEMANTIC_SIMILARITY_THRESHOLD = 0.75


class MemoryManager:
    """Singleton managing all memory stores."""

    _instance: Optional["MemoryManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "MemoryManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        # Short-Term Memory: FIFO queue with timestamps
        self._stm: deque[Dict[str, Any]] = deque()
        self._stm_timestamps: deque[float] = deque()
        # Working Memory: importance-based cache, 7 items max
        self._wm: list[Dict[str, Any]] = []
        # Episodic Memory: experience records
        self._episodic: list[Dict[str, Any]] = []
        # Semantic Memory: knowledge graph (SPO triples)
        self._semantic: list[Dict[str, Any]] = []
        # Procedural Memory: skill records
        self._procedural: list[Dict[str, Any]] = []
        # Social Memory: user profiles
        self._social: Dict[str, Dict[str, Any]] = {}
        # Stats tracking
        self._store_count = 0
        self._retrieve_count = 0
        self._decay_count = 0

    # STM Operations --------------------------------------------------------
    def stm_push(self, item: Dict[str, Any]) -> None:
        now = time.time()
        self._stm.append(item)
        self._stm_timestamps.append(now)
        if len(self._stm) > STM_MAX_SIZE:
            self._stm.popleft()
            self._stm_timestamps.popleft()

    def stm_flush_expired(self) -> List[Dict[str, Any]]:
        now = time.time()
        expired = []
        while self._stm_timestamps and (now - self._stm_timestamps[0]) > STM_LIFETIME:
            expired.append(self._stm.popleft())
            self._stm_timestamps.popleft()
        return expired

    # Working Memory Operations --------------------------------------------
    def wm_insert(self, item: Dict[str, Any], importance: float = 0.5) -> Optional[Dict[str, Any]]:
        if len(self._wm) < WM_SLOTS:
            self._wm.append({"item": item, "importance": importance,
                             "timestamp": time.time()})
            return None
        else:
            # evict lowest importance
            self._wm.sort(key=lambda x: x["importance"])
            evicted = self._wm.pop(0)
            self._wm.append({"item": item, "importance": importance, "timestamp": time.time()})
            return evicted

    def wm_snapshot(self) -> List[Dict[str, Any]]:
        return [entry["item"] for entry in self._wm]

    # Episodic Memory Operations --------------------------------------------
    def episodic_store(self, experience: Dict[str, Any]) -> None:
        entry = {
            "experience": experience,
            "importance": experience.get("importance", 0.5),
            "emotion_tags": experience.get("emotion_tags", []),
            "timestamp": time.time(),
            "access_count": 0,
        }
        self._episodic.append(entry)
        self._store_count += 1

    def episodic_recall(self, query: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
        """Recall episodic memories by importance and recency."""
        now = time.time()
        scored = []
        for mem in self._episodic:
            age = now - mem["timestamp"]
            decay = math.exp(-EPISODIC_DECAY_RATE * age)
            q_emotions = query.get("emotion_tags", [])
            match = sum(1 for e in mem["emotion_tags"] if e in q_emotions)
            score = mem["importance"] * decay + match * 0.1
            scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]]

    def episodic_apply_decay(self) -> int:
        now = time.time()
        decayed_ids = []
        new_episodic = []
        for mem in self._episodic:
            age = now - mem["timestamp"]
            decay = math.exp(-EPISODIC_DECAY_RATE * age)
            if decay < 0.05:
                decayed_ids.append(mem)
            else:
                new_episodic.append(mem)
        self._episodic = new_episodic
        self._decay_count += len(decayed_ids)
        return len(decayed_ids)

    # Semantic Memory Operations --------------------------------------------
    def semantic_store_triple(self, subject: str, predicate: str, obj: str,
                            confidence: float = 1.0) -> None:
        entry = {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "confidence": confidence,
            "timestamp": time.time(),
            "last_accessed": time.time(),
        }
        self._semantic.append(entry)
        self._store_count += 1

    def semantic_query_similar(self, subject: str, threshold: float = SEMANTIC_SIMILARITY_THRESHOLD
                               ) -> List[Dict[str, Any]]:
        """Simple string similarity for semantic triples."""
        matches = []
        s_lower = subject.lower()
        for entry in self._semantic:
            sim = _jaccard(s_lower, entry["subject"].lower())
            if sim >= threshold:
                entry["similarity"] = sim
                entry["last_accessed"] = time.time()
                matches.append(entry)
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches

    # Procedural Memory Operations ------------------------------------------
    def procedural_store(self, skill_name: str, steps: List[str],
                         success: bool = True) -> None:
        entry = {
            "skill_name": skill_name,
            "steps": steps,
            "success": success,
            "attempts": 1,
            "timestamp": time.time(),
        }
        # Update if exists
        for proc in self._procedural:
            if proc["skill_name"] == skill_name:
                proc["steps"] = steps
                proc["success"] = success
                proc["attempts"] += 1
                proc["timestamp"] = time.time()
                return
        self._procedural.append(entry)
        self._store_count += 1

    def procedural_get(self, skill_name: str) -> Optional[Dict[str, Any]]:
        for proc in self._procedural:
            if proc["skill_name"] == skill_name:
                return proc
        return None

    # Social Memory Operations -----------------------------------------------
    def social_update_profile(self, user_id: str, trust: float = 0.0,
                              attachment: float = 0.0, humor: float = 0.0,
                              conflict: float = 0.0) -> None:
        profile = self._social.setdefault(user_id, {
            "trust": 0.0,
            "attachment": 0.0,
            "humor": 0.0,
            "conflict": 0.0,
            "interactions": 0,
            "last_update": time.time(),
        })
        profile["trust"] = max(0.0, min(1.0, trust))
        profile["attachment"] = max(0.0, min(1.0, attachment))
        profile["humor"] = max(0.0, min(1.0, humor))
        profile["conflict"] = max(0.0, min(1.0, conflict))
        profile["interactions"] += 1
        profile["last_update"] = time.time()
        self._store_count += 1

    def social_get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._social.get(user_id)

    # Stats ----------------------------------------------------------------
    def get_counts(self) -> Dict[str, int]:
        return {
            "stm": len(self._stm),
            "working": len(self._wm),
            "episodic": len(self._episodic),
            "semantic": len(self._semantic),
            "procedural": len(self._procedural),
            "social": len(self._social),
        }

    def get_avg_importance(self) -> float:
        if not self._episodic:
            return 0.0
        return sum(e["importance"] for e in self._episodic) / len(self._episodic)

    def memory_health(self) -> float:
        """Health is ratio of non-decayed memory relative to total capacity."""
        counts = self.get_counts()
        total = sum(counts.values())
        if total == 0:
            return 1.0
        decayed_ratio = self._decay_count / max(1, self._decay_count + total)
        return 1.0 - min(1.0, decayed_ratio)


def _jaccard(a: str, b: str) -> float:
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union_set = len(set_a | set_b)
    return intersection / union_set if union_set else 0.0


def _tokenize(text: str) -> set[str]:
    return {
        part.strip(".,:;!?()[]{}\"'`<>/\\|+-=*_#@")
        for part in str(text or "").lower().split()
        if len(part.strip(".,:;!?()[]{}\"'`<>/\\|+-=*_#@")) >= 3
    }


def _memory_to_text(memory: Any) -> str:
    if isinstance(memory, dict):
        data = memory.get("data", memory)
        if isinstance(data, dict):
            parts = [
                str(data.get("text", "")),
                str(data.get("raw_text", "")),
                str(data.get("summary", "")),
                str(data.get("source", "")),
            ]
            return " ".join(p for p in parts if p)
        return str(data)
    return str(memory)


def _token_score(tokens: set[str], text: str) -> float:
    if not tokens:
        return 0.0
    haystack = set(_tokenize(text))
    if not haystack:
        return 0.0
    overlap = len(tokens & haystack)
    return overlap / max(1, len(tokens))


class MemoryModule(CognitiveModule):
    """
    Tier 1: Memory Module
    Manages STM, Working Memory, Episodic, Semantic, Procedural, and Social memory
    via the event bus (no direct method calls).
    """

    def __init__(self) -> None:
        super().__init__(
            module_id="memory_module",
            cost={"cpu": 0.15, "gpu": 0.05, "ram": 0.20},
        )
        self._manager = MemoryManager()
        self._last_consolidation = 0.0
        self._kernel: Optional["Kernel"] = None

    def initialize(self, kernel: "Kernel") -> None:
        super().initialize(kernel)
        self._kernel = kernel
        # Load persisted memory on startup
        self._load_persisted()
        # Register event consumers
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "sensory_input",
                "user_utterance",
                "thought_generated",
                "response_generated",
                "memory_request",
                "kernel_started",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if event.type == "sensory_input":
            await self._handle_sensory(event.data)
        elif event.type == "user_utterance":
            await self._handle_utterance(event.data)
        elif event.type == "thought_generated":
            await self._handle_thought(event.data)
        elif event.type == "response_generated":
            await self._handle_response(event.data)
        elif event.type == "memory_request":
            await self._handle_request(event.data)

    async def _handle_sensory(self, data: Dict[str, Any]) -> None:
        # Store in STM + WM
        memory = {"type": "sensory_input", "data": data, "timestamp": time.time()}
        self._manager.stm_push(memory)
        self._manager.wm_insert(memory, importance=0.3)
        if self._kernel is not None:
            self._kernel.event_bus.emit(
                Event(type="memory_stored", data={"type": "sensory_input", "status": "ok"}),
                Priority.COGNITIVE,
            )

    async def _handle_utterance(self, data: Dict[str, Any]) -> None:
        memory = {"type": "user_utterance", "data": data, "timestamp": time.time()}
        self._manager.stm_push(memory)
        self._manager.wm_insert(memory, importance=0.6)
        self._manager.episodic_store({**memory, "importance": float(data.get("importance", 0.65) or 0.65)})
        logger.info(f"[Memory] Stored user_utterance: {data.get('text', '')[:50]}")
        # If user_id is present, update social profile
        user_id = data.get("user_id")
        if user_id:
            self._manager.social_update_profile(
                user_id,
                trust=data.get("trust", 0.5),
                attachment=data.get("attachment", 0.5),
            )
        if self._kernel is not None:
            self._kernel.event_bus.emit(
                Event(type="memory_stored", data={"type": "user_utterance", "status": "ok"}),
                Priority.COGNITIVE,
            )

    async def _handle_thought(self, data: Dict[str, Any]) -> None:
        memory = {"type": "thought_generated", "data": data, "timestamp": time.time()}
        self._manager.stm_push(memory)
        evicted = self._manager.wm_insert(memory, importance=0.5)
        # Evicted item goes to episodic
        if evicted is not None and isinstance(evicted, dict) and "item" in evicted:
            self._manager.episodic_store(evicted["item"])
        if self._kernel is not None:
            self._kernel.event_bus.emit(
                Event(type="memory_stored", data={"type": "thought_generated", "status": "ok"}),
                Priority.COGNITIVE,
            )


    async def _handle_response(self, data: Dict[str, Any]) -> None:
        """Store assistant responses as dialogue memory."""
        text = str(data.get("text", "") or "").strip()
        if not text:
            return
        memory = {
            "type": "assistant_response",
            "data": data,
            "timestamp": time.time(),
            "importance": float(data.get("importance", 0.55) or 0.55),
        }
        self._manager.stm_push(memory)
        self._manager.wm_insert(memory, importance=0.55)
        self._manager.episodic_store(memory)
        logger.info(f"[Memory] Stored assistant_response: {text[:50]}")
        if self._kernel is not None:
            self._kernel.event_bus.emit(
                Event(type="memory_stored", data={"type": "assistant_response", "status": "ok"}),
                Priority.COGNITIVE,
            )

    async def _handle_request(self, data: Dict[str, Any]) -> None:
        query_type = data.get("query_type")
        result: Dict[str, Any] = {}
        if query_type == "stm":
            result = {"stm_items": list(self._manager._stm)[-5:]}
        elif query_type == "wm":
            result = {"wm_snapshot": self._manager.wm_snapshot()}
        elif query_type == "episodic":
            query = data.get("query", {})
            result = {"episodic_recalls": self._manager.episodic_recall(query)}
        elif query_type == "semantic":
            subject = data.get("subject", "")
            result = {"semantic_matches": self._manager.semantic_query_similar(subject)}
        elif query_type == "procedural":
            skill = data.get("skill_name")
            result = {"procedural": self._manager.procedural_get(skill) if skill else None}
        elif query_type == "social":
            uid = data.get("user_id")
            result = {"social_profile": self._manager.social_get_profile(uid) if uid else None}
        elif query_type in {"dialogue_context", "relevant"}:
            query_text = str(data.get("query_text") or data.get("subject") or "")
            result = self._build_dialogue_context(query_text=query_text, top_k=int(data.get("top_k", 6)))
            if data.get("request_id"):
                result["request_id"] = data.get("request_id")
        else:
            result = {"error": f"Unknown query_type: {query_type}"}

        if self._kernel is not None:
            self._kernel.event_bus.emit(
                Event(type="memory_retrieved", data=result),
                Priority.COGNITIVE,
            )


    def _build_dialogue_context(self, query_text: str, top_k: int = 6) -> Dict[str, Any]:
        """Return compact, relevant memory for the dialogue module/LLM.

        This is intentionally lightweight: no vector DB yet. It combines
        working memory, recent short-term memory, episodic recall, semantic
        triples, and social profile into one stable payload.
        """
        tokens = _tokenize(query_text)
        wm = self._manager.wm_snapshot()[-7:]
        stm_recent = list(self._manager._stm)[-10:]

        scored: List[tuple[float, Dict[str, Any]]] = []
        now = time.time()
        for mem in self._manager._episodic:
            exp = mem.get("experience", mem)
            text = _memory_to_text(exp)
            score = _token_score(tokens, text)
            age = max(0.0, now - float(mem.get("timestamp", now)))
            recency = 1.0 / (1.0 + age / 3600.0)
            importance = float(mem.get("importance", exp.get("importance", 0.5) if isinstance(exp, dict) else 0.5) or 0.5)
            final = score * 1.5 + recency * 0.35 + importance * 0.25
            if score > 0 or not tokens:
                scored.append((final, exp))

        scored.sort(key=lambda item: item[0], reverse=True)
        episodic = [m for _, m in scored[:top_k]]

        semantic_matches = []
        if query_text:
            semantic_matches = self._manager.semantic_query_similar(query_text, threshold=0.15)[:top_k]

        return {
            "query_text": query_text,
            "wm_snapshot": wm,
            "stm_recent": stm_recent,
            "episodic_recalls": episodic,
            "semantic_matches": semantic_matches,
            "social_profile": self._manager.social_get_profile("default_user"),
            "counts": self._manager.get_counts(),
        }

    def update(self, dt: float) -> None:
        # Decay old STM entries
        expired = self._manager.stm_flush_expired()
        # Episodic decay
        decayed_count = self._manager.episodic_apply_decay()
        if expired or decayed_count:
            if self._kernel is not None:
                self._kernel.event_bus.emit(
                    Event(
                        type="memory_decayed",
                        data={"stm_expired": len(expired), "episodic_decayed": decayed_count},
                    ),
                    Priority.BACKGROUND,
                )
        # Periodic consolidation to episodic if WM churn is high
        now = time.time()
        if now - self._last_consolidation > 10.0:
            self._consolidate()
            self._last_consolidation = now
        # Emit snapshot of working memory for other modules
        if self._kernel is not None:
            self._kernel.event_bus.emit(
                Event(
                    type="context_ready",
                    data={"wm_snapshot": self._manager.wm_snapshot(),
                          "stm_count": len(self._manager._stm)},
                ),
                Priority.COGNITIVE,
            )

    def _consolidate(self) -> None:
        # Move high-importance WM items to episodic memory
        for entry in list(self._manager._wm):
            if entry["importance"] >= 0.7:
                self._manager.episodic_store(entry["item"])

    def shutdown(self) -> None:
        if self._kernel is None:
            return
        p = self._kernel.persistence
        p.save("memory_episodic", self._manager._episodic)
        p.save("memory_semantic", self._manager._semantic)
        p.save("memory_social", self._manager._social)
        p.save("memory_procedural", self._manager._procedural)
        logger.info("[Memory] Saved episodic, semantic, social, procedural to disk")

    def _load_persisted(self) -> None:
        if self._kernel is None:
            return
        p = self._kernel.persistence
        episodic = p.load("memory_episodic")
        if episodic:
            self._manager._episodic = episodic
            logger.info(f"[Memory] Loaded {len(episodic)} episodic memories")
        semantic = p.load("memory_semantic")
        if semantic:
            self._manager._semantic = semantic
        social = p.load("memory_social")
        if social:
            self._manager._social = social
        procedural = p.load("memory_procedural")
        if procedural:
            self._manager._procedural = procedural

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["memory_stats"] = {
            "counts": self._manager.get_counts(),
            "avg_importance": self._manager.get_avg_importance(),
            "memory_health": self._manager.memory_health(),
            "store_count": self._manager._store_count,
            "retrieve_count": self._manager._retrieve_count,
            "decay_count": self._manager._decay_count,
        }
        return base


def create_module():
    return MemoryModule()
