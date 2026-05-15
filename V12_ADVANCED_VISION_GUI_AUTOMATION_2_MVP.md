# V12 — Advanced Vision + GUI Automation 2.0 MVP

V12 upgrades JAV's GUI layer from a simple guided click/typing helper into a safer screen-driven automation loop.

## Goal

Make desktop control more general and less hardcoded:

```text
observe screen
→ understand GUI/text targets
→ choose one safe semantic step
→ execute through V7 safety
→ screenshot before/after
→ verify screen changed/progressed
→ continue or ask for the next instruction
```

## New behavior

- Semantic target matching for `click_text`.
- No blind coordinate guessing when text target is not visible.
- Screenshot audit for GUI actions.
- Verification observation after every successful GUI action.
- GUI action executor methods implemented explicitly:
  - `open_url`
  - `open_app`
  - `gui_click`
  - `gui_type_text`
  - `gui_press`
  - `gui_hotkey`
  - `gui_scroll`
  - `gui_wait`
- Safer blocks for passwords, tokens, payment text, and risky hotkeys.

## Usage

```bash
python main.py --chat
```

Then:

```text
/gui-task знайди музику на YouTube
/gui-step
/gui-status
```

Natural language also works:

```text
Джарвіс, знайди музику на YouTube
продовжуй GUI задачу
статус GUI
```

## Safety model

V12 still routes all external actions through:

```text
gui_agent
→ action_request
→ ActionFirewall
→ RiskEngine
→ PermissionManager
→ action_executor
→ action_result
→ verify screen
```

Voice/chat cannot bypass safety.

## Recommended config

```env
GUI_AUTOMATION_ENABLED=true
GUI_AUTOMATION_AUTO_ENABLED=false
GUI_AUTOMATION_VERIFY_AFTER_ACTION=true
GUI_AUTOMATION_SCREENSHOT_AUDIT=true
GUI_AUTOMATION_SEMANTIC_CLICK_THRESHOLD=35
GUI_AUTOMATION_MAX_RETRIES_PER_STEP=2
```

Keep `GUI_AUTOMATION_AUTO_ENABLED=false` until guided mode is tested on the target machine.
