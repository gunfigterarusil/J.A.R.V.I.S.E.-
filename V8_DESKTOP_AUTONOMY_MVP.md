# V8 Desktop + Conversational Actions MVP

This version adds a native desktop interface and a natural-language bridge to V7 safe actions.

## Start desktop mode

```bash
python main.py --desktop
```

This opens a Tkinter desktop window, not a browser. It includes:

- chat panel;
- event stream;
- screen reading button;
- sleep/consolidation button;
- action status button;
- safety level buttons;
- fast command presets.

## Build into an application

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
python scripts/build_desktop_app.py
```

Output will appear in:

```text
dist/JAV/
```

On Windows you can also use:

```bat
run_desktop.bat
```

On Linux/macOS:

```bash
./run_desktop.sh
```

## Natural conversational actions

The new `action_intent` module can convert simple natural phrases into safe V7 actions:

```text
покажи файли .
прочитай файл README.md
знайди error в .
створи папку notes
запиши в notes/test.txt :: hello
запусти python --version
```

All actions still pass through:

```text
action_request -> safety firewall -> sandbox -> permission manager -> action executor
```

So conversation and voice do not bypass safety.

## Can it fix errors by voice?

Partially, in MVP form.

It can already understand repair intent and guide the safe workflow. It can read files, search for errors, run allowlisted commands, and write patches in the sandbox when safety allows it.

Full autonomous repair needs the next step: a Code Repair Agent that performs this loop:

```text
understand task
-> inspect files
-> run tests/checks
-> identify failing file
-> propose patch
-> wait for approval if risky
-> write patch
-> run verification
-> summarize result
```

This MVP intentionally does not give the LLM unlimited control over your PC.
