# Patch notes

## Voice MVP with Piper + pyttsx3 fallback

Added:

- `python main.py --voice`
- microphone input through `sounddevice`
- STT through `faster-whisper`
- Piper TTS backend
- pyttsx3 fallback TTS backend
- `VOICE_TTS_BACKEND=auto|piper|pyttsx3|none`
- `.env.example` voice settings
- `VOICE_MVP.md` instructions

Default behavior:

```text
Piper -> pyttsx3 fallback -> log TTS error without crashing
```

Security/cleanup from the previous clean MVP remains included:

- no hardcoded API keys
- `.env.example`
- `requirements.txt`
- `.gitignore`
- stricter CORS configuration through env
- optional Web UI API token
# Patch notes — Clean MVP security pass

## Fixed

- Removed the hardcoded Gemini API key from `config.py`.
- Added `.env.example` for local/private configuration.
- Added `python-dotenv` loading support in `config.py`.
- Added `requirements.txt` with the runtime dependencies.
- Added `.gitignore` for caches, logs, virtualenvs, local memory, and secrets.
- Removed generated `__pycache__`, `.pyc`, `.log`, and backup files from the package.
- Changed web dashboard host/port/reload settings to be configurable through environment variables.
- Replaced permissive CORS `allow_origins=["*"]` with `WEB_CORS_ORIGINS`.
- Added optional bearer-token protection for mutating REST endpoints via `WEB_UI_API_TOKEN`.
- Updated `main.py` to use config/env defaults for web host and port.

## Validation performed

```bash
python -m compileall -q .
python main.py --help
timeout 5s python main.py
```

Result: Python files compile successfully, CLI help works, and headless mode starts with 17 modules loaded.

## Important

The old Gemini API key was present in the original archive. Treat it as exposed and revoke/regenerate it in Google AI Studio or your provider dashboard.

## Voice MVP update

Added:

- `interfaces/voice/stt.py` — microphone recording + faster-whisper STT.
- `interfaces/voice/piper_tts.py` — Piper CLI wrapper + local WAV playback.
- `interfaces/voice/voice_loop.py` — microphone -> `user_utterance` event loop.
- `modules/tier4_actions/tts/tts_module.py` — speaks `response_generated` events through Piper when voice mode is enabled.
- `python main.py --voice` startup mode.
- Voice settings in `KernelConfig.voice`.
- Voice env examples in `.env.example`.
- `VOICE_MVP.md` setup guide.

Voice mode is opt-in. Normal headless and web modes are unchanged.
