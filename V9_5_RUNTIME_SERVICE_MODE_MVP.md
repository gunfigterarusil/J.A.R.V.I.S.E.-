# V9.5 Runtime / Service Mode / Watchdog MVP

This upgrade turns JAV from a development script into a more service-friendly local assistant.

## New launch modes

```bash
python main.py --service
```

Runs the same headless cognitive kernel, but with service-oriented logging, signal handling, PID/heartbeat files and runtime health snapshots.

```bash
python scripts/watchdog.py
```

Starts `main.py --service`, watches `runtime_heartbeat.json`, and restarts JAV if the process exits or the heartbeat becomes stale.

Convenience launchers:

```bash
./run_service.sh
./run_watchdog.sh
run_service.bat
run_watchdog.bat
```

## Runtime files

By default, files live in the configured brain data directory:

```text
data/brain/runtime_heartbeat.json
data/brain/runtime_health.json
data/brain/runtime.pid
data/brain/logs/jav_service.log
```

In non-portable mode, the default brain directory is `~/.jarvis_brain`.

## Chat/Desktop commands

```text
/runtime
/runtime-status
/health
/service-status
/self-test
/runtime-self-test
/health-check
```

Natural language also works:

```text
покажи runtime status
перевір стан програми
запусти runtime self-test
```

## Linux systemd user service

Create the service file:

```bash
python scripts/install_systemd_service.py
```

Then enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now jav-watchdog.service
systemctl --user status jav-watchdog.service
```

## Windows startup

Run on Windows:

```bash
python scripts/create_windows_startup_shortcut.py
```

It creates a startup `.bat` launcher for the watchdog.

## What this is and is not

V9.5 improves stability for 24/7 use, but it is still not a magical infinite process. Real long-running reliability still depends on:

- stable Python environment;
- enough disk space;
- stable LLM backend;
- regular backups;
- careful safety settings;
- occasional updates/restarts.

The watchdog/service layer makes crashes and hangs recoverable instead of silent.
