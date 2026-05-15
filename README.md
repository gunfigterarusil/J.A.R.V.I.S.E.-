# Jarvis Brain Core

A **persistent modular cognitive brain** — not a chatbot, not a prompt wrapper.

A running program that thinks, remembers, imagines, and evolves. It starts when you turn on your PC and keeps a continuous thread of identity across sessions. Every module is replaceable. The kernel is permanent.

---

## What It Is

Most AI assistants are stateless: every conversation starts from zero. Jarvis Brain Core is different.

It maintains a **continuous cognitive runtime** — a kernel that ticks 10 times per second, orchestrating a set of cognitive modules (memory, emotions, hormones, imagination, goals, personality) that collectively produce something closer to *ongoing thought* than *request-response*.

```
You talk to it → it thinks, remembers, imagines multiple possibilities,
                 evaluates them, feels something about the answer,
                 and responds from a persistent identity
                 that grows over time.
```

The LLM (Ollama, Gemini, Claude, GPT) is just a **reasoning tool** — not the brain. The brain is the kernel.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     KERNEL CORE                     │
│  EventBus · CoreState · Scheduler · Persistence     │
│  AttentionRouter · ModuleManager · LifecycleManager │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │         SAFETY LAYER  (always active)        │   │
│  │  Constitution · Sandbox · RiskEngine         │   │
│  │  PermissionManager · ActionFirewall · Audit  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
          │ registers / ticks / routes events
          ▼
┌─────────────────────────────────────────────────────┐
│                    MODULES                          │
│                                                     │
│  Tier 1 — Essential (always loaded)                 │
│    memory · working_memory · self_model             │
│    emotions · hormones · goals · temporal_engine    │
│                                                     │
│  Tier 2 — Perception (stubs, ready to wire)         │
│    screen · vision · audio                          │
│                                                     │
│  Tier 3 — Reasoning                                 │
│    llm · monologue · planner · world_model          │
│    imagination/                                     │
│      theory_builder · critic · counterfactuals      │
│      hypothesis_engine · scenario_simulator         │
│      idea_memory                                    │
│                                                     │
│  Tier 4 — Actions (stubs, safe-gated)               │
│    tts                                              │
│                                                     │
│  Tier 5 — Evolution                                 │
│    dream · personality · self_learning              │
└─────────────────────────────────────────────────────┘
          │ web UI
          ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Dashboard  (localhost:8000)                │
│  Live state · module control · event stream         │
└─────────────────────────────────────────────────────┘
```

---

## Key Concepts

### Cognitive Kernel
The runtime core. It ticks every 100ms, dispatches events across three priority queues (`REALTIME → COGNITIVE → BACKGROUND`), allocates attention budget between modules, and persists state to disk on shutdown.

### Modules
Self-contained cognitive units. Each module:
- subscribes to event types it cares about
- emits events to communicate with other modules
- never calls another module directly
- has a cost (cpu/ram) that the attention router uses for throttling

### Safety Constitution
Every action with side effects (`speak`, `write_file`, `run_command`, etc.) is emitted as an `action_request` event. The **ActionFirewall** intercepts it before any module sees it and runs:
1. **Constitution** — 14 hard rules (rm -rf, format, System32, encoded exec, etc.) — unbypassable
2. **Sandbox** — write access restricted to `~/jarvis_workspace/` and `~/.jarvis_brain/`
3. **RiskEngine** — danger score 0–10
4. **PermissionManager** — level gate L0 (think) → L6 (autonomous)

Safety cannot be disabled by any module or permission level.

### Imagination Engine
When a goal fails, uncertainty is high, or a complex question arrives, the brain switches to `IMAGINATION` or `DEEP_ANALYSIS` thinking mode:

```
Problem
  → HypothesisEngine  → 3-7 competing theories (each with confidence, risk, evidence)
  → ScenarioSimulator → projected outcomes per theory
  → CriticModule      → filter impossible, rank by confidence × (1 − risk)
  → Planner           → decompose best theory into action steps
  → ActionFirewall    → gate before any execution
```

The brain thinks in **possibilities**, not single answers.

### Multi-LLM Router
A single interface that routes to whichever AI provider is available and best suited for the task:

| Task | Default provider |
|------|-----------------|
| Simple chat | Ollama (local) |
| Complex reasoning | Ollama → Anthropic → OpenAI |
| Imagination | Strongest available |
| Summarization | Fastest available |

If no provider is configured, `NullProvider` returns structured low-confidence stubs. The system always runs.

### Persistence
Everything that matters survives restart:
- Episodic, semantic, social, procedural memory
- Active goals
- Personality traits (Big Five, slow drift)
- Permission grants/denials
- Generated theories (idea memory)
- Session count and uptime

Stored in `~/.jarvis_brain/` as atomic JSON files.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

For local LLM (recommended):
```bash
# Install Ollama: https://ollama.com
ollama pull llama3.2
```

For cloud LLM (optional):
```bash
pip install anthropic          # Claude
pip install openai             # OpenAI / LM Studio
pip install google-generativeai  # Gemini
```

### 2. Run headless (kernel only)

```bash
python main.py
```

The kernel starts, auto-discovers all modules, and begins the cognitive tick loop. Press `Ctrl+C` to stop (state is saved automatically).

### 3. Run terminal dialogue mode

```bash
python main.py --chat
```

This is the V1 real dialogue loop:

```text
user text → memory retrieval → LLMRouter → response_generated → dialogue history persistence
```

Use this mode to test Jarvis before enabling voice or PC automation. You can also inspect V5 state and test V3 screen reading here:

```text
/self
/world
/see
/read-screen
/explain-screen
/actions
/ls
/read <path>
/safety 4
/write notes.txt :: hello
```

V8 also adds a natural-language bridge to V7 actions, so chat/desktop/voice can understand simple commands like:

```text
покажи файли .
прочитай файл README.md
знайди error в .
створи папку notes
запиши в notes/test.txt :: hello
запусти python --version
```

These commands still pass through the same safety firewall and sandbox. Shell commands require `ACTION_ALLOW_SHELL=true` and safety L5.

### 4. Run with voice

```bash
python main.py --voice
```

Voice mode uses microphone STT through `faster-whisper`, sends recognized speech into the same V1 dialogue/memory loop as `--chat`, then speaks `response_generated` with Piper TTS. If Piper is not configured, it falls back to `pyttsx3` when available. The voice loop waits for the answer/TTS completion before listening again to avoid transcribing its own speaker output.


### 5. Run native desktop interface

```bash
python main.py --desktop
```

This starts a standalone Tkinter app, not a browser dashboard. It includes chat, event stream, screen reading, sleep/consolidation controls, action status, safety level buttons, and quick natural-language action presets.

Build it into a desktop application:

```bash
pip install pyinstaller
python scripts/build_desktop_app.py
```

Output appears in `dist/JAV/`. See `V8_DESKTOP_AUTONOMY_MVP.md`.

### 6. Run with web dashboard

```bash
python main.py --web
```

Open **http://localhost:8000** — live view of kernel state, active modules, event stream.

```bash
# Custom port
python main.py --web --port 9000
```

---

## Connecting an LLM

Edit `config.py` or override at runtime. The system starts without any LLM — just add what you have.

### Ollama (local, free, recommended for start)

```bash
# Make sure Ollama is running
ollama serve
ollama pull llama3.2   # or llama3.1, mistral, phi3, etc.
```

In `config.py`:
```python
llm: LLMRouterConfig = field(default_factory=lambda: LLMRouterConfig(
    ollama_host="http://localhost:11434",
    ollama_model="llama3.2",
))
```

Ollama is auto-detected on startup — no API key needed.

### Anthropic (Claude)

```bash
pip install anthropic
```

```python
llm: LLMRouterConfig = field(default_factory=lambda: LLMRouterConfig(
    anthropic_api_key="${ANTHROPIC_API_KEY}",
    anthropic_model="claude-3-5-sonnet-latest",
))
```

### Gemini

```bash
pip install google-generativeai
```

```python
llm: LLMRouterConfig = field(default_factory=lambda: LLMRouterConfig(
    gemini_api_key="${GEMINI_API_KEY}",
    gemini_model="gemini-2.0-flash",
))
```

### OpenAI / LM Studio / vLLM

```bash
pip install openai
```

```python
llm: LLMRouterConfig = field(default_factory=lambda: LLMRouterConfig(
    openai_api_key="${OPENAI_API_KEY}",
    openai_model="gpt-4o",
    # For LM Studio:
    # openai_base_url="http://localhost:1234/v1",
    # openai_api_key="lm-studio",
))
```

### llama.cpp server

```python
llm: LLMRouterConfig = field(default_factory=lambda: LLMRouterConfig(
    llamacpp_host="http://localhost:8080",
))
```

### Multiple providers + custom routing

```python
llm: LLMRouterConfig = field(default_factory=lambda: LLMRouterConfig(
    ollama_model="llama3.2",
    anthropic_api_key="${ANTHROPIC_API_KEY}",
    anthropic_model="claude-opus-4-7",
    # Route heavy tasks to Claude, everything else to Ollama
    routing={
        "complex_reasoning": "anthropic",
        "creative_imagination": "anthropic",
        "simple_chat": "ollama",
        "summarization": "ollama",
    }
))
```

---

## Sending Events

Any module can trigger cognitive processing by emitting events. Via the web UI (`POST /api/event/emit`) or directly in code:

```python
from core.event_bus import CognitiveEvent, Priority

# Simulate user input
kernel.event_bus.emit(
    CognitiveEvent(
        type="user_utterance",
        data={"text": "Why does my Gradle build keep failing?"},
        source_module="user",
    ),
    Priority.REALTIME,
)
```

The brain will:
1. Select thinking mode (`DELIBERATIVE` or `IMAGINATION` for long questions)
2. Request memory context
3. Call the LLM with assembled context (self-model + working memory + memory)
4. Emit `thought_generated` → `response_generated`
5. Optionally trigger the imagination engine for hypothesis generation

### Trigger imagination directly

```python
kernel.event_bus.emit(
    CognitiveEvent(
        type="imagination_requested",
        data={"text": "Gradle build fails intermittently on CI but not locally"},
        source_module="user",
    ),
    Priority.COGNITIVE,
)
```

Result: 3–7 competing hypotheses → scenario simulation per hypothesis → critic ranking → monologue reflection.

### Request an action (goes through safety layer)

```python
kernel.event_bus.emit(
    CognitiveEvent(
        type="action_request",
        data={
            "action_type": "speak",
            "payload": {"text": "Hello, I am ready."},
            "reason": "Startup greeting",
        },
        source_module="self_model",
    ),
    Priority.REALTIME,
)
# → ActionFirewall validates → action_approved → TTS module executes
```

---

## Permission Levels

The system starts at **L1** (read screen, no writes). Raise it by emitting a grant event or at runtime:

| Level | Name | Allowed |
|-------|------|---------|
| L0 | THINK | think, remember, speak |
| L1 | READ_SCREEN | + screenshot, OCR, read files *(default)* |
| L2 | WEB_SEARCH | + web search, web fetch |
| L3 | OPEN_APPS | + open/close/switch applications |
| L4 | EDIT_FILES | + write/move/delete files in sandbox |
| L5 | RUN_COMMANDS | + shell commands (confirmed only) |
| L6 | AUTONOMOUS | + chained actions (never default) |

```python
# Grant a specific action permanently
kernel.event_bus.emit(
    CognitiveEvent(
        type="user_permission_grant",
        data={"action_type": "write_file"},
        source_module="user",
    ),
    Priority.COGNITIVE,
)

# Raise the global level
kernel.permission_manager.set_level(PermissionLevel.L3_OPEN_APPS)
```

---

## Project Structure

```
C:\AI\JAV\
│
├── main.py                          # Entry point
├── config.py                        # All configuration (KernelConfig, LLMRouterConfig)
│
├── core/
│   ├── kernel.py                    # Kernel + KernelAPI
│   ├── event_bus.py                 # CognitiveEvent + 3-queue EventBus
│   ├── state.py                     # CoreState (rich live snapshot)
│   ├── module_base.py               # CognitiveModule base class
│   ├── module_manager.py            # Auto-discovery and hot-reload
│   ├── attention_router.py          # Budget allocation + event scoring
│   ├── scheduler.py                 # Delayed and repeating tasks
│   ├── persistence.py               # Atomic JSON persistence
│   ├── lifecycle.py                 # Startup / shutdown sequencing
│   ├── llm_router.py                # Multi-LLM provider abstraction
│   ├── thinking_modes.py            # 6 cognition depth levels
│   └── safety/
│       ├── constitution.py          # 14 hard rules (unbypassable)
│       ├── sandbox.py               # Filesystem ACL
│       ├── risk_engine.py           # Danger scoring 0–10
│       ├── permission_manager.py    # L0–L6 permission gate
│       ├── action_firewall.py       # Validation chain
│       └── audit_log.py             # Append-only JSONL log
│
├── modules/
│   ├── tier1_essential/
│   │   ├── memory/                  # STM, episodic, semantic, procedural, social
│   │   ├── working_memory/          # 7-slot active thought buffer
│   │   ├── self_model/              # Identity, confidence, attachment
│   │   ├── emotions/                # VAD emotional model
│   │   ├── hormones/                # Dopamine, cortisol, serotonin, oxytocin
│   │   ├── goals/                   # Goal management and persistence
│   │   └── temporal_engine/         # Session continuity, idle detection
│   │
│   ├── tier2_perception/            # screen · vision · audio (stubs)
│   │
│   ├── tier3_reasoning/
│   │   ├── action_intent/           # V8 natural language → safe V7 actions
│   │   ├── llm/                     # LLM module (uses LLMRouter)
│   │   ├── monologue/               # Internal self-narration
│   │   ├── planner/                 # Goal → action steps (LLM-driven)
│   │   ├── world_model/             # User pattern tracking
│   │   └── imagination/
│   │       ├── theory_builder.py    # Orchestrates imagination cycle
│   │       ├── hypothesis_engine.py # Generates competing theories
│   │       ├── scenario_simulator.py# Simulates outcomes per theory
│   │       ├── critic.py            # Ranks and filters theories
│   │       ├── counterfactuals.py   # "What if X hadn't happened?"
│   │       └── idea_memory.py       # Persistent theory storage
│   │
│   ├── tier4_actions/               # tts (stub, safety-gated)
│   │
│   └── tier5_evolution/
│       ├── dream/                   # Memory consolidation during idle
│       ├── personality/             # Big Five traits, slow drift
│       └── self_learning/           # Heuristics from success/failure
│
└── interfaces/
    ├── desktop/
    │   └── desktop_app.py           # V8 native Tkinter desktop app
    ├── voice/                       # STT/TTS voice interface
    └── web_ui/
        ├── app.py                   # FastAPI + WebSocket dashboard
        └── templates/index.html
```

---

## Persistent State

Everything is stored in `~/.jarvis_brain/`:

| File | Contents |
|------|----------|
| `core_state.json` | Consciousness, energy, focus at shutdown |
| `memory_episodic.json` | Episodic memory |
| `memory_semantic.json` | Semantic knowledge |
| `memory_social.json` | Social memory |
| `goals.json` | In-progress goals |
| `personality.json` | Big Five traits + history |
| `self_model.json` | Legacy identity snapshot |
| `self_model_v5.json` | V5 mature identity, capabilities, limits, reliability |
| `world_model.json` | Legacy observed user patterns |
| `world_model_v5.json` | V5 projects, environment, open loops, causal beliefs |
| `permissions.json` | Granted/denied action overrides |
| `idea_memory.json` | Generated theories and hypotheses |
| `audit.jsonl` | Append-only log of all action attempts |
| `affective_state_v4.json` | V4 emotion/mood/style state |
| `monologue_state_v4.json` | V4 internal monologue buffer, open questions, focus stack |

---

## Development Roadmap

| Version | Status | Focus |
|---------|--------|-------|
| V0 | ✅ Done | Kernel + modules + safety + imagination |
| V1 | ✅ Done | Real LLM dialogue loop + relevant memory retrieval |
| V2 | ✅ Stable MVP | Voice STT + V1 dialogue loop + Piper/pyttsx3 TTS fallback |
| V3 | ✅ MVP Done | Screen reading (OCR + ScreenParser) |
| V4 | ✅ MVP Done | Rich emotions + deep internal monologue |
| V5 | ✅ MVP Done | World model + mature self-model |
| V6 | ✅ MVP Done | Sleep/dream replay + memory consolidation |
| V7 | ✅ MVP Done | PC automation via tier4_actions (safety-gated) |
| V8 | ✅ MVP Done | Native desktop app + conversational safe actions |
| V8.1 | ✅ MVP Done | Settings Center + broader natural voice/chat actions |
| V9 | ✅ MVP Done | Cognitive Project Repair Agent: diagnose → memory/self/world → LLM patch → safety apply |
| V9.1 | ✅ Done | Long-term memory retention + portable paths |
| V9.2 | ✅ Done | SQLite + vector memory search |
| V9.3 | ✅ Done | Web learning/search + improved desktop UI/settings usability |
| V9.4 | ✅ Done | Autonomous task chains: guided/auto task plans with safety gates |
| V9.5 | ✅ Done | Runtime / service mode: watchdog, heartbeat, rotating logs, health checks |
| V9.6 | ✅ MVP Done | Real Vision + GUI Understanding: active window, UI/text elements, safe next-step suggestions |
| V9.7 | ✅ MVP Done | Safe General GUI Automation: observe → reason → action → observe loop via safety gates |
| V10 | ✅ MVP Done | Modular role-based model/API router and profiles |
| V11 | ✅ MVP Done | Proactive companion + system monitor |
| V12 | ✅ MVP Done | Advanced Vision + GUI Automation 2.0: semantic targets, screenshot audit, verify-after-action loop |
| V13 | Next | Advanced task orchestrator + rollback/retry/verifier |


### V8 desktop + conversational action MVP details

V8 adds two practical upgrades:

1. **Native desktop interface** through `python main.py --desktop`. This is a Tkinter app, not the browser dashboard.
2. **Natural action intent layer** through `modules/tier3_reasoning/action_intent/action_intent_module.py`. It converts simple user phrases into V7 `action_request` events.

Supported MVP examples:

```text
покажи файли .
прочитай файл README.md
знайди error в .
створи папку notes
запиши в notes/test.txt :: hello
запусти python --version
```

Important: voice/chat/desktop do **not** bypass safety. Every action still goes through the ActionFirewall, Sandbox, RiskEngine, and PermissionManager.

Build app:

```bash
pip install pyinstaller
python scripts/build_desktop_app.py
```

Repair/fix requests now route into **V9 Project Repair Agent**. It diagnoses the project, pulls cognitive context, asks the LLM for a minimal patch, validates the proposal, and applies only through V7 safety-gated file writes.


### V9 cognitive project repair MVP details

V9 adds `modules/tier3_reasoning/code_repair/code_repair_module.py`, a cognitive repair loop designed to behave like a careful assistant rather than a blind file-rewriter.

Workflow:

```text
user says: "виправ помилки в ."
→ action_intent detects repair intent
→ code_repair starts perception/diagnostics
→ memory_request retrieves relevant past context
→ self_model/world_model/context_request refresh identity/environment state
→ LLMRouter is used as repair cortex for "how to fix" reasoning
→ proposed file contents are locally validated with py_compile
→ proposal is shown to the user
→ user says "застосуй ремонт rp..."
→ V7 action_request/write_file applies through sandbox, permission, risk, audit
```

Useful chat/voice phrases:

```text
виправ помилки в .
почини проєкт у .
fix errors in .
зроби патч для помилки в .
застосуй ремонт rp1234567890
apply repair rp1234567890
```

Slash command equivalents:

```text
/repair .
/apply-repair rp1234567890
```

Configuration:

```env
CODE_REPAIR_V9_ENABLED=true
CODE_REPAIR_MAX_FILES=160
CODE_REPAIR_MAX_FILE_CHARS=18000
CODE_REPAIR_AUTO_APPLY=false
CODE_REPAIR_REQUIRE_LLM=true
```

Safety notes:

- V9 does not write directly to disk.
- Actual modifications are submitted as V7 `write_file` actions.
- File writes require safety L4 and remain sandboxed to `ACTION_WORKSPACE_PATH`.
- If no real LLM is configured, V9 still diagnoses and produces a plan, but will not invent patches.


### V7 safe PC automation MVP details

V7 is implemented in `modules/tier4_actions/automation/action_executor_module.py`. It gives Jarvis limited “hands” while keeping the safety layer in the middle. Raw actions are never executed directly:

```text
chat/LLM/tool request
  → action_request
  → ActionFirewall + Constitution + Sandbox + PermissionManager + RiskEngine
  → action_approved / action_denied / action_pending_confirmation
  → action_executor
  → action_result + response_generated
```

Default workspace:

```text
~/jarvis_workspace
```

Useful commands in `python main.py --chat`:

```text
/actions                         show V7 status and pending actions
/ls [path]                       list files in workspace or allowed path
/read <path>                     read a text file
/search <query> [:: path]        search text files
/safety                          show current safety level
/safety 4                        allow sandboxed file edits
/write <path> :: <content>       write file in sandbox
/append <path> :: <content>      append file in sandbox
/mkdir <path>                    create directory in sandbox
/safety 5                        allow command tier checks
/run python --version            run allowlisted command if shell enabled
/approve <pending_id>            approve one pending risky action
/deny <pending_id>               deny one pending action
```

Important `.env` settings:

```env
ACTIONS_V7_ENABLED=true
ACTION_WORKSPACE_PATH=~/jarvis_workspace
ACTION_ALLOW_SHELL=false
ACTION_COMMAND_TIMEOUT=20
ACTION_ALLOWED_COMMANDS=python,python3,py,pytest,pip,pip3,git
ACTION_MAX_READ_CHARS=12000
ACTION_MAX_LIST_ENTRIES=120
```

Shell commands are disabled by default and still require safety level L5 plus confirmation. V7 does not permit unrestricted PC control.


### V6 implementation details

V6 is implemented in `modules/tier5_evolution/dream/dream_module.py`. It converts recent runtime experience into persistent consolidation reports:

```text
recent events + dialogue turns + monologue + screen/errors
  → sleep_cycle_requested / memory_consolidation_requested
  → dream replay narrative
  → extracted themes, lessons and open loops
  → memory_consolidated + consolidation_lesson + learning_applied
  → self/world/LLM context updates
```

Manual commands in `--chat`:

```text
/sleep
/dream
/consolidate
/memory-consolidate
```

Voice triggers also work in `--voice`, for example: “consolidate memory”, “run sleep cycle”, “запусти сон”, “консолідуй памʼять”.

Persisted state:

```text
~/.jarvis_brain/dream_v6_state.json
```

### V1 implementation details

V1 is now implemented in `modules/tier3_reasoning/llm/llm_module.py` and `modules/tier1_essential/memory/memory_module.py`. Both `--chat` and `--voice` use the same dialogue path:

```text
user_utterance
  → memory_request(query_type=dialogue_context)
  → memory_retrieved(wm + stm + episodic + semantic + social context)
  → LLMRouter.generate(...)
  → response_generated
  → dialogue_turn_completed
  → persisted dialogue_history + persisted memory
```

New test mode:

```bash
python main.py --chat
```

The system still runs without a configured LLM through `NullProvider`, but real dialogue requires Ollama, Gemini, OpenAI-compatible API, Anthropic, or llama.cpp configured through `.env`/`config.py`.


### V2 stable voice details

V2 is wired through `interfaces/voice/voice_loop.py` and `modules/tier4_actions/tts/tts_module.py`:

```text
microphone
  → faster-whisper STT
  → user_utterance(input_mode=voice)
  → V1 memory + LLM dialogue path
  → response_generated
  → Piper TTS or pyttsx3 fallback
  → tts_spoken / tts_error
  → listen again
```

Important voice settings in `.env`:

```env
VOICE_RESPONSE_TIMEOUT=90
VOICE_TTS_WAIT_TIMEOUT=45
VOICE_LISTEN_AFTER_RESPONSE_DELAY=0.35
VOICE_TTS_BACKEND=auto
```

This prevents the microphone from immediately listening while Jarvis is still speaking.


### V3 screen reading MVP details

V3 is wired through `modules/tier2_perception/screen/screen_parser_module.py`. It is request-driven, not always watching the screen. This is intentional for privacy and performance.

Flow:

```text
/see or voice command "what is on screen"
  → screen_capture_requested
  → screenshot via mss
  → OCR via pytesseract/Tesseract
  → lightweight ScreenParser
  → screen_parsed + sensory_input
  → response_generated
```

Chat commands:

```bash
python main.py --chat
/see
/read-screen
/explain-screen
```

Voice triggers in `--voice` mode include:

```text
what is on screen
read the screen
що на екрані
прочитай екран
що тут не так
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install the OCR binary on Ubuntu:

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ukr
```

Important screen settings in `.env`:

```env
SCREEN_READING_ENABLED=true
SCREEN_OCR_LANGUAGE=eng
# For Ukrainian + English OCR after installing language packs:
# SCREEN_OCR_LANGUAGE=eng+ukr
SCREEN_AUTO_WATCH_ENABLED=false
SCREEN_SAVE_SCREENSHOTS=true
```

Screenshots are saved to `~/.jarvis_brain/screenshots/` by default unless `SCREENSHOT_DIR` is set.


### V4 emotion + deep monologue MVP details

V4 upgrades the affective and self-narration layers. It does not claim human feelings; it gives the runtime a bounded internal state that helps with tone, prioritization, memory tags, and future dashboard/sleep systems.

Main files:

```text
modules/tier1_essential/emotions/emotion_module.py
modules/tier3_reasoning/monologue/monologue_module.py
modules/tier3_reasoning/llm/llm_module.py
```

Flow:

```text
user_utterance / memory_retrieved / screen_parsed / goal events
  → affective appraisal
  → emotional_state + response_style_hint
  → deep internal_monologue + monologue_state
  → LLM prompt receives affect/style/monologue context
  → response_generated adapts tone without becoming melodramatic
```

The V4 emotional state tracks:

```text
emotion, mood, valence, arousal, dominance, curiosity, frustration,
confidence, social_warmth, cognitive_load, response_style, triggers
```

Important V4 settings in `.env`:

```env
EMOTION_V4_ENABLED=true
EMOTION_STATE_EMIT_INTERVAL=4.0
EMOTION_DECAY_STRENGTH=0.985
MONOLOGUE_V4_ENABLED=true
MONOLOGUE_INTERVAL=6.0
```

Persisted files in `~/.jarvis_brain/` now also include:

```text
affective_state_v4.json
monologue_state_v4.json
```

### V5 world model + mature self-model details

V5 upgrades Jarvis from a reactive assistant into a runtime that keeps a grounded model of itself and its environment.

Main files:

```text
modules/tier1_essential/self_model/self_model_module.py
modules/tier3_reasoning/world_model/world_model_module.py
modules/tier3_reasoning/llm/llm_module.py
```

Self-model now tracks:

```text
identity, role, purpose, operating principles, real limits,
capability inventory, active interfaces, confidence, reliability,
autonomy level, cognitive maturity, recent successes/failures
```

World-model now tracks:

```text
environment state, active projects, project stages, open loops,
user intent trends, recurring patterns, causal beliefs, timeline
```

The LLM prompt now receives V5 context:

```text
user_utterance
  → memory retrieval
  → cached self_model_updated + world_context
  → LLM prompt with memory + affect + monologue + self/world model
  → response_generated
```

New chat inspection commands:

```bash
python main.py --chat
/self
/world
```

Important V5 settings in `.env`:

```env
SELF_MODEL_V5_ENABLED=true
SELF_MODEL_SNAPSHOT_INTERVAL=12.0
SELF_MODEL_REFLECTION_INTERVAL=45.0
WORLD_MODEL_V5_ENABLED=true
WORLD_MODEL_SNAPSHOT_INTERVAL=10.0
WORLD_MODEL_MAX_TIMELINE_ITEMS=80
WORLD_MODEL_MAX_OPEN_LOOPS=25
```

Persisted files in `~/.jarvis_brain/` now also include:

```text
self_model_v5.json
world_model_v5.json
```

---

## Writing a New Module

Create a file anywhere under `modules/` following the `create_module()` convention — it will be auto-discovered on next startup.

```python
# modules/tier3_reasoning/my_module/my_module.py
from core import CognitiveModule, CognitiveEvent as Event, Priority

class MyModule(CognitiveModule):
    def __init__(self):
        super().__init__(
            module_id="my_module",
            cost={"cpu": 0.10, "gpu": 0.0, "ram": 0.05},
        )

    def initialize(self, kernel):
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id, ["user_utterance", "goal_activated"]
        )

    async def on_event(self, event: Event):
        if event.type == "user_utterance":
            text = event.data.get("text", "")
            # Do something, then emit
            self.kernel.event_bus.emit(
                Event(
                    type="thought_generated",
                    data={"text": f"My module processed: {text}"},
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )

    def update(self, dt: float):
        pass  # called every tick


def create_module():
    return MyModule()
```

**Rules:**
- Never import another module directly — use events
- Never emit `action_request` — emit it and let the firewall decide
- Use `kernel.persistence.save("my_namespace", data)` in `shutdown()`
- Use `kernel.llm_router.generate(prompt, task_type=TaskType.SIMPLE_CHAT)` for LLM access

---

## Requirements

```
Python 3.10+
fastapi
uvicorn[standard]
websockets

# Optional LLM providers (install what you need):
anthropic          # Claude
openai             # OpenAI / LM Studio / vLLM
google-generativeai # Gemini

# Local LLM (no pip install needed — standalone binary):
# Ollama:   https://ollama.com
# llama.cpp: https://github.com/ggerganov/llama.cpp
```

Minimum hardware: any PC with 4 GB RAM runs the full cognitive runtime without an LLM.  
With local LLM: 8 GB RAM for 7B models, 16 GB for 13B+.


---

## V8.1 — Desktop Settings Center + Natural Action Router

V8.1 adds a native **Settings Center** to the desktop app and expands natural language control.

Start the desktop app:

```bash
python main.py --desktop
```

Open **Settings Center** from the right-side controls to edit `.env` settings for:

- LLM providers;
- voice STT/TTS;
- Piper and pyttsx3;
- screen OCR;
- safe PC actions;
- sleep/consolidation;
- emotion/monologue;
- self/world model;
- web dashboard/API.

Natural phrases now work from chat, voice and desktop, not only slash commands:

```text
прочитай екран
запусти сон
покажи файли .
прочитай файл README.md
знайди error в .
запиши в notes/test.txt :: hello
запусти python --version
постав safety 4
схвали p123
виправ помилки в .
```

All external actions still pass through the V7 safety layer and workspace sandbox.

Repair requests now start a safe diagnostics pass inside `ACTION_WORKSPACE_PATH`; automatic project-wide rewrites are intentionally not silent.

---

## V9.1 Long-Term Memory + Portable Mode

V9.1 fixes the earlier short episodic-memory retention and adds portable storage controls.

### Memory location

JAV now stores brain state in:

```env
JARVIS_DATA_DIR=/path/to/brain-data
```

If `JAV_PORTABLE=true`, the default becomes:

```text
data/brain
```

beside the program folder. This makes it suitable for a portable HDD/SSD.

### Portable setup

Initialize portable folders in the current project:

```bash
python main.py --init-portable
```

Create a portable copy on another drive:

```bash
python scripts/install_portable.py E:/JAV
```

The portable copy creates:

```text
data/brain       memory and brain state
data/workspace   safe editable workspace
data/screenshots OCR screenshots
```

### Desktop settings

Open:

```bash
python main.py --desktop
```

Then use **Settings Center → Portable / Paths** and **Memory / Sleep** to set:

```text
JAV_PORTABLE
JARVIS_DATA_DIR
ACTION_WORKSPACE_PATH
SCREENSHOT_DIR
MEMORY_EPISODIC_RETENTION_DAYS
MEMORY_EPISODIC_MAX_ITEMS
```

### Memory status

In chat or desktop, ask naturally:

```text
покажи стан пам'яті
де зберігається пам'ять
memory status
```

or use:

```text
/memory
/storage
```

### Retention

Default V9.1 policy:

```env
MEMORY_STM_LIFETIME_SECONDS=30
MEMORY_EPISODIC_RETENTION_DAYS=730
MEMORY_EPISODIC_MAX_ITEMS=20000
MEMORY_ARCHIVE_DECAYED=true
MEMORY_SEMANTIC_AUTOSTORE=true
MEMORY_SAVE_INTERVAL_SECONDS=60
```

This means normal episodic memories can persist for about two years, and semantic/procedural/user-profile memories can persist indefinitely as long as the data folder is kept.


## V9.2 Long-Term Memory Search

Implemented in `JAV_v9_2_sqlite_vector_memory_mvp`: durable SQLite memory plus local hashed-vector semantic search.

New commands:

```text
/memory
/recall <query>
/memory-search <query>
згадай <тема>
пошукай в пам'яті <тема>
```

Memory files are stored under `JARVIS_DATA_DIR` / portable `data/brain`:

```text
longterm_memory.sqlite3
memory_episodic.json
memory_semantic.json
memory_episodic_archive.json
```

Recommended portable setup:

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
MEMORY_EPISODIC_RETENTION_DAYS=3650
MEMORY_SQLITE_ENABLED=true
MEMORY_VECTOR_ENABLED=true
```

This is still not fine-tuning of the LLM weights. It is durable experience/memory retrieval, which gives the LLM much better context over months or years.


## V9.3 Web Learning + Desktop UI Upgrade

V9.3 adds a request-driven web learning/search module and improves the native desktop interface.

### Web learning commands

```text
/web-search <query>
/web-learn <topic>
/web-fetch <url>
пошукай в інтернеті <запит>
вивчи <тему>
прочитай сайт <url>
```

Flow:

```text
voice/chat/desktop request
→ natural action router
→ web_learning module
→ search/fetch sources
→ optional LLM summary
→ sourced semantic memory write
→ SQLite/vector recall later
```

The module stores source URLs, domains, checked time, confidence and a compact learning note. It does not browse autonomously forever by default; it learns only when requested, so web learning stays controllable and auditable.

New settings:

```env
WEB_LEARNING_ENABLED=true
WEB_SEARCH_ENABLED=true
WEB_LEARN_STORE_ENABLED=true
WEB_SEARCH_MAX_RESULTS=5
WEB_LEARN_MAX_SOURCES=4
WEB_FETCH_TIMEOUT_SECONDS=12
WEB_FETCH_MAX_CHARS_PER_PAGE=9000
WEB_USER_AGENT=JAV-WebLearning/0.1
```

### Desktop UI upgrade

The desktop app now uses a resizable split layout with tabs:

```text
Conversation panel
Right tabs: Controls / Commands / Events
Settings Center with search, scrollable groups and Browse buttons for paths/files
```

This fixes the old problem where settings/buttons could go off-screen on smaller displays.


## V9.4 — Autonomous Task Chains MVP

Status: ✅ MVP Done

JAV can now turn broad goals into guided or controlled-auto task chains.

Examples:

```bash
python main.py --chat
```

```text
/task розберися з помилками в .
/task-step
/tasks
/task-auto досліди тему vector memory і запиши висновки
```

Natural language also works from chat, voice, and desktop:

```text
розберися з помилками в .
продовжуй задачу
статус задачі
```

The chain uses memory, self/world model, LLM planning, screen/web/repair/actions, and V7 safety gates. File writes and shell actions still require the configured safety level and approval when needed.


---

## V9.5 — Runtime / Service Mode MVP

V9.5 adds the first production-style runtime layer so JAV can run more like a local assistant service instead of only a terminal/Desktop experiment.

### New commands

```bash
python main.py --service
python scripts/watchdog.py
```

Convenience launchers:

```text
run_service.bat
run_watchdog.bat
run_service.sh
run_watchdog.sh
```

### What V9.5 adds

- rotating file logs;
- heartbeat file for watchdogs;
- PID file;
- runtime health snapshot;
- chat/Desktop health commands;
- user-level systemd service generator;
- Windows startup launcher generator;
- graceful signal handling for service shutdown;
- optional shutdown memory consolidation request.

### Chat/Desktop commands

```text
/runtime
/runtime-status
/health
/service-status
/self-test
/runtime-self-test
/health-check
```

Natural language examples:

```text
покажи runtime status
перевір стан програми
запусти runtime self-test
```

### Portable service layout

When `JAV_PORTABLE=true`, runtime files live beside the program:

```text
JAV/
  data/
    brain/
      runtime_heartbeat.json
      runtime_health.json
      runtime.pid
      logs/
        jav_service.log
    workspace/
    screenshots/
```

See `V9_5_RUNTIME_SERVICE_MODE_MVP.md` for setup details.


---

## V9.6 — Real Vision + GUI Understanding MVP

Status: ✅ MVP Done

V9.6 upgrades screen reading from raw OCR into a safer first version of visual/UI understanding. It still does **not** click or type automatically; it analyzes the screen and suggests next steps. Any future GUI control must go through V7 safety gates.

### New chat commands

```text
/vision
/gui
/understand-screen
/analyze-screen
```

Existing screen commands still work:

```text
/see
/screen
/read-screen
/explain-screen
```

### Natural voice/chat examples

```text
проаналізуй екран
розбери інтерфейс
що натиснути?
куди натиснути?
analyze screen
understand gui
```

### What V9.6 detects

- screenshot dimensions and saved path;
- active window title when `pygetwindow` can access it;
- OCR text;
- important error/warning/traceback blocks;
- approximate UI/text elements with bounding boxes;
- likely context, such as terminal traceback, code editor, browser, settings screen;
- recommended next steps, such as using `/repair`, installing missing modules, checking permissions, or manually pressing visible buttons.

### New settings

```env
SCREEN_VISION_ENABLED=true
SCREEN_GUI_UNDERSTANDING_ENABLED=true
SCREEN_ACTIVE_WINDOW_ENABLED=true
SCREEN_MAX_UI_ELEMENTS=40
SCREEN_MIN_UI_CONFIDENCE=35
```

### Dependency note

The core still works without GUI dependencies. For best screen understanding install:

```bash
pip install mss Pillow pytesseract pygetwindow
```

System OCR is still required for Tesseract:

```bash
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ukr
```


---

## V9.7 — Safe General GUI Automation MVP

Status: ✅ MVP Done

V9.7 turns V9.6 screen understanding into a controlled GUI agent. It is **not** a hardcoded YouTube/browser script. The loop is general:

```text
user goal by voice/chat/desktop
→ observe screen with V9.6
→ LLM/heuristic chooses one small next action
→ V7 safety firewall + permission level + confirmation
→ pyautogui/webbrowser executes the approved step
→ observe again
```

Example:

```text
Джарвіс, знайди музику на YouTube і включи щось спокійне.
```

The first step can open a YouTube search page. Further clicking/typing is selected from the current screen state and still goes through safety gates. This makes the agent adaptable to different interfaces instead of being locked to one scenario.

### Commands

```text
/gui-task <goal>
/gui-auto <goal>
/gui-step [task_id]
/gui-status [task_id]
/gui-cancel [task_id]
```

### Natural voice/chat examples

```text
знайди музику на YouTube
відкрий браузер і знайди документацію Python
натисни кнопку Continue
введи в поле пошуку lofi music
продовжуй GUI задачу
статус GUI
```

### Safety model

V9.7 refuses or blocks sensitive actions such as passwords, tokens, payments, purchases and irreversible confirmations. Risky GUI actions require safety level/confirmation. Voice cannot bypass the same firewall used by file actions and shell commands.

### New settings

```env
GUI_AUTOMATION_ENABLED=true
GUI_AUTOMATION_AUTO_ENABLED=false
GUI_AUTOMATION_MAX_STEPS=12
GUI_AUTOMATION_STEP_DELAY_SECONDS=1.0
GUI_AUTOMATION_REQUIRE_CONFIRMATION=true
GUI_AUTOMATION_BLOCK_SENSITIVE=true
GUI_AUTOMATION_ALLOWED_ACTIONS=observe,done,open_url,open_app,click_xy,click_text,type_text,press,hotkey,scroll,wait
```

### Dependencies

```bash
pip install pyautogui
```

On Linux, GUI automation also requires a real desktop session and may need OS packages for screenshots/keyboard/mouse integration.

---

## V10 — Modular Model/API Router MVP

Status: ✅ MVP Done

V10 makes JAV model-role based instead of single-model based. Different parts of the brain can use different providers/models:

```text
fast      → quick dialogue and summaries
reason    → deep thinking / analysis
code      → project repair and patches
critic    → future verification/review loops
vision    → screen/vision reasoning
embedding → semantic memory/vector search role
action    → task-chain and GUI action planning
```

### Model profiles

```env
MODEL_PROFILE=offline
```

Built-in profiles:

```text
offline
balanced
power
code
voice_companion
custom
```

### Role override example

```env
MODEL_PROFILE=custom
MODEL_FAST_PROVIDER=ollama
MODEL_FAST_NAME=qwen2.5:7b
MODEL_REASON_PROVIDER=ollama
MODEL_REASON_NAME=llama3.1:8b
MODEL_CODE_PROVIDER=ollama
MODEL_CODE_NAME=qwen2.5-coder:7b
MODEL_ACTION_PROVIDER=ollama
MODEL_ACTION_NAME=qwen2.5:7b
MODEL_VISION_PROVIDER=ollama
MODEL_VISION_NAME=llava
```

### Status commands

```text
/models
/model-status
/model-health
/model-profile
```

Natural language:

```text
покажи статус моделей
яка модель активна
model health
```

Settings Center now includes a **Model Profiles / Router** tab where the roles, providers, models, fallbacks and default generation settings can be configured.

---

## V11 — Proactive Companion + System Monitor MVP

Status: ✅ MVP Done

V11 moves JAV closer to a permanent companion: it monitors the local machine/runtime/model stack and can proactively notify you when something likely needs attention.

### New modules

```text
modules/tier1_essential/system_monitor/system_monitor_module.py
modules/tier3_reasoning/proactive/proactive_assistant_module.py
```

### What it monitors

```text
CPU / RAM / disk usage
portable data drive and workspace disk
network availability
Ollama health
model-router role availability
runtime health/error signals
recent task/repair/gui/web/action errors
```

### Commands

```text
/system
/monitor
/system-status
/diagnose-system
/proactive
/proactive-status
/daily-summary
```

Natural language also works:

```text
перевір систему
діагностуй систему
стан комп'ютера
покажи proactive status
що ти помітив
зроби підсумок дня
```

### Safety / anti-spam behavior

Proactive messages are conservative by default:

```text
importance threshold
per-issue cooldown
chat/UI notifications on
spoken proactive alerts off by default
```

Enable spoken alerts only after testing:

```env
PROACTIVE_SPEAK_NOTIFICATIONS=true
```

### V11 config

```env
SYSTEM_MONITOR_ENABLED=true
SYSTEM_MONITOR_INTERVAL_SECONDS=20
SYSTEM_CPU_WARN_PERCENT=90
SYSTEM_MEMORY_WARN_PERCENT=88
SYSTEM_DISK_WARN_PERCENT=90
SYSTEM_TEMP_WARN_C=85
SYSTEM_CHECK_NETWORK=true
SYSTEM_CHECK_OLLAMA=true
SYSTEM_CHECK_MODELS=true

PROACTIVE_COMPANION_ENABLED=true
PROACTIVE_CHAT_NOTIFICATIONS=true
PROACTIVE_SPEAK_NOTIFICATIONS=false
PROACTIVE_MIN_IMPORTANCE=0.55
PROACTIVE_COOLDOWN_SECONDS=300
PROACTIVE_DAILY_SUMMARY_ENABLED=true
```


## V12 — Advanced Vision + GUI Automation 2.0 MVP

V12 upgrades the V9.7 GUI agent from simple observe→act steps into a safer verifyable desktop-control loop.

### Core loop

```text
observe screen
→ parse OCR/UI elements
→ choose one semantic action
→ send through V7 safety firewall
→ screenshot before/after action
→ observe again
→ verify whether the screen changed or the goal progressed
→ continue only if guided/auto policy allows it
```

### What changed

```text
- semantic click target matching with configurable threshold
- verify-after-action screen observation
- screenshot audit before/after GUI actions
- safer pyautogui action executor implementation
- support for open_url/open_app/click/type/press/hotkey/scroll/wait
- no guessing coordinates when a semantic target is not visible
```

### Example

```text
User: Джарвіс, знайди музику на YouTube.
JAV: opens a YouTube search via the GUI action layer, captures before/after screenshots, verifies the screen, then waits for the next guided step or continues in auto mode if enabled.
```

### Safety

V12 still does **not** give unrestricted PC control. Every GUI action goes through the same V7 firewall, risk engine, permission levels and pending approvals. It blocks sensitive text such as passwords, tokens, payment data and risky hotkeys.

### Config

```env
GUI_AUTOMATION_ENABLED=true
GUI_AUTOMATION_AUTO_ENABLED=false
GUI_AUTOMATION_VERIFY_AFTER_ACTION=true
GUI_AUTOMATION_SCREENSHOT_AUDIT=true
GUI_AUTOMATION_SEMANTIC_CLICK_THRESHOLD=35
GUI_AUTOMATION_MAX_RETRIES_PER_STEP=2
GUI_AUTOMATION_ALLOWED_ACTIONS=observe,done,open_url,open_app,click_xy,click_text,type_text,press,hotkey,scroll,wait
```


## V13 Advanced Task Orchestrator

V13 adds stronger long-task autonomy: strategy A/B/C, step verification, retries, rollback guidance, progress scoring and full task reports.

Commands:

```text
/task <goal>
/task-auto <goal>
/task-step [task_id]
/task-retry [task_id] [step_id]
/task-report [task_id]
/task-resume [task_id]
/task-cancel [task_id]
```

The orchestrator still uses the same safety layer. File writes, shell commands, repair application and GUI actions are never allowed to bypass V7 safety/approval.

Roadmap update:

```text
V12 ✅ Advanced Vision + GUI Automation 2.0
V13 ✅ Advanced Task Orchestrator MVP
V14 ⏭ Skill Learning + Knowledge Graph
```


## V14 Skill Learning + Knowledge Graph MVP

Added procedural skills, auto-learning from tasks/repair/web/action events, lightweight knowledge graph, `/skills`, `/skill`, `/learn-skill`, `/knowledge`, and Settings Center controls.
