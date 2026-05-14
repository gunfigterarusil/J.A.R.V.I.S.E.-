# V9.1 — Long-Term Memory + Portable Mode

This upgrade fixes the biggest V9 weakness: memory retention was too short for real long-term use.

## What changed

- `persistence_dir` now reads from `JARVIS_DATA_DIR`, `MEMORY_DIR`, or `PERSISTENCE_DIR`.
- `JAV_PORTABLE=true` stores data beside the program:
  - `data/brain` — memory, self/world model, repair proposals, audit-related state
  - `data/workspace` — safe editable workspace
  - `data/screenshots` — screen OCR captures
- Episodic memory retention is now measured in days/years, not seconds.
- Old low-importance memories are archived to `memory_episodic_archive.json` instead of silently disappearing.
- Memory is periodically saved during runtime, not only on shutdown.
- Desktop Settings Center now has Portable / Paths and Memory settings.
- Terminal chat has `/memory`, `/memory-status`, `/storage`.
- Natural language can ask: `покажи стан пам'яті`, `де зберігається пам'ять`, `memory status`.

## Portable setup

Inside the project folder:

```bash
python main.py --init-portable
python main.py --desktop
```

To copy JAV to a removable drive:

```bash
python scripts/install_portable.py E:/JAV
```

Then launch:

```bat
E:\JAV\run_desktop_portable.bat
```

or Linux:

```bash
/media/user/USB/JAV/run_desktop_portable.sh
```

## Recommended memory policy

For a personal assistant:

```env
MEMORY_EPISODIC_RETENTION_DAYS=730
MEMORY_EPISODIC_MAX_ITEMS=20000
MEMORY_ARCHIVE_DECAYED=true
MEMORY_SEMANTIC_AUTOSTORE=true
```

For years-long archival use:

```env
MEMORY_EPISODIC_RETENTION_DAYS=3650
MEMORY_EPISODIC_MAX_ITEMS=100000
```

## Important limitation

This is still lightweight JSON long-term memory, not a full vector database. It can retain data for years if the storage is preserved, but the next major memory upgrade should add SQLite + vector search for much better recall over huge histories.
