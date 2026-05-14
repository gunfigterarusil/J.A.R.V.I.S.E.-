# V7 Safe PC Automation MVP

V7 adds the first safe “hands” for Jarvis. It can work with files and limited commands, but only through the existing safety layer.

## What is implemented

- `action_executor` tier4 module
- workspace sandbox: `~/jarvis_workspace` by default
- action firewall integration
- action audit flow through `action_request -> action_approved/action_denied/action_pending_confirmation -> action_result`
- CLI commands in `python main.py --chat`
- one-time approval flow for pending risky actions

## Supported actions

| Action | Chat command | Default permission |
|---|---|---|
| list files | `/ls [path]` | L1 |
| read file | `/read <path>` | L1 |
| search files | `/search <query> [:: path]` | L1 |
| create directory | `/mkdir <path>` | L4 |
| write file | `/write <path> :: <content>` | L4 |
| append file | `/append <path> :: <content>` | L4 |
| run safe command | `/run <command>` | L5 + confirmation |
| action status | `/actions` | L0 |
| set safety level | `/safety 0..6` | user command |
| approve pending action | `/approve <pending_id>` | user command |
| deny pending action | `/deny <pending_id>` | user command |

## Safety levels

The system still starts conservatively. By default, `safety_default_level` is L1, so read-only workspace actions are available. File writing requires L4. Commands require L5 and still go through confirmation.

Recommended dev flow:

```bash
python main.py --chat
```

Then:

```text
/actions
/ls
/read notes.txt
/safety 4
/write notes.txt :: Hello from Jarvis V7
/read notes.txt
```

For shell commands, set this in `.env` first:

```env
ACTION_ALLOW_SHELL=true
```

Then in chat:

```text
/safety 5
/run python --version
/approve p123
```

The pending id is printed by Jarvis when an action needs confirmation.

## Hard limits

V7 does **not** give Jarvis unrestricted control of the PC.

- no write outside workspace unless added to sandbox config
- no write to core safety/kernel directories
- shell is disabled by default
- shell uses `shell=False`
- commands are allowlisted
- destructive command patterns are blocked
- high-risk actions require explicit approval

## Environment settings

```env
ACTIONS_V7_ENABLED=true
ACTION_WORKSPACE_PATH=~/jarvis_workspace
ACTION_ALLOW_SHELL=false
ACTION_COMMAND_TIMEOUT=20
ACTION_ALLOWED_COMMANDS=python,python3,py,pytest,pip,pip3,git
ACTION_MAX_READ_CHARS=12000
ACTION_MAX_LIST_ENTRIES=120
```

## Roadmap after V7 MVP

Next improvements:

- richer dashboard action panel
- file diff/patch workflow
- project scan action
- test runner action with result parsing
- temporary rather than persistent permissions
- V8 remote/server body interface
