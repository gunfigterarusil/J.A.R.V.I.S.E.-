# V9.6 — Real Vision + GUI Understanding MVP

This release upgrades the V3 OCR screen reader into a richer perception layer.
It is still **understanding-only**: JAV analyzes what is on screen and suggests
next steps, but it does not click, type, or control the GUI automatically.

## New capabilities

- captures the screen via `mss`;
- reads text with Tesseract/pytesseract;
- detects active window title when `pygetwindow` works on the OS/session;
- extracts approximate UI/text elements from OCR boxes;
- classifies elements as:
  - `error_text`
  - `button_or_action`
  - `input_or_label`
  - `menu_or_tab`
  - `text_block`
- emits richer events:
  - `screen_parsed`
  - `screen_understood`
  - `sensory_input`
- suggests safe next steps without clicking automatically.

## Commands

```text
/vision
/gui
/understand-screen
/analyze-screen
```

Existing commands still work:

```text
/see
/screen
/read-screen
/explain-screen
```

## Natural language examples

```text
проаналізуй екран
розбери інтерфейс
що натиснути?
куди натиснути?
analyze screen
understand gui
what should I click?
```

## Settings

```env
SCREEN_VISION_ENABLED=true
SCREEN_GUI_UNDERSTANDING_ENABLED=true
SCREEN_ACTIVE_WINDOW_ENABLED=true
SCREEN_MAX_UI_ELEMENTS=40
SCREEN_MIN_UI_CONFIDENCE=35
```

## Dependencies

Python:

```bash
pip install mss Pillow pytesseract pygetwindow
```

Ubuntu OCR packages:

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ukr
```

Windows:

- install Tesseract OCR;
- set `TESSERACT_CMD` in Settings Center if it is not in PATH.

## Safety boundary

V9.6 is intentionally not a GUI automation system. It can say:

> I see a button called Apply. You probably need to review changes and press Apply.

It should not silently perform clicks. Future GUI automation should be a separate
safety-gated V9.7/V10 feature using action requests, approval, and rollback.
