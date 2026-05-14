# V3 Screen Reading MVP

V3 gives Jarvis its first practical “eyes”: request-driven screenshot capture, OCR, and lightweight screen parsing.

## What works

```text
/see or /read-screen
  → screen_capture_requested
  → screenshot via mss
  → OCR via pytesseract + Tesseract
  → simple ScreenParser
  → screen_parsed
  → response_generated
```

Voice mode can also trigger screen reading with phrases such as:

```text
what is on screen
read the screen
що на екрані
прочитай екран
що тут не так
```

## Files changed

```text
modules/tier2_perception/screen/screen_parser_module.py
interfaces/voice/voice_loop.py
main.py
config.py
.env.example
requirements.txt
README.md
```

## Install

Python dependencies:

```bash
pip install -r requirements.txt
```

Ubuntu system OCR dependencies:

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ukr
```

Windows users need to install Tesseract OCR and set `TESSERACT_CMD` in `.env` if it is not in PATH.

## Test

```bash
python main.py --chat
```

Then type:

```text
/see
```

## Environment settings

```env
SCREEN_READING_ENABLED=true
SCREEN_AUTO_WATCH_ENABLED=false
SCREENSHOT_DIR=
SCREEN_OCR_BACKEND=tesseract
SCREEN_OCR_LANGUAGE=eng
SCREEN_OCR_CONFIG=--psm 6
SCREEN_SAVE_SCREENSHOTS=true
SCREEN_MAX_OCR_CHARS=7000
TESSERACT_CMD=
```

For Ukrainian + English OCR after installing language packs:

```env
SCREEN_OCR_LANGUAGE=eng+ukr
```

## Notes

V3 is deliberately request-driven. It does not constantly watch the screen. Continuous monitoring should be added later only with clear privacy controls and safety limits.

Screenshots are saved to:

```text
~/.jarvis_brain/screenshots/
```

unless `SCREENSHOT_DIR` is configured.

## Next recommended stage

V4 should improve inner monologue and emotions, but a useful mini-polish before V4 is to make `/see` optionally pass the parsed screen text into the LLM for deeper explanation, especially for code errors and terminal logs.
