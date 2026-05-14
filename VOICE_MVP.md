# Voice MVP: faster-whisper + Piper TTS with pyttsx3 fallback

This build adds a separate voice mode:

```bash
python main.py --voice
```

Flow:

```text
microphone -> faster-whisper STT -> user_utterance event -> V1 memory retrieval -> LLM dialogue -> response_generated -> TTS
```

TTS backend order by default:

```text
Piper -> pyttsx3 fallback -> log error without crashing
```

## Install Python dependencies

```bash
pip install -r requirements.txt
```

On Linux you may also need audio packages:

```bash
sudo apt update
sudo apt install -y portaudio19-dev python3-pyaudio alsa-utils espeak-ng
```

`pyttsx3` usually needs an OS speech engine. On Linux, `espeak-ng` is the simplest fallback engine.

## TTS modes

Use this variable in `.env`:

```env
VOICE_TTS_BACKEND=auto
```

Available values:

```text
auto     = try Piper first, then pyttsx3
piper    = only Piper
pyttsx3  = only pyttsx3
none     = disable voice output
```

## Install Piper

Install the Piper CLI for your OS and make sure the `piper` command works, or set:

```bash
PIPER_EXECUTABLE=/path/to/piper
```

Download a Piper `.onnx` voice model and set:

```bash
PIPER_MODEL_PATH=/path/to/voice.onnx
```

Optional config:

```bash
PIPER_CONFIG_PATH=/path/to/voice.onnx.json
```

## pyttsx3 fallback

If Piper is not installed or `PIPER_MODEL_PATH` is empty, `VOICE_TTS_BACKEND=auto` will try pyttsx3 automatically.

Optional settings:

```env
PYTTSX3_VOICE_ID=
PYTTSX3_RATE=175
PYTTSX3_VOLUME=1.0
```

To force pyttsx3 without Piper:

```env
VOICE_TTS_BACKEND=pyttsx3
```

## Recommended `.env` for CPU-only server/laptop

```env
VOICE_STT_MODEL=small
VOICE_STT_DEVICE=cpu
VOICE_STT_COMPUTE_TYPE=int8
VOICE_STT_LANGUAGE=
VOICE_RECORD_SECONDS=5
VOICE_ENERGY_THRESHOLD=0.005
VOICE_WAKE_WORD=
VOICE_RESPONSE_TIMEOUT=90
VOICE_TTS_WAIT_TIMEOUT=45
VOICE_LISTEN_AFTER_RESPONSE_DELAY=0.35
VOICE_TTS_ENABLED=true
VOICE_TTS_BACKEND=auto

PIPER_EXECUTABLE=piper
PIPER_MODEL_PATH=/absolute/path/to/voice.onnx

PYTTSX3_VOICE_ID=
PYTTSX3_RATE=175
PYTTSX3_VOLUME=1.0
```


## V1/V2 integration behavior

`python main.py --voice` now uses the same V1 dialogue path as `python main.py --chat`. The voice loop:

1. records one microphone chunk;
2. transcribes it with faster-whisper;
3. emits `user_utterance` with `input_mode=voice`;
4. waits for `response_generated`;
5. waits for `tts_spoken` or `tts_error`;
6. only then listens again.

This reduces the classic bug where the microphone hears Jarvis speaking and starts replying to itself.

Timing settings:

```env
VOICE_RESPONSE_TIMEOUT=90
VOICE_TTS_WAIT_TIMEOUT=45
VOICE_LISTEN_AFTER_RESPONSE_DELAY=0.35
```

## Notes

- Without `--voice`, TTS stays disabled and the project behaves like the previous clean MVP.
- If Piper is missing in `auto` mode, the brain still starts and pyttsx3 is tried automatically.
- If both Piper and pyttsx3 are unavailable, the project logs a clear TTS error and keeps running.
- If `sounddevice` or `faster-whisper` is missing, voice mode stops with installation instructions.
- The old fake audio module is still present, but the real voice interface is `interfaces/voice/voice_loop.py`.
