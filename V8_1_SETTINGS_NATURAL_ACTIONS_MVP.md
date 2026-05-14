# V8.1 — Desktop Settings Center + Natural Voice/Chat Actions

This update makes the desktop app more like a real program instead of only a
browser dashboard or terminal tool.

## Added

### Desktop Settings Center

Start:

```bash
python main.py --desktop
```

Then open **Settings Center** from the right-side controls.

It edits `.env` and covers the main runtime systems:

- LLM providers: Ollama, Gemini, OpenAI-compatible, Anthropic, llama.cpp
- Voice: STT, Piper, pyttsx3 fallback
- Screen reading: OCR, screenshots, Tesseract
- Actions: workspace, shell toggle, allowed commands, natural actions
- Sleep/consolidation
- Emotion and monologue
- Self/world model
- Web UI/API settings

Most settings are applied after restart. A few action/safety-related settings
can be partially applied live.

### Natural Action Router

Anything that previously needed a slash command can now be requested with normal
chat/voice phrases. Examples:

```text
прочитай екран
що тут не так
запусти сон
консолідуй пам'ять
покажи файли .
прочитай файл README.md
знайди error в .
створи папку notes
запиши в notes/test.txt :: hello
допиши в notes/test.txt :: more text
запусти python --version
постав safety 4
схвали p123
відхили p123
покажи налаштування
виправ помилки в .
```

The same phrases work from:

- `python main.py --chat`
- `python main.py --voice`
- `python main.py --desktop`

Voice and chat do **not** bypass safety. They emit the same `action_request`
events that slash commands and buttons use.

## Repair intent MVP

The phrase:

```text
виправ помилки в .
```

now starts a safe diagnostics workflow inside `ACTION_WORKSPACE_PATH`:

1. checks Python files with `compileall`;
2. scans for common error markers;
3. reports suspicious files/lines;
4. asks you to read/patch the target file next.

It does **not** silently rewrite the whole project. File writing still requires
V7 safety level L4 and the sandbox.

## Important safety model

- Reading screen/files: low-risk, available at normal safety levels.
- Writing files: requires L4.
- Shell commands: require `ACTION_ALLOW_SHELL=true`, L5, and may ask for approval.
- Full autonomous chains remain intentionally limited.

## New env settings

```env
NATURAL_ACTIONS_ENABLED=true
NATURAL_ACTIONS_REQUIRE_EXPLICIT_VERB=true
REPAIR_AGENT_ENABLED=true
```
