"""V7 Action Executor — safe PC/file automation inside a sandbox.

This module is intentionally conservative. It only executes actions after the
core ActionFirewall emits action_approved. Risky actions can become pending and
must be approved once through a v7_user_approval event.
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import shlex
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("actions.v7")


class PendingAction:
    def __init__(self, pending_id: str, action_type: str, data: Dict[str, Any], reason: str = "", risk_score: float = 0.0) -> None:
        self.pending_id = pending_id
        self.action_type = action_type
        self.data = data
        self.created_at = time.time()
        self.reason = reason
        self.risk_score = risk_score


class ActionExecutorModule(CognitiveModule):
    """Executes approved V7 actions: files, commands and V9.7 safe GUI actions."""

    MODULE_DESCRIPTION = "V7/V12 sandboxed file, command and safe GUI action executor with screenshot audit"
    MODULE_VERSION = "12.0.0"

    def __init__(self) -> None:
        super().__init__(module_id="action_executor", cost={"cpu": 0.10, "gpu": 0.0, "ram": 0.05})
        self.workspace = Path("~/jarvis_workspace").expanduser().resolve()
        self.allow_shell = False
        self.command_timeout = 20.0
        self.max_read_chars = 12000
        self.max_list_entries = 120
        self.allowed_commands: set[str] = {
            "python", "python3", "py", "pytest", "pip", "pip3", "git"
        }
        self._pending: Dict[str, PendingAction] = {}
        self._last_result: Dict[str, Any] = {}
        self.actions_enabled = True
        self.gui_screenshot_audit = True
        self.gui_pause_after_action = 0.35

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "actions", None)
        self.actions_enabled = bool(getattr(cfg, "enabled", True))
        gui_cfg = getattr(kernel.config, "gui_automation", None)
        self.gui_screenshot_audit = bool(getattr(gui_cfg, "screenshot_audit", True))
        self.gui_pause_after_action = float(getattr(gui_cfg, "step_delay_seconds", 1.0) or 1.0) / 3.0
        self.workspace = Path(getattr(cfg, "workspace_path", "~/jarvis_workspace") or "~/jarvis_workspace").expanduser().resolve()
        self.allow_shell = bool(getattr(cfg, "allow_shell", False))
        self.command_timeout = float(getattr(cfg, "command_timeout", 20.0))
        self.max_read_chars = int(getattr(cfg, "max_read_chars", 12000))
        self.max_list_entries = int(getattr(cfg, "max_list_entries", 120))
        extra = getattr(cfg, "allowed_commands", []) or []
        self.allowed_commands.update(str(x).strip() for x in extra if str(x).strip())
        self.workspace.mkdir(parents=True, exist_ok=True)
        # Make sure the kernel sandbox also knows about the configured workspace.
        try:
            kernel.sandbox.add_allowed_path(str(self.workspace))
        except Exception:
            pass
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "action_approved",
                "action_denied",
                "action_pending_confirmation",
                "v7_user_approval",
                "v7_user_deny",
                "action_status_requested",
            ],
        )
        logger.info("[V7] Action executor ready. Workspace: %s, enabled=%s", self.workspace, self.actions_enabled)

    async def on_event(self, event: Event) -> None:
        if not self.actions_enabled and event.type != "action_status_requested":
            return
        if event.type == "action_approved":
            await self._execute(event.data)
        elif event.type == "action_denied":
            await self._emit_response(
                f"Action denied: {event.data.get('deny_reason', 'no reason provided')}",
                event.data,
                event_type="action_denied_notice",
            )
        elif event.type == "action_pending_confirmation":
            await self._register_pending(event)
        elif event.type == "v7_user_approval":
            await self._approve_pending(str(event.data.get("pending_id", "")).strip())
        elif event.type == "v7_user_deny":
            await self._deny_pending(str(event.data.get("pending_id", "")).strip())
        elif event.type == "action_status_requested":
            await self._status(respond=bool(event.data.get("respond", True)))

    async def _register_pending(self, event: Event) -> None:
        raw_id = event.data.get("_original_event_id") or event.causal_parent_id or int(time.time())
        pending_id = f"p{raw_id}"
        action_type = str(event.data.get("action_type", "unknown"))
        pending = PendingAction(
            pending_id=pending_id,
            action_type=action_type,
            data=dict(event.data),
            reason=str(event.data.get("pending_reason", "confirmation required")),
            risk_score=float(event.data.get("risk_score", 0.0) or 0.0),
        )
        self._pending[pending_id] = pending
        msg = (
            f"Action pending confirmation: {action_type} ({pending_id}). "
            f"Reason: {pending.reason} To approve once: /approve {pending_id}. To deny: /deny {pending_id}."
        )
        await self._emit_response(msg, {"pending_id": pending_id, "action_type": action_type}, event_type="action_pending_registered")

    async def _approve_pending(self, pending_id: str) -> None:
        pending = self._pending.pop(pending_id, None)
        if pending is None:
            await self._emit_response(f"No pending action found for id: {pending_id}", {"pending_id": pending_id})
            return
        data = dict(pending.data)
        data["_approved_once"] = True
        data["_approved_pending_id"] = pending_id
        # Remove pending metadata that should not confuse executors.
        data.pop("pending_reason", None)
        data.pop("risk_category", None)
        data.pop("risk_reasons", None)
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="action_request", data=data, source_module=self.module_id), Priority.REALTIME)
        await self._emit_response(f"Approved once: {pending.action_type} ({pending_id}). Executing through firewall...", {"pending_id": pending_id})

    async def _deny_pending(self, pending_id: str) -> None:
        pending = self._pending.pop(pending_id, None)
        if pending is None:
            await self._emit_response(f"No pending action found for id: {pending_id}", {"pending_id": pending_id})
            return
        await self._emit_response(f"Denied pending action: {pending.action_type} ({pending_id}).", {"pending_id": pending_id})

    async def _execute(self, data: Dict[str, Any]) -> None:
        action_type = str(data.get("action_type", ""))
        payload = data.get("payload", {}) if isinstance(data.get("payload", {}), dict) else {}
        respond = bool(data.get("respond", payload.get("respond", True)))
        request_id = str(data.get("request_id", payload.get("request_id", "")) or "")
        try:
            if action_type == "list_files":
                result = await asyncio.to_thread(self._list_files, payload)
            elif action_type == "read_file":
                result = await asyncio.to_thread(self._read_file, payload)
            elif action_type == "search_files":
                result = await asyncio.to_thread(self._search_files, payload)
            elif action_type == "write_file":
                result = await asyncio.to_thread(self._write_file, payload)
            elif action_type == "create_dir":
                result = await asyncio.to_thread(self._create_dir, payload)
            elif action_type == "run_command":
                result = await asyncio.to_thread(self._run_command, payload)
            elif action_type == "open_url":
                result = await asyncio.to_thread(self._open_url, payload)
            elif action_type == "open_app":
                result = await asyncio.to_thread(self._open_app, payload)
            elif action_type == "gui_click":
                result = await asyncio.to_thread(self._gui_click, payload)
            elif action_type == "gui_type_text":
                result = await asyncio.to_thread(self._gui_type_text, payload)
            elif action_type == "gui_press":
                result = await asyncio.to_thread(self._gui_press, payload)
            elif action_type == "gui_hotkey":
                result = await asyncio.to_thread(self._gui_hotkey, payload)
            elif action_type == "gui_scroll":
                result = await asyncio.to_thread(self._gui_scroll, payload)
            elif action_type == "gui_wait":
                result = await asyncio.to_thread(self._gui_wait, payload)
            else:
                result = {"ok": False, "error": f"Unsupported V7 action: {action_type}"}
        except Exception as exc:
            logger.exception("[V7] Action failed: %s", action_type)
            result = {"ok": False, "error": str(exc)}

        result.update({"action_type": action_type, "request_id": request_id})
        self._last_result = result
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="action_result", data=result, source_module=self.module_id), Priority.COGNITIVE)
        if respond:
            await self._emit_response(self._format_result(result), result)

    # ------------------------------------------------------------------
    # Concrete actions
    # ------------------------------------------------------------------
    def _list_files(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve_user_path(payload.get("path") or ".")
        self._check_read(path)
        recursive = bool(payload.get("recursive", False))
        max_entries = int(payload.get("max_entries", self.max_list_entries))
        if not path.exists():
            return {"ok": False, "error": f"Path does not exist: {path}"}
        iterator = path.rglob("*") if recursive and path.is_dir() else path.iterdir() if path.is_dir() else [path]
        items = []
        for p in iterator:
            try:
                rel = self._display_path(p)
                items.append({"path": rel, "type": "dir" if p.is_dir() else "file", "size": p.stat().st_size if p.is_file() else None})
            except Exception:
                continue
            if len(items) >= max_entries:
                break
        return {"ok": True, "path": str(path), "count": len(items), "items": items}

    def _read_file(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve_user_path(payload.get("path") or "")
        self._check_read(path)
        max_chars = int(payload.get("max_chars", self.max_read_chars))
        if not path.is_file():
            return {"ok": False, "error": f"Not a file: {path}"}
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        truncated = len(text) > max_chars
        return {"ok": True, "path": str(path), "chars": min(len(text), max_chars), "truncated": truncated, "content": text[:max_chars]}

    def _search_files(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        base = self._resolve_user_path(payload.get("path") or ".")
        self._check_read(base)
        query = str(payload.get("query", "")).lower().strip()
        pattern = str(payload.get("pattern", "*")) or "*"
        max_results = int(payload.get("max_results", 50))
        if not query:
            return {"ok": False, "error": "search_files requires query"}
        results = []
        for p in base.rglob("*") if base.is_dir() else [base]:
            if len(results) >= max_results:
                break
            if not p.is_file() or not fnmatch.fnmatch(p.name, pattern):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            idx = text.lower().find(query)
            if idx >= 0:
                start = max(0, idx - 120)
                end = min(len(text), idx + len(query) + 180)
                results.append({"path": self._display_path(p), "snippet": text[start:end].replace("\n", " ")})
        return {"ok": True, "query": query, "count": len(results), "results": results}

    def _write_file(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve_user_path(payload.get("path") or "")
        self._check_write(path)
        content = str(payload.get("content", ""))
        append = bool(payload.get("append", False))
        create_dirs = bool(payload.get("create_dirs", True))
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": str(path), "bytes": len(content.encode("utf-8")), "append": append}

    def _create_dir(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve_user_path(payload.get("path") or "")
        self._check_write(path)
        path.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(path)}

    def _run_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.allow_shell:
            return {"ok": False, "error": "Shell actions are disabled. Set ACTION_ALLOW_SHELL=true and safety level L5 to enable."}
        command = payload.get("command", [])
        cwd = self._resolve_user_path(payload.get("cwd") or ".")
        self._check_execute(cwd)
        args = shlex.split(command) if isinstance(command, str) else [str(x) for x in command]
        if not args:
            return {"ok": False, "error": "Empty command"}
        exe = Path(args[0]).name
        if exe not in self.allowed_commands:
            return {"ok": False, "error": f"Command '{exe}' is not in ACTION_ALLOWED_COMMANDS"}
        joined = " ".join(args).lower()
        blocked = ["rm -rf", "del /", "format ", "shutdown", "reboot", "curl |", "wget |", "sudo "]
        if any(x in joined for x in blocked):
            return {"ok": False, "error": "Command blocked by V7 local safety filter"}
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=self.command_timeout,
            shell=False,
        )
        return {
            "ok": proc.returncode == 0,
            "cwd": str(cwd),
            "command": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-6000:],
            "stderr": proc.stderr[-6000:],
        }


    # ------------------------------------------------------------------
    # V12 GUI actions
    # ------------------------------------------------------------------
    def _open_url(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = str(payload.get("url", "")).strip()
        if not url:
            return {"ok": False, "error": "open_url requires url"}
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "error": "Only http/https URLs are allowed for open_url"}
        before = self._gui_screenshot("before_open_url", payload)
        opened = webbrowser.open(url)
        time.sleep(max(0.1, self.gui_pause_after_action))
        after = self._gui_screenshot("after_open_url", payload)
        return {"ok": bool(opened), "url": url, "before_screenshot": before, "after_screenshot": after}

    def _open_app(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        app = str(payload.get("app", "")).strip()
        if not app:
            return {"ok": False, "error": "open_app requires app"}
        blocked = {"cmd", "powershell", "terminal", "sudo", "regedit", "format", "shutdown"}
        if Path(app).name.lower() in blocked:
            return {"ok": False, "error": f"Blocked sensitive app launch: {app}"}
        before = self._gui_screenshot("before_open_app", payload)
        try:
            if sys.platform.startswith("win") and hasattr(os, "startfile"):
                os.startfile(app)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(shlex.split(app), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            return {"ok": False, "error": f"Application not found: {app}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        time.sleep(max(0.2, self.gui_pause_after_action))
        after = self._gui_screenshot("after_open_app", payload)
        return {"ok": True, "app": app, "before_screenshot": before, "after_screenshot": after}

    def _gui_click(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pg = self._import_pyautogui()
        x = int(float(payload.get("x", 0)))
        y = int(float(payload.get("y", 0)))
        if x <= 0 or y <= 0:
            return {"ok": False, "error": "gui_click requires positive x/y coordinates"}
        before = self._gui_screenshot("before_click", payload)
        pg.click(x=x, y=y)
        time.sleep(max(0.1, self.gui_pause_after_action))
        after = self._gui_screenshot("after_click", payload)
        return {"ok": True, "x": x, "y": y, "matched_text": payload.get("matched_text", ""), "before_screenshot": before, "after_screenshot": after}

    def _gui_type_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = str(payload.get("text", ""))
        if not text:
            return {"ok": False, "error": "gui_type_text requires text"}
        if self._looks_sensitive(text):
            return {"ok": False, "error": "Blocked typing text that looks like a password/token/secret"}
        pg = self._import_pyautogui()
        before = self._gui_screenshot("before_type", payload)
        pg.write(text, interval=0.01)
        time.sleep(max(0.1, self.gui_pause_after_action))
        after = self._gui_screenshot("after_type", payload)
        return {"ok": True, "chars": len(text), "before_screenshot": before, "after_screenshot": after}

    def _gui_press(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        key = str(payload.get("key", "")).strip().lower()
        if not key:
            return {"ok": False, "error": "gui_press requires key"}
        blocked = {"delete", "del", "f4"}
        if key in blocked:
            return {"ok": False, "error": f"Blocked risky key press: {key}"}
        pg = self._import_pyautogui()
        before = self._gui_screenshot("before_press", payload)
        pg.press(key)
        time.sleep(max(0.1, self.gui_pause_after_action))
        after = self._gui_screenshot("after_press", payload)
        return {"ok": True, "key": key, "before_screenshot": before, "after_screenshot": after}

    def _gui_hotkey(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        keys = payload.get("keys", [])
        if isinstance(keys, str):
            keys = [x.strip().lower() for x in keys.split("+") if x.strip()]
        keys = [str(k).strip().lower() for k in keys if str(k).strip()]
        if not keys:
            return {"ok": False, "error": "gui_hotkey requires keys"}
        joined = "+".join(keys)
        blocked = ["alt+f4", "ctrl+w", "ctrl+q", "ctrl+alt+delete", "shift+delete"]
        if joined in blocked:
            return {"ok": False, "error": f"Blocked risky hotkey: {joined}"}
        pg = self._import_pyautogui()
        before = self._gui_screenshot("before_hotkey", payload)
        pg.hotkey(*keys)
        time.sleep(max(0.1, self.gui_pause_after_action))
        after = self._gui_screenshot("after_hotkey", payload)
        return {"ok": True, "keys": keys, "before_screenshot": before, "after_screenshot": after}

    def _gui_scroll(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        amount = int(float(payload.get("amount", -5)))
        pg = self._import_pyautogui()
        before = self._gui_screenshot("before_scroll", payload)
        pg.scroll(amount)
        time.sleep(max(0.1, self.gui_pause_after_action))
        after = self._gui_screenshot("after_scroll", payload)
        return {"ok": True, "amount": amount, "before_screenshot": before, "after_screenshot": after}

    def _gui_wait(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        seconds = min(10.0, max(0.1, float(payload.get("seconds", 1.0))))
        time.sleep(seconds)
        after = self._gui_screenshot("after_wait", payload)
        return {"ok": True, "seconds": seconds, "after_screenshot": after}

    def _import_pyautogui(self):
        try:
            import pyautogui  # type: ignore
            pyautogui.FAILSAFE = True
            return pyautogui
        except Exception as exc:
            raise RuntimeError("Missing GUI automation dependency. Install: pip install pyautogui. On Linux also ensure a graphical session is available.") from exc

    def _gui_screenshot(self, label: str, payload: Dict[str, Any]) -> str:
        if not self.gui_screenshot_audit:
            return ""
        try:
            pg = self._import_pyautogui()
            base = ""
            if self.kernel is not None:
                base = str(getattr(getattr(self.kernel, "persistence", None), "_base", "") or "")
            out_dir = Path(base).expanduser() / "screenshots" / "gui_actions" if base else Path.home() / ".jarvis_brain" / "screenshots" / "gui_actions"
            out_dir.mkdir(parents=True, exist_ok=True)
            request_id = str(payload.get("request_id", "gui"))[:80].replace(os.sep, "_")
            path = out_dir / f"{request_id}_{label}_{int(time.time() * 1000)}.png"
            img = pg.screenshot()
            img.save(path)
            return str(path)
        except Exception:
            return ""

    def _looks_sensitive(self, text: str) -> bool:
        low = text.lower()
        if any(x in low for x in ["password", "пароль", "api_key", "api key", "token", "secret", "credit card", "cvv"]):
            return True
        # Generic long high-entropy token-ish string.
        compact = "".join(ch for ch in text if not ch.isspace())
        return len(compact) > 32 and any(c.isdigit() for c in compact) and any(c.isalpha() for c in compact)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_user_path(self, raw: Any) -> Path:
        s = str(raw or ".").strip()
        if not s or s == ".":
            return self.workspace
        p = Path(s).expanduser()
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.workspace))
        except Exception:
            return str(path)

    def _check_read(self, path: Path) -> None:
        if not self.kernel:
            return
        ok, reason = self.kernel.sandbox.check_read(str(path))
        if not ok:
            raise PermissionError(reason)

    def _check_write(self, path: Path) -> None:
        if not self.kernel:
            return
        ok, reason = self.kernel.sandbox.check_write(str(path))
        if not ok:
            raise PermissionError(reason)

    def _check_execute(self, path: Path) -> None:
        if not self.kernel:
            return
        ok, reason = self.kernel.sandbox.check_execute(str(path))
        if not ok:
            raise PermissionError(reason)

    def _format_result(self, result: Dict[str, Any]) -> str:
        action = result.get("action_type", "action")
        if not result.get("ok"):
            return f"{action} failed: {result.get('error', 'unknown error')}"
        if action == "list_files":
            items = result.get("items", [])
            lines = [f"{x.get('type')}: {x.get('path')}" for x in items[:40]]
            more = "" if len(items) <= 40 else f"\n...and {len(items) - 40} more"
            return f"Listed {result.get('count', 0)} item(s):\n" + "\n".join(lines) + more
        if action == "read_file":
            suffix = "\n...[truncated]" if result.get("truncated") else ""
            return f"Read {result.get('path')}:\n{result.get('content', '')}{suffix}"
        if action == "search_files":
            rows = [f"- {r.get('path')}: {r.get('snippet')}" for r in result.get("results", [])[:20]]
            return f"Found {result.get('count', 0)} match(es) for '{result.get('query')}':\n" + "\n".join(rows)
        if action == "run_command":
            return (
                f"Command finished with code {result.get('returncode')}.\n"
                f"STDOUT:\n{result.get('stdout','')}\nSTDERR:\n{result.get('stderr','')}"
            ).strip()
        if action in {"open_url", "open_app", "gui_click", "gui_type_text", "gui_press", "gui_hotkey", "gui_scroll", "gui_wait"}:
            return f"GUI action completed: {action} — {json.dumps(result, ensure_ascii=False)[:900]}"
        return f"{action} completed: {json.dumps(result, ensure_ascii=False)[:1200]}"

    async def _emit_response(self, text: str, data: Optional[Dict[str, Any]] = None, event_type: str = "response_generated") -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(type=event_type, data={"text": text, **(data or {})}, source_module=self.module_id),
                Priority.COGNITIVE,
            )
            if event_type != "response_generated":
                self.kernel.event_bus.emit(
                    Event(type="response_generated", data={"text": text, **(data or {})}, source_module=self.module_id),
                    Priority.COGNITIVE,
                )

    async def _status(self, respond: bool = True) -> None:
        data = self.to_dict()
        if respond:
            await self._emit_response(
                "V7 action executor status:\n"
                f"- workspace: {data['workspace']}\n"
                f"- shell enabled: {data['allow_shell']}\n"
                f"- pending actions: {len(data['pending_actions'])}\n"
                f"- allowed commands: {', '.join(data['allowed_commands'])}",
                data,
            )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "actions_enabled": self.actions_enabled,
                "workspace": str(self.workspace),
                "allow_shell": self.allow_shell,
                "allowed_commands": sorted(self.allowed_commands),
                "pending_actions": [
                    {
                        "pending_id": p.pending_id,
                        "action_type": p.action_type,
                        "age_sec": round(time.time() - p.created_at, 1),
                        "risk_score": p.risk_score,
                        "reason": p.reason,
                    }
                    for p in self._pending.values()
                ],
                "last_result": self._last_result,
            }
        )
        return base


def create_module() -> ActionExecutorModule:
    return ActionExecutorModule()
