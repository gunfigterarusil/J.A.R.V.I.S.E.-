# V9.7 — Safe General GUI Automation MVP

V9.7 adds a general desktop/browser/app automation loop. It is not hardcoded for YouTube or any single website. You give a goal, JAV observes the screen, asks the LLM/heuristics for one safe next GUI action, routes that action through V7 safety, executes it, and observes again.

## Flow

```text
voice/chat/desktop goal
→ gui_task_requested
→ screen_understand_requested
→ screen_understood
→ gui_agent chooses one action
→ action_request
→ ActionFirewall / RiskEngine / PermissionManager
→ action_executor performs open_url/open_app/click/type/press/hotkey/scroll/wait
→ action_result
→ next observation or wait for user
```

## Commands

```text
/gui-task <goal>
/gui-auto <goal>
/gui-step [task_id]
/gui-status [task_id]
/gui-cancel [task_id]
```

## Natural examples

```text
знайди музику на YouTube
відкрий браузер і знайди документацію Python
натисни Continue
введи в поле пошуку lofi music
продовжуй GUI задачу
статус GUI
```

## Safety

- GUI actions still go through V7 `action_request` and safety gates.
- `gui_click` and `gui_type_text` are risk-scored and may require confirmation.
- Passwords, API keys, tokens, payment data and purchase-like flows are blocked.
- `GUI_AUTOMATION_AUTO_ENABLED=false` by default. Guided mode is safer.

## Settings

```env
GUI_AUTOMATION_ENABLED=true
GUI_AUTOMATION_AUTO_ENABLED=false
GUI_AUTOMATION_MAX_STEPS=12
GUI_AUTOMATION_STEP_DELAY_SECONDS=1.0
GUI_AUTOMATION_REQUIRE_CONFIRMATION=true
GUI_AUTOMATION_BLOCK_SENSITIVE=true
GUI_AUTOMATION_ALLOWED_ACTIONS=observe,done,open_url,open_app,click_xy,click_text,type_text,press,hotkey,scroll,wait
```

## Dependencies

```bash
pip install pyautogui
```

Screen observation still needs V9.6 dependencies: `mss`, `Pillow`, `pytesseract`, `pygetwindow`, and Tesseract OCR.
