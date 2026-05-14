# V2 Voice + V1 Dialogue Stability Pass

Implemented after V1 dialogue MVP.

## Goal

Make voice mode use the same real dialogue pipeline as terminal chat instead of behaving like a separate audio demo.

## Runtime flow

```text
python main.py --voice
  -> microphone capture
  -> faster-whisper transcription
  -> user_utterance(input_mode=voice)
  -> memory_request(dialogue_context)
  -> LLMRouter.generate
  -> response_generated
  -> Piper or pyttsx3 TTS
  -> tts_spoken / tts_error
  -> microphone resumes listening
```

## Files changed

- `interfaces/voice/voice_loop.py`
  - waits for `response_generated` before listening again;
  - waits for `tts_spoken`/`tts_error` to reduce self-transcription;
  - prints the assistant response in voice mode;
  - emits `voice_status` events for dashboard/debugging.

- `modules/tier4_actions/tts/tts_module.py`
  - forwards `turn_id` into `tts_spoken`/`tts_error` events.

- `config.py` and `.env.example`
  - added timing controls:
    - `VOICE_RESPONSE_TIMEOUT`;
    - `VOICE_TTS_WAIT_TIMEOUT`;
    - `VOICE_LISTEN_AFTER_RESPONSE_DELAY`.

- `README.md` and `VOICE_MVP.md`
  - updated roadmap and voice instructions.

## Test commands

```bash
python -m compileall -q .
python main.py --help
printf 'привіт\n/exit\n' | timeout 12s python main.py --chat
python main.py --voice
```

`--voice` still requires local audio/STT dependencies at runtime. Without them it exits with a clear install message.
