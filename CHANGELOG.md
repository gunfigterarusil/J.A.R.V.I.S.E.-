# Changelog

## V18.3 — UI Overhaul: Web + Desktop Redesign

### Web UI (browser interface)

- **Bugfix — гормони завжди 0.5:** `hormone_module.to_dict()` кладе дані в `base["hormone_levels"]`, але JS читав `mod.dopamine` (flat). Виправлено: `const hl = mod.hormone_levels || mod` перед читанням значень.
- **Bugfix — цілі завжди порожні:** `goal_module.to_dict()` кладе цілі в `base["active_stack"]` (об'єкти з `.description`, `.priority`), але JS читав `mod.active_goals` (undefined). Виправлено: `mod.active_stack || mod.active_goals || []`.
- **Bugfix — modulation bars:** `updateModulationBars()` тепер отримує `hormoneMod.hormone_levels || hormoneMod` замість raw module dict.
- **Нова панель System Monitor:** показує реальний CPU%, RAM% та статус мережі (зелена/червона крапка). Дані з `system_monitor.last_snapshot.cpu_percent`, `.memory.used_percent`, `.internet`.
- **Нова панель Self-Model:** показує `confidence`, `reliability`, `autonomy_level`, `cognitive_maturity`, `goal_success_rate` та `communication_style` з модуля `self_model`.
- **Glassmorphism redesign:** панелі отримали `backdrop-filter: blur(12px)`, rgba-фони, hover glow; header — градієнтна cyan-лінія; кнопки — box-shadow при hover; custom scrollbar 5px.
- **Chat thinking indicator:** три пульсуючі крапки з'являються одразу після відправки повідомлення (до відповіді LLM), зникають при `response_generated`.
- **Cache busting:** `style.css?v=19`, `app.js?v=19`.

### Desktop app

- **Повний переробка на customtkinter:** `interfaces/desktop/desktop_app.py` переписано з нуля на `customtkinter>=5.2`. Tkinter/ttk більше не використовується для UI-шару.
- Розроблено helper `_btn_kwargs(accent, danger)` для уніфікованих стилів кнопок.
- `InfoCard` і `StatusPill` переписані як `ctk.CTkFrame` subclasses з `text_color` замість `foreground`.
- Всі `ttk.Frame` → `ctk.CTkFrame(corner_radius=8)`.
- Всі `ttk.Label` → `ctk.CTkLabel(text_color=...)`.
- Всі `ttk.Button` → `ctk.CTkButton` з rounded corners та hover glow.
- Всі `ttk.Entry` → `ctk.CTkEntry` з placeholder_text.
- `scrolledtext.ScrolledText` → `ctk.CTkTextbox` для chat, логів, голосового виводу, approval detail, memory detail.
- `ttk.Notebook` → `ctk.CTkTabview` зі стилізованим segmented button.
- `ttk.Combobox` → `ctk.CTkOptionMenu` для фільтру логів.
- `ScrollableFrame` (custom class) → `ctk.CTkScrollableFrame` всередині потрібних вкладок.
- `tk.Listbox` збережено для `approval_list` і `memory_list` (потребують `.curselection()`).
- `task_feed` і `event_list` (display-only) → `ctk.CTkTextbox` readonly; insert/trim оновлено під CTkTextbox API.
- Виправлено `status_label.configure(foreground=...)` → `text_color=...` (degraded mode).
- Додано `customtkinter>=5.2` до `requirements.txt`.
- Вся бізнес-логіка (`send_message`, `_route_text`, всі action/voice/memory/approval методи) збережена без змін.

## V18.2 — Model Discovery + Provider Catalog

- Added `scripts/model_discovery.py` with unified model discovery across Ollama, OpenAI-compatible APIs, NVIDIA NIM, Anthropic, Gemini and llama.cpp.
- Added `python main.py --model-discover` and chat commands `/model-discover`, `/model-catalog`, `/model-assign <role> <provider>/<model>`.
- Added NVIDIA NIM config fields: `NVIDIA_NIM_API_KEY`, `NVIDIA_NIM_BASE_URL`, `NVIDIA_NIM_MODEL`.
- Added provider role suggestions: code, vision, embedding, fast, reason, critic and action.
- Added desktop **Model Catalog** window from the Models panel.
- Doctor now reports model discovery state separately from model router role health.


## V18.1 — README / Install Guide Cleanup

- Reworked README structure so install, first launch, build, portable and installer instructions are at the top.
- Added clearer sections for doctor, model setup, voice setup, ambient perception, workspace, memory and troubleshooting.
- Removed duplicate/confusing ordering from previous README.


## V18 — Modern Assistant Shell

- Upgraded the desktop UI into a cleaner Jarvis-style assistant cockpit while keeping lightweight Tkinter/ttk.
- Added a premium dark header with live HUD chips for Kernel, Voice, Ambient and Models.
- Expanded status cards to include Voice and Ambient perception.
- Improved chat layout with timestamps and quick scenario buttons: Diagnose, Screen, Models, Fix Project and Research.
- Added Home controls for Ambient status and Emotional Voice status.
- Added `/ambient-status` and `/emotion-voice-status` support to terminal chat.
- Added safer ambient perception defaults: baseline-first behavior, sensitive-screen skip, cooldowns and privacy controls.
- Made emotional TTS modulation subtler by default (`VOICE_EMOTIONAL_TTS_STRENGTH=0.35`).
- Hardened file logging so bad log permissions no longer crash startup.

## V17 — Voice Companion Mode

- Added acoustic wake word detection via openWakeWord (`interfaces/voice/wake_word_detector.py`): JAV wakes on "Hey Jarvis", listens, responds, then returns to sleep — Phase 3A.
- Added ambient screen perception: silent background capture every 8 s keeps world model current without interrupting the user — Phase 3B.
- Added change detection in `screen_parser_module.py`: app switch, context change, or detected error → `proactive_event` → JAV speaks proactively.
- Added emotional voice modulation: emotion + hormone state drives TTS speed (0.70–1.40×) and ElevenLabs stability (0.20–0.95) in real time — Phase 3C.
  - Speed: `arousal×0.25 + frustration×0.12 + adrenaline×0.30 − cognitive_load×0.10`
  - Stability: `oxytocin+0.20 − |arousal|×0.15 − cortisol×0.10 + valence×0.05`
- New env vars: `VOICE_WAKE_WORD_DETECTOR`, `VOICE_WAKE_WORD_MODEL`, `VOICE_WAKE_WORD_THRESHOLD`, `VOICE_WAKE_WORD_ACK`.
- New env vars: `SCREEN_AMBIENT_INTERVAL`, `SCREEN_AMBIENT_SPEECH_GAP`, `SCREEN_AMBIENT_PROACTIVE`.
- New env vars: `VOICE_EMOTIONAL_TTS`, `VOICE_EMOTIONAL_TTS_STRENGTH` (0.0 = off, 1.0 = full).

## V16 — Character System

- Added UserProfileEngine (`modules/tier1_essential/user_profile/`): learns user name, preferred language, communication style, interests, active projects across conversations — Phase 2.
- Added PersonaEvolution in SelfModel: relationship depth grows with every turn, shared references, adapted style, rotating persona evolution log.
- User profile injected into every LLM system prompt; responses personalise automatically after the first few sessions.
- Profile persisted locally in `~/.jarvis_brain/user_profile.json` — no cloud sync, data is yours.
- Added back-channel responses: JAV says "Розумію..." while the LLM is thinking — eliminates the silent-wait dead zone — Phase 1.
- Added speech-start interrupt: user starting to speak immediately stops ongoing TTS — Phase 1.
- Added LLM streaming with sentence-split TTS: first sentence spoken ≈0.5 s after generation starts — Phase 1.
- Streaming added to all LLM providers: Ollama, OpenAI-compatible, Anthropic, Gemini, llama.cpp.

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


## V15.8 — Voice Setup / Dependency Wizard

- Added `scripts/voice_setup.py` for voice diagnostics without starting the full kernel.
- Added CLI commands:
  - `python main.py --voice-doctor`
  - `python main.py --voice-list-mics`
  - `python main.py --voice-test-pyttsx3 "text"`
  - `python main.py --voice-test-piper "text"`
- Added chat commands:
  - `/voice`
  - `/voice-mics`
  - `/voice-test-pyttsx3`
  - `/voice-test-piper`
- Added a new Desktop **Voice** tab with microphone listing, TTS tests, voice report, dependency command copy and start/stop voice process.
- Doctor now includes a dedicated voice setup section so missing voice dependencies are easier to understand.
- Voice warnings remain optional and do not block core/chat/desktop startup.

## V15.9 — First Launch + Installer Stability

- Added explicit setup commands:
  - `python main.py --setup`
  - `python main.py --reset-setup`
- First-launch wizard is now resizable and scrollable, so it fits smaller laptop screens.
- First-launch setup now creates selected memory/workspace/screenshot/log folders before the main app starts.
- Setup completion is now stored both beside the app and inside the data directory, improving portable/movable installs.
- Portable paths selected by the wizard are saved relative to the app folder when possible.
- Doctor now reports setup/portable state: setup complete/incomplete, `.env` presence and memory/data directory path.
- Build output now includes setup launchers:
  - `run_setup.bat` / `run_setup.sh`
  - `run_reset_setup.bat`
- Windows installer script updated to version 15.9 and now adds Start Menu entries for **JAV Setup Wizard** and **Reset JAV Setup**.

## V16 — Model Setup Wizard 2.0

Added a full model configuration workflow:

- `python main.py --model-doctor` for offline model diagnostics;
- desktop Model Setup Wizard 2.0 with Offline / Low RAM / Hybrid / Cloud / Code / Voice profiles;
- per-role assignment for `fast`, `reason`, `code`, `critic`, `vision`, `embedding`, `action`;
- Ollama discovery through `/api/tags`;
- installed/missing model indicators;
- copy-ready `ollama pull ...` commands for missing local models;
- API key fields for Gemini, OpenAI-compatible and Anthropic providers;
- safer `.env` writing beside the app for portable/frozen builds.

Recommended local starter models:

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

Run diagnostics:

```bash
python main.py --model-doctor
```


## V17 — Voice Companion Mode

- Added push-to-talk voice mode:
  - `python main.py --voice-ptt`
  - `run_voice_ptt.bat` / `run_voice_ptt.sh`
- Added voice companion runtime status: `idle`, `listening`, `thinking`, `speaking`, `muted`, `timeout`, `error`, `stopped`.
- Voice status is emitted as `voice_status` events and written to `runtime_voice_status.json` inside the configured data directory.
- Added TTS mute/unmute/toggle/interrupt event handling.
- Added chat commands: `/mute`, `/unmute`, `/stop-speaking`, `/tts-status`.
- Added spoken control phrases for mute/unmute/interrupt, configurable through `.env`.
- Desktop Voice tab can now start continuous or push-to-talk voice process.
- Settings Center exposes voice input mode, mute phrases, unmute phrases and start-muted mode.