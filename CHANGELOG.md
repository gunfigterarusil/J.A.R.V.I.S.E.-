# Changelog

## v15.4-repair — Stable base restoration

### Fixed

- Removed hardcoded Gemini API key from `config.py`.
- Added `.env` loading with python-dotenv fallback/manual parser.
- Added portable path resolution through `JAV_PORTABLE` and `JARVIS_DATA_DIR`.
- Added `python main.py --doctor` diagnostics.
- Added `python main.py --chat` terminal chat.
- Added `python main.py --desktop` lightweight desktop shell.
- Added `python main.py --init-portable` portable structure initialization.
- Reduced episodic memory decay from minutes-level loss to long-term retention logic.
- Secured Web UI CORS defaults and optional `WEB_UI_API_TOKEN` for control event endpoint.
- Added run scripts for desktop/chat/doctor.
- Added build/dependency helper scripts.
- Removed release cache/log/backup artifacts from packaged ZIP.

### Known limitations

- Desktop UI is intentionally lightweight Tkinter, not final PySide/Tauri UI.
- Chat uses the existing memory/LLM event loop; without a configured model it falls back to NullProvider.
- Full voice, SQLite/vector memory, GUI automation, code repair, and installer wizard are queued for later restoration steps.
