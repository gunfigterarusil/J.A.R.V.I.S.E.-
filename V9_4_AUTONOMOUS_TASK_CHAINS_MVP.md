# V9.4 Autonomous Task Chains MVP

This upgrade adds controlled multi-step task execution to JAV.

## What it does

A broad request such as:

```text
розберися з помилками в .
```

can now become a safe task chain:

```text
user voice/chat/desktop
→ task_chains
→ memory/self/world context
→ planner/LLM plan
→ step execution
→ V7 safety/action executor or cognitive modules
→ observations
→ next step / final report
```

## Modes

- **guided**: creates a plan and waits for `/task-step` between steps.
- **auto**: continues low-risk steps automatically until completion, failure, or safety confirmation.

Writes, shell commands and repair application still use V7 safety gates.

## Chat commands

```text
/task <goal>
/task-auto <goal>
/tasks
/task-status [task_id]
/task-step [task_id]
/task-resume [task_id]
/task-cancel [task_id]
```

## Natural language

```text
розберися з помилками в .
займись цією задачею
виріши задачу перевірки проєкту
продовжуй задачу
статус задачі
скасуй задачу
продовжуй автономно
```

## Settings

```env
TASK_CHAINS_ENABLED=true
TASK_CHAINS_AUTO_STEP_DEFAULT=false
TASK_CHAINS_MAX_STEPS=8
TASK_CHAINS_STEP_TIMEOUT_SECONDS=90
```

## Storage

Task-chain state is saved to:

```text
data/brain/task_chains_v9_4.json
```

or the configured `JARVIS_DATA_DIR`.
