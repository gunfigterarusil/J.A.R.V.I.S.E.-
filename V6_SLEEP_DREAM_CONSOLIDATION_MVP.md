# V6 Sleep / Dream Replay / Memory Consolidation MVP

V6 adds an offline consolidation layer to Jarvis Brain Core.

## What it does

```text
recent events
+ dialogue turns
+ thoughts / monologue
+ screen observations
+ errors / safety events
→ replay
→ themes
→ lessons
→ dream narrative
→ memory_consolidated
→ self/world/LLM context update
```

## New module

```text
modules/tier5_evolution/dream/dream_module.py
```

The old random dream stub has been replaced with a real V6 module that:

- collects recent runtime events;
- stores recent dialogue pairs;
- detects open loops;
- extracts recurring themes;
- creates consolidation lessons;
- builds a dream replay narrative;
- persists reports to disk;
- emits events to memory, self-model, world-model and LLM modules.

## New commands

In terminal chat mode:

```bash
python main.py --chat
```

Then:

```text
/sleep
/dream
/consolidate
/memory-consolidate
```

## Voice triggers

In voice mode, Jarvis can trigger V6 from phrases such as:

```text
consolidate memory
run sleep cycle
dream replay
запусти сон
консолідуй пам'ять
консолідація пам'яті
```

## New events

```text
sleep_cycle_requested
memory_consolidation_requested
dream_request
sleep_state_changed
dream_narrative
memory_consolidated
sleep_cycle_completed
consolidation_lesson
learning_applied
```

## Persistence

V6 saves its state here:

```text
~/.jarvis_brain/dream_v6_state.json
```

It stores:

```text
last consolidation report
recent lessons
recent dream narratives
open loops
consolidation history
```

## Config

`.env`:

```env
SLEEP_V6_ENABLED=true
SLEEP_AUTO_ENABLED=true
SLEEP_AUTO_INTERVAL=900
SLEEP_IDLE_THRESHOLD=90
SLEEP_ENERGY_THRESHOLD=0.38
SLEEP_MANUAL_MIN_GAP=3.0
SLEEP_MAX_REPLAY_EVENTS=80
SLEEP_MAX_DIALOGUE_PAIRS=24
SLEEP_MAX_LESSONS_PER_CYCLE=8
```

## Current limits

This MVP does not yet use embeddings or a vector DB. Theme extraction is lightweight keyword-based. It is intentionally safe: it does not modify code, execute actions or rewrite memory destructively.

## Next logical step

V7: safety-gated PC automation via `tier4_actions`.
