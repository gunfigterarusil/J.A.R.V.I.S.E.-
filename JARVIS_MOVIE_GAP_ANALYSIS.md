# Gap Analysis — JAV vs. movie JARVIS

This is a practical comparison, not a claim that JAV is conscious or equal to
fictional JARVIS.

## Already moving toward JARVIS

- Voice conversation: STT + TTS with Piper/pyttsx3 fallback.
- Memory: dialogue context, sleep/consolidation, world/self model.
- Screen reading: OCR + ScreenParser.
- Desktop UI: native program mode, no browser required.
- Safe actions: sandboxed file actions and allowlisted commands.
- Natural action control: voice/chat phrases can trigger the same actions as slash commands.
- Internal state: emotion, monologue, self/world model.

## Still different from movie JARVIS

### 1. Perception is limited

Movie JARVIS has rich multimodal perception: cameras, sensors, location,
objects, faces, audio scene analysis, hardware telemetry. JAV currently has
microphone STT and OCR screen reading, not full visual understanding.

Needed next:

- computer vision beyond OCR;
- active window/app detection;
- structured UI element detection;
- audio scene/event recognition;
- hardware/system telemetry.

### 2. Automation is intentionally constrained

Movie JARVIS can operate machines, suits, doors, devices and networks. JAV only
has sandboxed PC/file actions and restricted commands.

Needed next:

- explicit device/plugin API;
- per-device permission model;
- reliable undo/rollback;
- action simulation before execution;
- multi-step task executor.

### 3. Code repair is still diagnostic-first

JAV can start repair diagnostics from natural language, but it does not yet do
full autonomous patching across a project with tests and rollback.

Needed next:

- Code Repair Agent V9;
- diff/patch generation;
- unit-test loop;
- rollback snapshots;
- user approval before writes;
- project-specific memory.

### 4. Long-term learning is basic

JAV has memory consolidation, but not real online model training or robust skill
learning.

Needed next:

- structured skill library;
- procedural memory;
- self-evaluation metrics;
- regression tests for learned behaviors;
- safe plugin development flow.

### 5. Reliability is not movie-grade

Movie JARVIS is always-on and near-instant. JAV still depends on local hardware,
models, dependencies and safety levels.

Needed next:

- background service mode;
- crash recovery;
- health monitor;
- model fallback manager;
- logs/telemetry dashboard;
- installer/updater.

### 6. No physical embodiment

Movie JARVIS can control physical systems. JAV has no Android/robot/server body
layer yet.

Needed next:

- server daemon mode;
- Android client;
- smart-home/device adapters;
- robotics API;
- strict physical-world safety rules.

## Recommended next milestone

V9 should be **Project Repair Agent**:

1. user says: "виправ помилки в цьому проєкті";
2. JAV scans workspace;
3. runs diagnostics/tests;
4. reads relevant files;
5. asks LLM for patch;
6. shows diff;
7. requests approval;
8. writes patch;
9. reruns checks;
10. summarizes result.

This is the biggest remaining step toward a useful JARVIS-like assistant for
real development work.
