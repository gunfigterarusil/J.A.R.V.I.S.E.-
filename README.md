# JAV — Repaired Cognitive Assistant Core

This build restores the project to a stable base after broken/partial rewrites. It keeps the working cognitive kernel and adds the minimal product layer needed for continued development:

- secure config with `.env` support;
- no hardcoded API keys;
- diagnostics via `--doctor`;
- terminal chat via `--chat`;
- lightweight desktop shell via `--desktop`;
- portable data folders via `--init-portable`;
- safer Web UI CORS/token controls;
- cleaned release structure.

## Quick start

```bash
python -m pip install -r requirements.txt
python main.py --doctor
python main.py --chat
```

Desktop UI:

```bash
python main.py --desktop
```

Web dashboard:

```bash
python main.py --web
```

Headless kernel:

```bash
python main.py
```

## Portable mode

To prepare the app so it can live on a portable SSD/HDD:

```bash
python main.py --init-portable
```

This creates:

```text
data/brain       # persistent brain state
data/workspace   # safe workspace for future actions
data/screenshots # screen/OCR output later
.env             # portable config
```

Portable `.env` defaults:

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
ACTION_WORKSPACE_PATH=data/workspace
SCREENSHOT_DIR=data/screenshots
```

Relative paths are resolved from the program folder, so moving the whole `JAV/` folder keeps the data layout intact.

## Configuration

Copy `.env.example` to `.env` and edit values.

Important keys:

```env
GEMINI_API_KEY=
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
WEB_HOST=127.0.0.1
WEB_PORT=8000
WEB_UI_API_TOKEN=
```

LLM models are **not bundled**. Install or configure them yourself, for example with Ollama.

## Commands

### Doctor

```bash
python main.py --doctor
```

Checks core files, dependencies, config, data folder, and kernel startup.

### Chat

```bash
python main.py --chat
```

Commands inside chat:

```text
/help
/status
/modules
/memory
/events
/exit
```

### Desktop

```bash
python main.py --desktop
```

If it fails, check:

```text
data/brain/logs/desktop_crash.log
```

or run:

```bash
python main.py --doctor
```

## Build desktop app

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
python scripts/build_desktop_app.py
```

Output:

```text
dist/JAV/
```

This does not bundle LLMs. Users configure Ollama/API keys in `.env`.

## Current status

Working now:

- cognitive kernel;
- 17 module auto-load;
- safety constitution/firewall/sandbox base;
- web dashboard;
- doctor;
- terminal chat;
- lightweight desktop UI;
- portable path initialization.

Still planned / not fully restored yet:

- SQLite/vector memory upgrade;
- role-based model router;
- full voice companion;
- real screen/OCR/vision;
- safe action executor;
- task orchestrator;
- code repair agent;
- web learning;
- installer wizard.

## Security note

A previous build contained a Gemini API key in `config.py`. This repaired build removes it. If that key was real, revoke/regenerate it.
