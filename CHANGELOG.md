# Changelog

## V15.7 — Quality & UX Stabilization

- Doctor now separates REQUIRED failures from optional/external WARN items, so missing voice/OCR/Ollama dependencies no longer look like full startup failure.
- Desktop Doctor tab now shows optional warnings with a yellow marker and reports “Core OK” when only optional components are missing.
- Added a real Workspace block in the desktop Home tab: open workspace, change workspace, and import project into workspace.
- Added explicit `/workspace` guidance in chat mode so users understand that file actions only operate inside the sandbox workspace.
- Replaced the Memory tab placeholder with a basic SQLite memory browser: recent rows, search, and detail preview.
- Added filesystem sanity checks in System Monitor so unrealistic virtual-disk sizes are shown as “unknown” instead of absurd GB values.
- Cleaned the release output from `__pycache__`, `.pyc`, `.log`, and runtime data.

## V15.4 — Safety Constitution + Modern Desktop Shell Polish

- Confirmed and documented the Asimov-inspired Safety Constitution layer.
- Safety Constitution is wired into the action firewall before sandbox/risk/permission checks.
- Desktop UI was visually refreshed: darker modern palette, product-like header, clearer Home tab, improved chat typography, icon-labeled tabs, and safer quick actions.
- Added clearer README guidance for the modern desktop shell, first-launch wizard, Doctor and Logs workflow.
- Kept the UI pure Tkinter/ttk to avoid heavy dependencies and preserve portable builds.

## V15.3 — Installer / Portable / Startup Fix

- Added proper portable-aware build flow with `JAV.exe` and `JAV-Console.exe`.
- Built desktop app now opens GUI by default on double-click instead of starting headless mode.
- Added `scripts/bootstrap_dependencies.py` for source/dev dependency installation without installing LLM models.
- Added `scripts/make_portable_release.py` for creating a movable external-drive app folder.
- Reworked `scripts/build_desktop_app.py` to include submodules and create portable `.env`/data folders.
- Reworked Inno Setup installer to let the user choose install directory and initialize portable data inside the app folder.
- Fixed relative portable paths so `.env` paths like `data/brain` resolve against the application folder, not the current terminal folder.
- Desktop UI now opens the window first and boots the kernel in the background, avoiding the “console shows two lines and appears stuck” startup problem.
- Added better source launchers: `run_desktop.bat`, `run_desktop_debug.bat`, `run_doctor.bat`, `run_install_deps.bat`.


## V15.2 — Startup stability / runtime doctor

- Added `python main.py --doctor` for startup diagnostics, dependency checks, import checks and chat smoke test.
- Added `scripts/doctor.py` for direct diagnostics.
- Improved desktop startup failure handling: writes `logs/desktop_crash.log` and prints a clear message instead of silently closing.
- Desktop now creates the Tk window before building the full kernel, so GUI/display problems are detected immediately.
- `run_desktop.bat` and `run_desktop.sh` now run doctor automatically if desktop startup fails.
- Added `PROACTIVE_STARTUP_GRACE_SECONDS` so startup alerts do not steal the first chat/desktop response.
- Cleaned generated `__pycache__` / `.pyc` files from release ZIP.

Уся історія великих етапів JAV зібрана тут. Окремі `V*_*.md` patch-файли більше не використовуються в корені проєкту.

---

## V15 — Better Desktop App / Assistant Shell MVP

- Оновлено desktop UI.
- Додано dashboard-картки: Kernel, Models, System, Tasks, Approvals, Memory.
- Додано вкладки: Dashboard, Commands, Tasks, Approvals, Memory/Skills, Models, Events.
- Додано approval panel для ризикових дій.
- Додано запуск voice mode із desktop.
- Додано optional tray icon і desktop notifications.
- Додано налаштування Desktop Shell у Settings Center.

## V14 — Skill Learning + Knowledge Graph MVP

- Додано skill library.
- Додано lightweight knowledge graph.
- Додано auto-learning із task/repair/web/action/sleep подій.
- Додано команди `/skills`, `/skill`, `/learn-skill`, `/knowledge`, `/kg`.
- Додано збереження `skills_knowledge_v14.json`.

## V13 — Advanced Task Orchestrator MVP

- Посилено task chains.
- Додано стратегії A/B/C.
- Додано verifier, retry, rollback guidance, progress score і task report.
- Додано команди `/task`, `/task-auto`, `/task-step`, `/task-retry`, `/task-report`.

## V12 — Advanced Vision + GUI Automation 2.0 MVP

- Покращено GUI-loop: observe → understand → act → verify.
- Додано screenshot audit before/after.
- Реалізовано GUI-дії: open_url, open_app, click, type, press, hotkey, scroll, wait.
- Додано verify-after-action і semantic click safety.

## V11 — Proactive Companion + System Monitor MVP

- Додано system monitor.
- Додано proactive assistant.
- Моніторинг CPU/RAM/disk/network/Ollama/model roles/runtime/errors.
- Додано `/system`, `/monitor`, `/diagnose-system`, `/proactive`, `/daily-summary`.

## V10 — Modular Model/API Router MVP

- Додано role-based model router.
- Ролі: fast, reason, code, critic, vision, embedding, action.
- Профілі: offline, balanced, power, code, voice_companion, custom.
- Провайдери: Ollama, OpenAI-compatible, Gemini, Anthropic, llama.cpp, null fallback.
- Додано `/models`, `/model-health`, `/model-status`.

## V9.7 — Safe General GUI Automation MVP

- Додано універсальний GUI-agent.
- Додано cycle observe → reason → act → observe.
- Додано GUI action types і safety gates.
- Додано `/gui-task`, `/gui-auto`, `/gui-step`, `/gui-status`, `/gui-cancel`.

## V9.6 — Real Vision + GUI Understanding MVP

- Покращено screen parser.
- Додано GUI scene understanding: buttons, inputs, menus, errors, likely context.
- Додано `/vision`, `/gui`, `/understand-screen`, `/analyze-screen`.

## V9.5 — Runtime / Service Mode MVP

- Додано `--service` mode.
- Додано watchdog.
- Додано runtime monitor, heartbeat, PID, health snapshot, rotating logs.
- Додано systemd helper і Windows startup helper.

## V9.4 — Autonomous Task Chains MVP

- Додано task chain module.
- Додано guided/auto task execution.
- Інтеграція з memory, screen, web, repair, actions, sleep і safety.

## V9.3 — Web Learning/Search + UI Upgrade

- Додано web learning module.
- Додано `/web-search`, `/web-learn`, `/web-fetch`.
- Додано sourced semantic memory notes.
- Покращено desktop UI і Settings Center.

## V9.2 — SQLite + Vector Long-Term Memory MVP

- Додано SQLite long-term memory.
- Додано hashed-vector semantic search.
- Додано `/recall` і `/memory-search`.
- Додано міграцію JSON memories у SQLite/vector index.

## V9.1 — Long-Term Memory + Portable Mode

- Виправлено агресивний episodic decay.
- Додано retention у днях/роках.
- Додано `JARVIS_DATA_DIR` і `JAV_PORTABLE`.
- Додано portable install script.
- Додано налаштування шляхів у Settings Center.

## V9 — Project Repair Agent MVP

- Додано cognitive repair cycle.
- Додано diagnostics → memory/self/world context → LLM repair cortex → proposal → apply через safety.
- Додано `/repair` і `/apply-repair`.

## V8.1 — Settings Center + Natural Actions MVP

- Додано Settings Center.
- Розширено natural action router.
- Додано repair intent для фраз типу “виправ помилки”.

## V8 — Desktop + Conversational Actions MVP

- Додано desktop UI на Tkinter.
- Додано build script для desktop app.
- Додано natural bridge до V7 actions.

## V7 — Safe PC Automation MVP

- Додано action executor.
- Додано workspace sandbox.
- Додано list/read/search/write/mkdir/run_command.
- Додано approval flow.

## V6 — Sleep / Dream Replay + Memory Consolidation MVP

- Переписано dream module.
- Додано sleep cycle, consolidation lessons, dream narrative.
- Додано `/sleep`, `/dream`, `/consolidate`.

## V5 — World Model + Mature Self-Model MVP

- Переписано self-model і world-model.
- Додано `/self`, `/world`.
- LLM context отримав self/world state.

## V4 — Emotion + Deep Monologue MVP

- Переписано emotion module.
- Переписано monologue module.
- LLM відповіді враховують emotional state, mood, curiosity, confidence і internal monologue.

## V3 — Screen Reading MVP

- Додано screen capture через mss.
- Додано OCR через Tesseract/pytesseract.
- Додано `/see`, `/screen`, `/read-screen`, `/explain-screen`.

## V2 — Voice Dialogue Stability MVP

- Додано voice mode.
- STT через faster-whisper.
- TTS через Piper із pyttsx3 fallback.
- Voice mode підключено до V1 dialogue/memory loop.

## V1 — Real Dialogue Loop + Memory Retrieval MVP

- Переписано LLM module у dialogue coordinator.
- Додано memory request/retrieval у діалог.
- Додано `--chat`.

## V0 — Clean MVP Foundation

- Очищено проєкт.
- Прибрано hardcoded secrets.
- Додано `.env.example`, `.gitignore`, `requirements.txt`.
- Додано базовий safety layer, kernel і module loading.

## V15.5-restored — Full functionality restore

- Restored the full V15-era feature set from the older stable patch line.
- Kept Safety Constitution / modern UI improvements.
- Fixed model router fallback: when Ollama/API is unavailable, chat falls back to NullProvider instead of emitting connection errors.
- Restored explicit chat commands: `/help`, `/status`, `/modules`, `/events`.
- Cleaned release archive from `.env`, runtime `data/`, logs and caches.

## V15.6 — Model Connection + Interface Bugfix Patch

- Fixed Ollama role availability checks: JAV now verifies that the configured model is actually pulled, not only that Ollama is running.
- Added clear model diagnostics for missing Ollama models, for example: `ollama pull qwen2.5:7b`.
- Added `/model-test [role]` in chat for live model role testing.
- Improved `/models` output with provider/model/detail fields.
- Fixed model status panel to show the configured model name and connection details instead of blank model cells.
- Fixed Model Setup Wizard profile selection refresh bug.
- Settings Center and Model Setup Wizard now keep their windows inside smaller screens.
- Settings Center writes `.env` beside the movable app/exe in frozen builds.
- Desktop now reloads the model router live after saving model/provider/API settings.
- Doctor now includes model-router diagnostics and per-role status.

