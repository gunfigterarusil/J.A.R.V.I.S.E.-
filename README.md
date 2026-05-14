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
| V9 | Next | Android / server / robot bodies |


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

Repair/fix requests are recognized, but full autonomous code repair is intentionally not unrestricted yet. The next deeper upgrade would be a Code Repair Agent: inspect → test → propose patch → approve → write → verify.


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
