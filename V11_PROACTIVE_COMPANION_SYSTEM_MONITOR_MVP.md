# V11 Proactive Companion + System Monitor MVP

V11 adds the first real “always beside you” layer.

## Goal

Make JAV notice system/runtime/model problems and surface them proactively, without becoming noisy or unsafe.

## Added

- `system_monitor` module
- `proactive_assistant` module
- Desktop UI buttons for system/proactive/daily summary
- Settings Center tabs for System Monitor and Proactive Companion
- Chat commands and natural-language intents
- Conservative notification rules with cooldowns

## Event flow

```text
system_monitor
→ system_snapshot
→ system_alert
→ proactive_assistant
→ proactive_notification
→ response_generated / desktop chat / optional TTS
```

## Commands

```text
/system
/diagnose-system
/proactive
/daily-summary
```

## Natural phrases

```text
перевір систему
діагностуй систему
що з комп'ютером
покажи proactive status
що ти помітив
зроби підсумок дня
```

## What this makes possible

- JAV can warn about disk/RAM/CPU/network/model/runtime issues.
- JAV can explain what it noticed.
- JAV can suggest the next safe action.
- JAV can later launch task chains with user approval.

## Still not final Jarvis-level

Needs future work:

- system tray notifications
- wake word / push-to-talk
- richer process/GPU monitoring
- scheduled checks
- automatic task-chain proposal flow
- do-not-disturb based on user activity
