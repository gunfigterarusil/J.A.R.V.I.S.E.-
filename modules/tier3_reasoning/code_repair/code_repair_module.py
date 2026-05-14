"""V8.1 Code Repair Agent MVP.

This is the first real bridge from conversational requests like
"виправ помилки в ." to a safe diagnostic workflow. It does not silently edit
random files. It diagnoses Python projects inside ACTION_WORKSPACE_PATH,
reports likely files/lines, and then the user can ask for specific reads/writes
through the V7 safety layer.
"""
from __future__ import annotations

import asyncio
import compileall
import io
import re
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Any, Dict, List

from core import CognitiveModule, CognitiveEvent as Event, Priority


class CodeRepairModule(CognitiveModule):
    MODULE_DESCRIPTION = "V8.1 conversational code repair diagnostics"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(module_id="code_repair", cost={"cpu": 0.20, "gpu": 0.0, "ram": 0.06})
        self.enabled = True
        self.workspace = Path("~/jarvis_workspace").expanduser().resolve()
        self.last_diagnostic: Dict[str, Any] = {}

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "actions", None)
        self.workspace = Path(getattr(cfg, "workspace_path", "~/jarvis_workspace") or "~/jarvis_workspace").expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        ncfg = getattr(kernel.config, "natural_actions", None)
        self.enabled = bool(getattr(ncfg, "repair_agent_enabled", True))
        kernel.event_bus.register_consumer(self.module_id, ["code_repair_requested"])

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        if event.type == "code_repair_requested":
            await self._diagnose(event)

    async def _diagnose(self, event: Event) -> None:
        raw_path = str(event.data.get("path") or ".").strip()
        target = self._resolve(raw_path)
        if not self._inside_workspace(target):
            self._respond(f"Repair denied: path is outside workspace: {target}")
            return
        self._respond(f"Starting repair diagnostics for `{self._display(target)}`. I will inspect safely first; file edits still require V7 safety approval.")
        result = await asyncio.to_thread(self._run_python_diagnostics, target)
        self.last_diagnostic = result
        self._emit("code_repair_diagnostic", result)
        self._respond(self._format_result(result))

    def _run_python_diagnostics(self, target: Path) -> Dict[str, Any]:
        py_files: List[Path] = []
        if target.is_file() and target.suffix == ".py":
            py_files = [target]
        elif target.is_dir():
            ignore = {".venv", "venv", "__pycache__", ".git", "dist", "build"}
            for p in target.rglob("*.py"):
                if any(part in ignore for part in p.parts):
                    continue
                py_files.append(p)
        if not py_files:
            return {"ok": True, "path": str(target), "python_files": 0, "issues": [], "summary": "No Python files found."}

        issues: List[Dict[str, Any]] = []
        for p in py_files[:250]:
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    ok = compileall.compile_file(str(p), quiet=1, force=True)
                if not ok:
                    text = (stdout.getvalue() + "\n" + stderr.getvalue()).strip()
                    issues.append({"path": self._display(p), "type": "compile_failed", "details": text[-2000:]})
            except Exception as exc:
                issues.append({"path": self._display(p), "type": type(exc).__name__, "details": str(exc)})

        # Lightweight text scan for common runtime problem markers.
        markers = ["todo fix", "fixme", "traceback", "modulenotfounderror", "importerror", "syntaxerror", "exception"]
        marker_hits: List[Dict[str, str]] = []
        for p in py_files[:250]:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            low = txt.lower()
            for marker in markers:
                idx = low.find(marker)
                if idx >= 0:
                    line = txt[:idx].count("\n") + 1
                    snippet = txt[max(0, idx - 90): idx + 220].replace("\n", " ")
                    marker_hits.append({"path": self._display(p), "marker": marker, "line": str(line), "snippet": snippet})
                    break
            if len(marker_hits) >= 20:
                break

        return {
            "ok": len(issues) == 0,
            "path": str(target),
            "python_files": len(py_files),
            "issues": issues,
            "marker_hits": marker_hits,
            "timestamp": time.time(),
        }

    def _format_result(self, result: Dict[str, Any]) -> str:
        files = result.get("python_files", 0)
        issues = result.get("issues") or []
        hits = result.get("marker_hits") or []
        if not issues and not hits:
            return f"Repair diagnostics completed: checked {files} Python file(s), no compile errors or obvious error markers found."
        lines = [f"Repair diagnostics completed: checked {files} Python file(s)."]
        if issues:
            lines.append("Compile issues:")
            for item in issues[:8]:
                lines.append(f"- {item.get('path')}: {item.get('type')} {str(item.get('details',''))[:500]}")
        if hits:
            lines.append("Possible runtime/error markers:")
            for item in hits[:8]:
                lines.append(f"- {item.get('path')}:{item.get('line')} marker={item.get('marker')} — {item.get('snippet')[:220]}")
        lines.append("Next step: say `прочитай файл <path>` for the problematic file, then ask me to prepare or write a patch. Writes still go through safety L4.")
        return "\n".join(lines)

    def _resolve(self, raw: str) -> Path:
        p = Path(raw or ".").expanduser()
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()

    def _inside_workspace(self, p: Path) -> bool:
        try:
            p.resolve().relative_to(self.workspace)
            return True
        except Exception:
            return p.resolve() == self.workspace

    def _display(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.workspace)) or "."
        except Exception:
            return str(p)

    def _respond(self, text: str) -> None:
        self._emit("response_generated", {"text": text, "source": "code_repair/v8.1"})

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if not self.kernel:
            return
        self.kernel.event_bus.emit(Event(type=event_type, data=data, source_module=self.module_id), Priority.COGNITIVE)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({"enabled": self.enabled, "workspace": str(self.workspace), "last_diagnostic": self.last_diagnostic})
        return base


def create_module() -> CodeRepairModule:
    return CodeRepairModule()
