# V9 — Project Repair Agent MVP

V9 turns ordinary chat/voice requests like “виправ помилки в проєкті” into a safe cognitive repair workflow.

## Goal

Make repair behave like a thinking system, not a blind script:

```text
perception → memory → self/world context → planning → LLM reasoning → validation → safety → proposal → apply
```

## What participates

- **Perception / diagnostics:** scans Python files and compile errors.
- **Memory:** receives a `memory_request` for relevant repair context.
- **Self-model:** receives `self_model_request` so the repair prompt knows capabilities/limits.
- **World-model:** receives `world_model_request` so the repair prompt understands active project/environment state.
- **Monologue/emotion:** snapshots are added to the repair context.
- **LLM router:** used only as a reasoning cortex for how to repair.
- **Safety layer:** all writes still go through V7 `action_request` → firewall → sandbox → risk → permissions.
- **Action executor:** performs approved file writes.

## Commands

Natural language:

```text
виправ помилки в .
почини проєкт у .
fix errors in .
зроби патч для помилки в .
застосуй ремонт rp1234567890
apply repair rp1234567890
```

Slash commands:

```text
/repair .
/apply-repair rp1234567890
```

## Safety

V9 does not silently overwrite files. It creates a repair proposal. Applying it sends `write_file` requests through V7.

For file changes:

```text
/safety 4
застосуй ремонт rp...
```

If the firewall asks for confirmation:

```text
/approve p...
```

## Limitations

- MVP focuses on Python syntax/compile errors first.
- Deep test-driven repair needs shell actions enabled and safety L5.
- Without a real LLM provider, V9 diagnoses and explains but does not invent full-file patches.
