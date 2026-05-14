# V5 — World Model + Mature Self-Model MVP

V5 adds grounded self-awareness and world-awareness to the runtime. This is not mystical consciousness; it is a practical persistent model used by the dialogue system, dashboard, memory, planning, and later sleep/automation modules.

## Implemented

- Replaced the old `self_model_module.py` with V5 mature self-model.
- Replaced the old `world_model_module.py` with V5 structured world model.
- Updated the LLM dialogue module so responses can use self/world context.
- Added `/self` and `/world` inspection commands in `python main.py --chat`.
- Added config/env controls for V5 snapshot/reflection intervals.
- Added persistent files:
  - `~/.jarvis_brain/self_model_v5.json`
  - `~/.jarvis_brain/world_model_v5.json`

## Self-model now tracks

- identity and role
- purpose and operating principles
- real capabilities and hard limits
- active interfaces: chat, voice, screen
- confidence, reliability, autonomy level, cognitive maturity
- recent successes/failures
- self-reflection events

## World-model now tracks

- environment state: screen, voice, LLM, safety
- active project state, currently `JAV / Jarvis Brain Core`
- open loops and unresolved tasks
- user intent trends
- recurring patterns
- causal beliefs
- recent timeline

## Dialogue integration

The V1 dialogue loop now receives:

```text
memory context
+ affective state
+ internal monologue
+ V5 self-model
+ V5 world-model
```

This lets Jarvis answer from grounded context instead of pretending to know things.

## Test

```bash
python -m compileall -q .
python main.py --help
python main.py --chat
```

Inside chat:

```text
/self
/world
```

## Next

V6 should implement sleep/dream replay and memory consolidation:

```text
idle detector
→ collect recent dialogue/world/self/emotion timeline
→ summarize useful lessons
→ consolidate into memory/world model
→ propose improvements without directly modifying core code
```
