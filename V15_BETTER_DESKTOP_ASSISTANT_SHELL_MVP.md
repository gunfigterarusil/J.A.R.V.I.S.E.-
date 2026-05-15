# V15 — Better Desktop App / Assistant Shell MVP

V15 improves `python main.py --desktop` from a simple technical UI into a more practical assistant shell.

## Goals

- Keep the UI native and lightweight with Tkinter.
- Make controls fit on-screen and group them logically.
- Provide a visible dashboard for the current assistant state.
- Add approval controls for safety-gated actions.
- Add task/GUI/memory/model panels for daily use.
- Add optional tray and desktop notifications without making them mandatory dependencies.

## New UI sections

```text
Dashboard      — quick status/actions, voice start/stop, safety levels
Commands       — natural language command palette
Tasks          — task chain and GUI task controls/feed
Approvals      — approve/deny pending V7 confirmations
Memory/Skills  — recall, skill library, knowledge graph shortcuts
Models         — model router role status
Events         — recent event stream
```

## Optional desktop features

```text
DESKTOP_TRAY_ENABLED=true
DESKTOP_NOTIFICATIONS_ENABLED=true
```

Optional packages:

```bash
pip install pystray plyer pillow
```

If these packages are missing, JAV still starts. It simply reports that tray/notification support is unavailable.

## Voice launcher

The desktop shell can start/stop voice mode as a separate process:

```text
Voice button → python main.py --voice
```

This keeps the desktop kernel stable while voice dependencies run separately.

## Safety

V15 does not weaken the existing safety model. Approvals are surfaced more clearly, but file writes, shell, GUI actions and repair application still pass through V7 safety gates.
