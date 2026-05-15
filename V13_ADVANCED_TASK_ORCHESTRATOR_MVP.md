# V13 Advanced Task Orchestrator MVP

V13 upgrades task chains from a simple linear checklist into a safer long-task orchestrator.

## New behavior

A user request now follows this cognitive flow:

```text
voice/chat/desktop
→ task_chain_requested
→ context snapshot from memory/self/world/system
→ strategy A/B/C
→ safe steps
→ execution through existing modules
→ verifier
→ retry if possible
→ rollback guidance
→ final report
→ memory/sleep consolidation
```

## Commands

```text
/task <goal>              Create a guided task chain
/task-auto <goal>         Create a controlled auto chain
/tasks                    Show active task chain status
/task-status [task_id]    Show task status
/task-step [task_id]      Run next step
/task-retry [task_id] [step_id]
/task-report [task_id]    Show full report
/task-resume [task_id]    Continue in controlled auto mode
/task-cancel [task_id]    Cancel task
```

Natural language also works:

```text
розберися з цією проблемою
продовжуй задачу
статус задачі
повний звіт задачі
повтори крок ще раз
```

## New safeguards

- Guided mode is still default.
- Auto mode can continue only through safe/verified steps.
- File writes, shell commands and GUI actions still pass through V7 safety.
- Failed steps get retry limits.
- Risky steps include rollback guidance.
- A final report includes findings, verification result and next safe action.

## New settings

```env
TASK_CHAINS_ENABLED=true
TASK_CHAINS_AUTO_STEP_DEFAULT=false
TASK_CHAINS_MAX_STEPS=12
TASK_CHAINS_STEP_TIMEOUT_SECONDS=120
TASK_CHAINS_MAX_RETRIES_PER_STEP=2
TASK_CHAINS_VERIFIER_ENABLED=true
TASK_CHAINS_ROLLBACK_ENABLED=true
TASK_CHAINS_STRATEGY_COUNT=3
TASK_CHAINS_AUTO_CONTINUE_AFTER_SAFE_STEP=true
```

## Notes

This is not uncontrolled autonomy. It is a supervised Jarvis-style task loop:

```text
plan → act safely → verify → retry/rollback → report
```
