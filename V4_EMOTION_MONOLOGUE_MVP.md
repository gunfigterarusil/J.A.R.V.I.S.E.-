# V4 Emotion + Deep Monologue MVP

V4 upgrades the project from basic VAD emotion labels and random idle thoughts to a richer affective/context layer.

## What changed

### Emotion module

`modules/tier1_essential/emotions/emotion_module.py` now keeps a bounded affective state:

- `emotion`
- `mood`
- `valence`
- `arousal`
- `dominance`
- `curiosity`
- `frustration`
- `confidence`
- `social_warmth`
- `cognitive_load`
- `response_style`
- recent `triggers`

It listens to user messages, memory retrieval, screen parsing, goal results, action approvals/denials, and TTS status.

It emits:

- `emotional_state`
- `emotion_changed`
- `emotional_tag`
- `response_style_hint`

### Monologue module

`modules/tier3_reasoning/monologue/monologue_module.py` now keeps a deeper internal thought thread:

- latest internal thought
- open questions
- active goals
- focus stack
- recent dialogue context
- affective context
- screen-reading context

It emits:

- `internal_monologue`
- `monologue_state`

### LLM dialogue integration

`modules/tier3_reasoning/llm/llm_module.py` now includes:

- affective state in the prompt
- response style hints
- latest internal monologue context
- open questions/focus stack

This does **not** make the model pretend to have human emotions. It uses emotion state only as an internal prioritization/style signal.

## Environment settings

```env
EMOTION_V4_ENABLED=true
EMOTION_STATE_EMIT_INTERVAL=4.0
EMOTION_DECAY_STRENGTH=0.985
MONOLOGUE_V4_ENABLED=true
MONOLOGUE_INTERVAL=6.0
```

## Test

```bash
python -m compileall -q .
python main.py --chat
```

Then talk normally. The dialogue module will use the V4 affect/monologue context automatically.

## Roadmap status

```text
V0 ✅ Done
V1 ✅ Done
V2 ✅ Stable MVP
V3 ✅ MVP Done
V4 ✅ MVP Done
V5 ⏭ Next: world model + mature self-model
```
