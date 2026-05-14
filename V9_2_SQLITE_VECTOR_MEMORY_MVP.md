# V9.2 SQLite + Vector Long-Term Memory MVP

This version upgrades memory from JSON-only persistence to a durable SQLite index with local semantic search.

## What changed

- Adds `longterm_memory.sqlite3` inside the configured brain data directory.
- Indexes episodic and semantic memories into SQLite.
- Adds local hashed-vector embeddings for portable semantic search.
- Keeps old JSON memory files for compatibility and backup.
- Adds `/recall <query>` and `/memory-search <query>` in chat.
- Adds natural language memory search: `згадай ...`, `пошукай в пам'яті ...`, `remember ...`, `recall ...`.
- Settings Center now exposes SQLite/vector memory switches.

## Important limits

This is not neural-weight learning. JAV does not fine-tune the base LLM automatically.
It learns by storing experience, extracting facts, and retrieving relevant context for the LLM.

## Portable setup

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
MEMORY_SQLITE_ENABLED=true
MEMORY_VECTOR_ENABLED=true
MEMORY_EPISODIC_RETENTION_DAYS=3650
MEMORY_EPISODIC_MAX_ITEMS=100000
```

## Commands

```text
/memory
/recall server setup
/memory-search помилки запуску
згадай що ми вирішили про пам'ять
пошукай в пам'яті сервер
```

## Files

```text
data/brain/longterm_memory.sqlite3
data/brain/memory_episodic.json
data/brain/memory_semantic.json
data/brain/memory_episodic_archive.json
```
