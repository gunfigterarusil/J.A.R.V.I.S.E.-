"""Tier 1: Memory Module

Manages all memory types:
- Short-Term Memory (STM): FIFO queue, configurable lifetime
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
import hashlib
import json
import logging
import math
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("memory")  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STM_MAX_SIZE = 50
STM_LIFETIME = 5.0
WM_SLOTS = 7
EPISODIC_DECAY_RATE = 0.02  # legacy fallback; V9.1 uses retention_days in MemoryManager
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
        # V9.1 long-term retention policy. Defaults are conservative and
        # overridden from config during module initialization.
        self._stm_lifetime_seconds = STM_LIFETIME
        self._episodic_retention_seconds = 730.0 * 86400.0
        self._episodic_max_items = 20000
        self._archive_decayed = True
        self._semantic_autostore = True
        self._episodic_archive: list[Dict[str, Any]] = []
        # V9.2 durable memory index. SQLite is standard-library only, so the
        # agent can remain portable. The vector index uses deterministic hashed
        # lexical embeddings as a local fallback; external embedding models can
        # be added later without changing the event API.
        self._sqlite_enabled = True
        self._vector_enabled = True
        self._vector_dimensions = 256
        self._db_path: Optional[Path] = None
        self._db: Optional[sqlite3.Connection] = None

    def configure(
        self,
        *,
        stm_lifetime_seconds: float | None = None,
        episodic_retention_days: float | None = None,
        episodic_max_items: int | None = None,
        archive_decayed: bool | None = None,
        semantic_autostore: bool | None = None,
        sqlite_enabled: bool | None = None,
        vector_enabled: bool | None = None,
        vector_dimensions: int | None = None,
    ) -> None:
        if stm_lifetime_seconds is not None:
            self._stm_lifetime_seconds = max(5.0, float(stm_lifetime_seconds))
        if episodic_retention_days is not None:
            self._episodic_retention_seconds = max(1.0, float(episodic_retention_days)) * 86400.0
        if episodic_max_items is not None:
            self._episodic_max_items = max(100, int(episodic_max_items))
        if archive_decayed is not None:
            self._archive_decayed = bool(archive_decayed)
        if semantic_autostore is not None:
            self._semantic_autostore = bool(semantic_autostore)
        if sqlite_enabled is not None:
            self._sqlite_enabled = bool(sqlite_enabled)
        if vector_enabled is not None:
            self._vector_enabled = bool(vector_enabled)
        if vector_dimensions is not None:
            self._vector_dimensions = max(64, min(2048, int(vector_dimensions)))

    def initialize_sqlite(self, base_dir: str | Path) -> None:
        if not self._sqlite_enabled:
            return
        base = Path(base_dir).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        self._db_path = base / "longterm_memory.sqlite3"
        self._db = sqlite3.connect(str(self._db_path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                text TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                timestamp REAL NOT NULL,
                source TEXT DEFAULT '',
                vector_json TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_type_time ON memories(memory_type, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_memories_time ON memories(timestamp DESC);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                id UNINDEXED, text, memory_type UNINDEXED, source UNINDEXED
            );
            CREATE TABLE IF NOT EXISTS semantic_triples (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                timestamp REAL NOT NULL,
                UNIQUE(subject, predicate, object)
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        if self._db is not None:
            self._db.commit()
            self._db.close()
            self._db = None

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
        while self._stm_timestamps and (now - self._stm_timestamps[0]) > self._stm_lifetime_seconds:
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
        now = time.time()
        entry = {
            "id": f"ep_{int(now * 1000)}_{len(self._episodic)}",
            "experience": experience,
            "importance": float(experience.get("importance", 0.5) or 0.5),
            "emotion_tags": experience.get("emotion_tags", []),
            "timestamp": float(experience.get("timestamp", now) or now),
            "created_at": now,
            "access_count": 0,
            "text_index": _memory_to_text(experience)[:4000],
        }
        self._episodic.append(entry)
        self._index_memory_sqlite(entry["id"], "episodic", entry["text_index"], entry, entry["importance"], entry["timestamp"], str(experience.get("type", "")))
        self._compact_episodic_if_needed()
        self._store_count += 1
        if self._semantic_autostore:
            self._autostore_semantic(experience)

    def episodic_recall(self, query: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
        """Recall episodic memories by importance, relevance and long-term recency."""
        now = time.time()
        scored = []
        q_text = str(query.get("text") or query.get("query_text") or query.get("subject") or "")
        q_tokens = _tokenize(q_text)
        for mem in self._episodic:
            age = max(0.0, now - float(mem.get("timestamp", now)))
            # V9.1: decay on a retention horizon measured in days/years, not seconds.
            long_term_decay = math.exp(-age / max(1.0, self._episodic_retention_seconds))
            q_emotions = query.get("emotion_tags", []) or []
            match = sum(1 for e in mem.get("emotion_tags", []) if e in q_emotions)
            text_score = _token_score(q_tokens, mem.get("text_index") or _memory_to_text(mem.get("experience", {})))
            access_boost = min(0.25, float(mem.get("access_count", 0)) * 0.02)
            score = float(mem.get("importance", 0.5)) * (0.55 + 0.45 * long_term_decay) + text_score * 1.25 + match * 0.1 + access_boost
            scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        recalled = [s[1] for s in scored[:top_k]]
        for mem in recalled:
            mem["access_count"] = int(mem.get("access_count", 0)) + 1
            mem["last_accessed"] = now
        return recalled

    def episodic_apply_decay(self) -> int:
        """Archive/remove only very old low-importance memories.

        Previous MVP code deleted memories after minutes. V9.1 keeps normal
        memories for months/years and archives low-importance expired items.
        """
        now = time.time()
        kept: list[Dict[str, Any]] = []
        expired: list[Dict[str, Any]] = []
        for mem in self._episodic:
            age = max(0.0, now - float(mem.get("timestamp", now)))
            importance = float(mem.get("importance", 0.5) or 0.5)
            if age > self._episodic_retention_seconds and importance < 0.72:
                expired.append(mem)
            else:
                kept.append(mem)
        self._episodic = kept
        if expired and self._archive_decayed:
            for mem in expired:
                mem["archived_at"] = now
            self._episodic_archive.extend(expired)
            self._episodic_archive = self._episodic_archive[-self._episodic_max_items:]
        self._decay_count += len(expired)
        return len(expired)

    def _compact_episodic_if_needed(self) -> None:
        if len(self._episodic) <= self._episodic_max_items:
            return
        self._episodic.sort(key=lambda m: (float(m.get("importance", 0.5)), float(m.get("timestamp", 0))))
        overflow = self._episodic[:-self._episodic_max_items]
        self._episodic = self._episodic[-self._episodic_max_items:]
        if self._archive_decayed:
            now = time.time()
            for mem in overflow:
                mem["archived_at"] = now
            self._episodic_archive.extend(overflow)
            self._episodic_archive = self._episodic_archive[-self._episodic_max_items:]

    def _autostore_semantic(self, experience: Dict[str, Any]) -> None:
        data = experience.get("data", experience) if isinstance(experience, dict) else {}
        text = str(data.get("text") or data.get("summary") or data.get("message") or "").strip()
        if not text:
            return
        lower = text.lower()
        cues = ["remember", "запам", "пам'ятай", "памятай", "my ", "моє", "мій", "моя", "мои", "люблю", "не люблю", "prefer", "віддаю перевагу"]
        if any(cue in lower for cue in cues):
            self.semantic_store_triple("user_or_project", "noted", text[:700], confidence=0.72)

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
        for old in self._semantic:
            if old.get("subject") == subject and old.get("predicate") == predicate and old.get("object") == obj:
                old["confidence"] = max(float(old.get("confidence", 0.0)), confidence)
                old["last_accessed"] = time.time()
                return
        self._semantic.append(entry)
        self._index_semantic_sqlite(entry)
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

    # Durable vector/SQLite memory -------------------------------------------
    def _index_memory_sqlite(self, memory_id: str, memory_type: str, text: str, payload: Dict[str, Any], importance: float, timestamp: float, source: str = "") -> None:
        if not self._sqlite_enabled or self._db is None or not text:
            return
        vector_json = json.dumps(_hash_embedding(text, self._vector_dimensions)) if self._vector_enabled else ""
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        now = time.time()
        self._db.execute(
            """INSERT OR REPLACE INTO memories(id, memory_type, text, payload_json, importance, timestamp, source, vector_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (memory_id, memory_type, text[:16000], payload_json, float(importance), float(timestamp), source, vector_json, now),
        )
        self._db.execute("DELETE FROM memory_fts WHERE id = ?", (memory_id,))
        self._db.execute("INSERT INTO memory_fts(id, text, memory_type, source) VALUES (?, ?, ?, ?)", (memory_id, text[:16000], memory_type, source))

    def _index_semantic_sqlite(self, entry: Dict[str, Any]) -> None:
        if not self._sqlite_enabled or self._db is None:
            return
        sid = "sem_" + hashlib.sha1(f"{entry.get('subject')}|{entry.get('predicate')}|{entry.get('object')}".encode("utf-8", errors="ignore")).hexdigest()
        self._db.execute(
            """INSERT OR REPLACE INTO semantic_triples(id, subject, predicate, object, confidence, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, entry.get("subject", ""), entry.get("predicate", ""), entry.get("object", ""), float(entry.get("confidence", 1.0)), float(entry.get("timestamp", time.time()))),
        )
        text = f"{entry.get('subject', '')} {entry.get('predicate', '')} {entry.get('object', '')}"
        self._index_memory_sqlite(sid, "semantic", text, entry, float(entry.get("confidence", 0.8)), float(entry.get("timestamp", time.time())), "semantic_triple")

    def commit_index(self) -> None:
        if self._db is not None:
            self._db.commit()

    def sqlite_counts(self) -> Dict[str, Any]:
        if self._db is None:
            return {"enabled": self._sqlite_enabled, "db_path": str(self._db_path or ""), "memories": 0, "semantic_triples": 0}
        memories = self._db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        triples = self._db.execute("SELECT COUNT(*) FROM semantic_triples").fetchone()[0]
        return {"enabled": True, "db_path": str(self._db_path or ""), "memories": int(memories), "semantic_triples": int(triples), "vector_enabled": self._vector_enabled, "vector_dimensions": self._vector_dimensions}

    def durable_search(self, query_text: str, top_k: int = 8, memory_type: str | None = None) -> List[Dict[str, Any]]:
        if not query_text.strip():
            return []
        rows: List[sqlite3.Row] = []
        if self._db is not None:
            # FTS can fail on punctuation-heavy queries, so keep a safe fallback.
            fts_query = _fts_query(query_text)
            try:
                sql = """SELECT m.* FROM memory_fts f JOIN memories m ON m.id = f.id
                         WHERE memory_fts MATCH ?"""
                params: list[Any] = [fts_query]
                if memory_type:
                    sql += " AND m.memory_type = ?"
                    params.append(memory_type)
                sql += " ORDER BY bm25(memory_fts) LIMIT ?"
                params.append(max(top_k * 4, 20))
                rows = list(self._db.execute(sql, params))
            except Exception:
                like = f"%{query_text[:80]}%"
                sql = "SELECT * FROM memories WHERE text LIKE ?"
                params = [like]
                if memory_type:
                    sql += " AND memory_type = ?"
                    params.append(memory_type)
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(max(top_k * 4, 20))
                rows = list(self._db.execute(sql, params))
        # Include in-memory memories too, so unsaved current-session context is searchable.
        candidates: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            candidates[str(row["id"])] = dict(row)
        for mem in self._episodic[-min(len(self._episodic), 500):]:
            mid = str(mem.get("id", f"live_{len(candidates)}"))
            if mid not in candidates:
                candidates[mid] = {
                    "id": mid, "memory_type": "episodic", "text": mem.get("text_index") or _memory_to_text(mem.get("experience", {})),
                    "payload_json": json.dumps(mem, ensure_ascii=False, default=str), "importance": mem.get("importance", 0.5),
                    "timestamp": mem.get("timestamp", time.time()), "source": "live", "vector_json": "", "created_at": mem.get("created_at", time.time()),
                }
        q_vec = _hash_embedding(query_text, self._vector_dimensions) if self._vector_enabled else []
        q_tokens = _tokenize(query_text)
        scored: List[tuple[float, Dict[str, Any]]] = []
        now = time.time()
        for item in candidates.values():
            text = str(item.get("text", ""))
            token = _token_score(q_tokens, text)
            vec_score = 0.0
            if q_vec:
                try:
                    stored_vec = json.loads(item.get("vector_json") or "[]")
                except Exception:
                    stored_vec = []
                if stored_vec:
                    vec_score = _cosine(q_vec, stored_vec)
                else:
                    vec_score = _cosine(q_vec, _hash_embedding(text, self._vector_dimensions))
            age = max(0.0, now - float(item.get("timestamp", now) or now))
            recency = 1.0 / (1.0 + age / 86400.0)
            importance = float(item.get("importance", 0.5) or 0.5)
            score = vec_score * 1.35 + token * 1.0 + importance * 0.25 + recency * 0.15
            if score > 0.08:
                payload = {}
                try:
                    payload = json.loads(item.get("payload_json") or "{}")
                except Exception:
                    payload = {}
                scored.append((score, {
                    "id": item.get("id"), "type": item.get("memory_type"), "score": round(score, 4),
                    "text": text[:1200], "importance": importance, "timestamp": item.get("timestamp"), "source": item.get("source", ""), "payload": payload,
                }))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def migrate_existing_to_sqlite(self) -> int:
        if not self._sqlite_enabled or self._db is None:
            return 0
        count = 0
        for mem in self._episodic:
            text = mem.get("text_index") or _memory_to_text(mem.get("experience", {}))
            if text:
                self._index_memory_sqlite(str(mem.get("id")), "episodic", text, mem, float(mem.get("importance", 0.5)), float(mem.get("timestamp", time.time())), str((mem.get("experience") or {}).get("type", "")))
                count += 1
        for entry in self._semantic:
            self._index_semantic_sqlite(entry)
            count += 1
        self.commit_index()
        return count

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


def _hash_embedding(text: str, dims: int = 256) -> List[float]:
    vec = [0.0] * dims
    tokens = list(_tokenize(text))
    # Character n-grams improve recall for Ukrainian/Russian inflections and typos.
    compact = " ".join(tokens)
    grams = [compact[i:i+4] for i in range(max(0, len(compact) - 3)) if compact[i:i+4].strip()]
    for token in tokens + grams[:400]:
        h = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dims
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        weight = 1.0 + min(2.0, len(token) / 12.0)
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n)) / ((math.sqrt(sum(x*x for x in a[:n])) or 1.0) * (math.sqrt(sum(x*x for x in b[:n])) or 1.0))


def _fts_query(text: str) -> str:
    tokens = list(_tokenize(text))[:12]
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


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
        self._last_save = time.time()
        self._save_interval_seconds = 60.0
        self._kernel: Optional["Kernel"] = None

    def initialize(self, kernel: "Kernel") -> None:
        super().initialize(kernel)
        self._kernel = kernel
        mem_cfg = getattr(getattr(kernel, "config", None), "memory", None)
        if mem_cfg is not None:
            self._manager.configure(
                stm_lifetime_seconds=getattr(mem_cfg, "stm_lifetime_seconds", None),
                episodic_retention_days=getattr(mem_cfg, "episodic_retention_days", None),
                episodic_max_items=getattr(mem_cfg, "episodic_max_items", None),
                archive_decayed=getattr(mem_cfg, "archive_decayed", None),
                semantic_autostore=getattr(mem_cfg, "semantic_autostore", None),
                sqlite_enabled=getattr(mem_cfg, "sqlite_enabled", None),
                vector_enabled=getattr(mem_cfg, "vector_enabled", None),
                vector_dimensions=getattr(mem_cfg, "vector_dimensions", None),
            )
            self._save_interval_seconds = float(getattr(mem_cfg, "save_interval_seconds", 60.0) or 60.0)
        # Load persisted memory on startup, then initialize/migrate the durable index.
        self._load_persisted()
        try:
            self._manager.initialize_sqlite(kernel.persistence._base)
            migrated = self._manager.migrate_existing_to_sqlite()
            if migrated:
                logger.info(f"[Memory] Indexed {migrated} existing memories into SQLite/vector store")
        except Exception as exc:
            logger.warning(f"[Memory] SQLite/vector memory unavailable: {exc}")
        # Register event consumers
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "sensory_input",
                "user_utterance",
                "thought_generated",
                "response_generated",
                "memory_request",
                "memory_status_requested",
                "memory_search_requested",
                "semantic_memory_store_requested",
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
        elif event.type == "memory_status_requested":
            await self._handle_status(event.data)
        elif event.type == "memory_search_requested":
            await self._handle_search(event.data)
        elif event.type == "semantic_memory_store_requested":
            await self._handle_semantic_store(event.data)

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
            if isinstance(query, dict) and data.get("query_text"):
                query = {**query, "query_text": data.get("query_text")}
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
        elif query_type in {"vector", "search", "memory_search"}:
            query_text = str(data.get("query_text") or data.get("subject") or data.get("query") or "")
            result = {"query_text": query_text, "matches": self._manager.durable_search(query_text, top_k=int(data.get("top_k", 8)), memory_type=data.get("memory_type"))}
            if data.get("request_id"):
                result["request_id"] = data.get("request_id")
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
        durable_matches = []
        if query_text:
            semantic_matches = self._manager.semantic_query_similar(query_text, threshold=0.15)[:top_k]
            durable_matches = self._manager.durable_search(query_text, top_k=top_k)

        return {
            "query_text": query_text,
            "wm_snapshot": wm,
            "stm_recent": stm_recent,
            "episodic_recalls": episodic,
            "semantic_matches": semantic_matches,
            "durable_matches": durable_matches,
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
        if now - self._last_save > self._save_interval_seconds:
            self._save_all()
            self._last_save = now
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

    async def _handle_search(self, data: Dict[str, Any]) -> None:
        if self._kernel is None:
            return
        query = str(data.get("query_text") or data.get("query") or data.get("text") or "").strip()
        top_k = int(data.get("top_k", 8) or 8)
        matches = self._manager.durable_search(query, top_k=top_k, memory_type=data.get("memory_type"))
        if data.get("respond", True):
            if not matches:
                text = f"I did not find durable memory matches for: {query}"
            else:
                lines = [f"Memory search for: {query}"]
                for i, match in enumerate(matches, 1):
                    ts = match.get("timestamp")
                    try:
                        age_days = round((time.time() - float(ts)) / 86400, 1)
                    except Exception:
                        age_days = "?"
                    snippet = str(match.get("text", "")).replace("\n", " ")[:240]
                    lines.append(f"{i}. [{match.get('type')}] score={match.get('score')} age≈{age_days}d: {snippet}")
                text = "\n".join(lines)
            self._kernel.event_bus.emit(
                Event(type="response_generated", data={"text": text, "source": "memory_search/v9.2", "matches": matches}, source_module=self.module_id),
                Priority.COGNITIVE,
            )
        self._kernel.event_bus.emit(
            Event(type="memory_search_completed", data={"query_text": query, "matches": matches}, source_module=self.module_id),
            Priority.COGNITIVE,
        )


    async def _handle_semantic_store(self, data: Dict[str, Any]) -> None:
        """Store a sourced semantic note/triple from modules such as web_learning."""
        if self._kernel is None:
            return
        subject = str(data.get("subject") or "external_note").strip()[:240]
        predicate = str(data.get("predicate") or "noted").strip()[:80]
        obj = str(data.get("object") or data.get("text") or "").strip()
        if not obj:
            return
        confidence = float(data.get("confidence", 0.72) or 0.72)
        self._manager.semantic_store_triple(subject, predicate, obj[:4000], confidence=confidence)
        episodic = {
            "type": "semantic_memory_store",
            "data": data,
            "timestamp": time.time(),
            "importance": float(data.get("importance", max(0.7, confidence)) or 0.75),
        }
        self._manager.episodic_store(episodic)
        self._kernel.event_bus.emit(
            Event(type="memory_stored", data={"type": "semantic", "status": "ok", "subject": subject, "source": data.get("source", "")}, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    async def _handle_status(self, data: Dict[str, Any]) -> None:
        if self._kernel is None:
            return
        stats = self.to_dict().get("memory_stats", {})
        sqlite_stats = self._manager.sqlite_counts()
        text = (
            f"Memory storage: {self._kernel.persistence._base}\n"
            f"Counts: {stats.get('counts')}\n"
            f"Retention: episodic≈{round(self._manager._episodic_retention_seconds / 86400)} days, "
            f"max_items={self._manager._episodic_max_items}, archive={self._manager._archive_decayed}\n"
            f"Archive items: {len(self._manager._episodic_archive)}\n"
            f"SQLite/vector: {sqlite_stats}"
        )
        self._kernel.event_bus.emit(
            Event(type="response_generated", data={"text": text, "source": "memory_status"}, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    def _save_all(self) -> None:
        if self._kernel is None:
            return
        p = self._kernel.persistence
        p.save("memory_episodic", self._manager._episodic)
        p.save("memory_episodic_archive", self._manager._episodic_archive)
        p.save("memory_semantic", self._manager._semantic)
        p.save("memory_social", self._manager._social)
        p.save("memory_procedural", self._manager._procedural)
        self._manager.commit_index()

    def shutdown(self) -> None:
        if self._kernel is None:
            return
        self._save_all()
        self._manager.close()
        logger.info("[Memory] Saved episodic, archive, semantic, social, procedural and SQLite/vector index to disk")

    def _load_persisted(self) -> None:
        if self._kernel is None:
            return
        p = self._kernel.persistence
        episodic = p.load("memory_episodic")
        if episodic:
            self._manager._episodic = episodic
            logger.info(f"[Memory] Loaded {len(episodic)} episodic memories")
        archive = p.load("memory_episodic_archive")
        if archive:
            self._manager._episodic_archive = archive
            logger.info(f"[Memory] Loaded {len(archive)} archived episodic memories")
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
            "archive_count": len(self._manager._episodic_archive),
            "retention_days": round(self._manager._episodic_retention_seconds / 86400, 2),
            "stm_lifetime_seconds": self._manager._stm_lifetime_seconds,
            "storage_path": str(self._kernel.persistence._base) if self._kernel is not None else "",
            "sqlite": self._manager.sqlite_counts(),
        }
        return base


def create_module():
    return MemoryModule()
