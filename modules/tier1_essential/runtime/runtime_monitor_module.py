"""V9.5 Runtime monitor module.

Provides lightweight 24/7 runtime stability signals:
- heartbeat JSON file for an external watchdog
- periodic health snapshot
- runtime status/self-test events for chat/desktop
- graceful shutdown sleep/consolidation request

This module intentionally does not restart the process itself. Restarts are
handled by scripts/watchdog.py or by systemd/Windows Task Scheduler.
"""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List

from core.module_base import CognitiveModule
from core.event_bus import CognitiveEvent, Priority


class RuntimeMonitorModule(CognitiveModule):
    MODULE_ID = "runtime_monitor"
    MODULE_DESCRIPTION = "V9.5 runtime heartbeat, health checks and service-mode status"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(self.MODULE_ID, cost={"cpu": 0.01, "gpu": 0.0, "ram": 0.01})
        self.started_at = time.time()
        self._last_heartbeat = 0.0
        self._last_health = 0.0
        self._recent_errors: List[Dict[str, Any]] = []
        self._last_health_snapshot: Dict[str, Any] = {}
        self._heartbeat_path: Path | None = None
        self._health_path: Path | None = None
        self._pid_path: Path | None = None

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "runtime", None)
        data_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        if cfg is not None:
            self._heartbeat_path = Path(cfg.resolve_heartbeat_file(str(data_dir))).expanduser()
            self._pid_path = Path(cfg.resolve_pid_file(str(data_dir))).expanduser()
        else:
            self._heartbeat_path = data_dir / "runtime_heartbeat.json"
            self._pid_path = data_dir / "runtime.pid"
        self._health_path = data_dir / "runtime_health.json"
        for p in (self._heartbeat_path, self._health_path, self._pid_path):
            if p is not None:
                p.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self._pid_path is not None:
                self._pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass
        kernel.event_bus.register_consumer(self.module_id, [
            "runtime_status_requested",
            "runtime_self_test_requested",
            "screen_error",
            "tts_error",
            "action_denied",
            "action_error",
            "web_learning_error",
            "code_repair_error",
            "task_chain_error",
        ])
        self._write_heartbeat(reason="startup")
        self._write_health(reason="startup")

    async def tick(self, dt: float) -> None:
        if self.kernel is None:
            return
        cfg = getattr(self.kernel.config, "runtime", None)
        now = time.time()
        hb_interval = float(getattr(cfg, "heartbeat_interval_seconds", 10.0)) if cfg else 10.0
        health_interval = float(getattr(cfg, "health_check_interval_seconds", 30.0)) if cfg else 30.0
        if now - self._last_heartbeat >= hb_interval:
            self._write_heartbeat(reason="tick")
            self._last_heartbeat = now
        if now - self._last_health >= health_interval:
            snapshot = self._write_health(reason="periodic")
            self._last_health = now
            self.kernel.event_bus.emit(
                CognitiveEvent(type="runtime_health", data=snapshot, source_module=self.module_id),
                Priority.BACKGROUND,
            )

    async def on_event(self, event: CognitiveEvent) -> None:
        if event.type in {"screen_error", "tts_error", "action_denied", "action_error", "web_learning_error", "code_repair_error", "task_chain_error"}:
            self._remember_error(event)
            return
        if event.type == "runtime_status_requested":
            self._respond_status(event)
            return
        if event.type == "runtime_self_test_requested":
            self._respond_self_test(event)
            return

    def _remember_error(self, event: CognitiveEvent) -> None:
        self._recent_errors.append({
            "type": event.type,
            "source": event.source_module,
            "timestamp": event.timestamp,
            "data": self._safe_data(event.data),
        })
        self._recent_errors = self._recent_errors[-50:]

    def _safe_data(self, data: Any) -> Any:
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
            if len(text) > 1200:
                text = text[:1200] + "..."
            return json.loads(text)
        except Exception:
            return str(data)[:1200]

    def _base_snapshot(self, reason: str) -> Dict[str, Any]:
        kernel = self.kernel
        cfg = getattr(kernel.config, "runtime", None) if kernel else None
        data_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser() if kernel else Path("~/.jarvis_brain").expanduser()
        workspace = Path(getattr(getattr(kernel.config, "actions", None), "workspace_path", "~/jarvis_workspace")).expanduser() if kernel else Path("~/jarvis_workspace").expanduser()
        return {
            "version": "V9.5",
            "reason": reason,
            "timestamp": time.time(),
            "pid": os.getpid(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "service_mode": bool(getattr(cfg, "service_mode", False)) if cfg else False,
            "uptime_seconds": round(time.time() - self.started_at, 2),
            "kernel_running": bool(getattr(kernel, "running", False)) if kernel else False,
            "module_count": len(getattr(kernel, "modules", {}) or {}) if kernel else 0,
            "safety_level": int(getattr(getattr(kernel, "permission_manager", None), "current_level", 0)) if kernel else 0,
            "data_dir": str(data_dir),
            "data_dir_exists": data_dir.exists(),
            "workspace": str(workspace),
            "workspace_exists": workspace.exists(),
            "heartbeat_file": str(self._heartbeat_path) if self._heartbeat_path else "",
            "recent_error_count": len(self._recent_errors),
            "recent_errors": self._recent_errors[-8:],
        }

    def _write_heartbeat(self, reason: str) -> Dict[str, Any]:
        snapshot = self._base_snapshot(reason)
        snapshot["kind"] = "heartbeat"
        if self._heartbeat_path is not None:
            try:
                self._heartbeat_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        return snapshot

    def _write_health(self, reason: str) -> Dict[str, Any]:
        snapshot = self._base_snapshot(reason)
        snapshot["kind"] = "health"
        checks = []
        checks.append({"name": "kernel_running", "ok": bool(snapshot["kernel_running"]), "detail": str(snapshot["kernel_running"])})
        checks.append({"name": "modules_loaded", "ok": snapshot["module_count"] >= 10, "detail": str(snapshot["module_count"])})
        checks.append({"name": "data_dir", "ok": bool(snapshot["data_dir_exists"]), "detail": snapshot["data_dir"]})
        checks.append({"name": "workspace", "ok": bool(snapshot["workspace_exists"]), "detail": snapshot["workspace"]})
        checks.append({"name": "recent_errors", "ok": snapshot["recent_error_count"] < 10, "detail": str(snapshot["recent_error_count"])})
        snapshot["checks"] = checks
        snapshot["ok"] = all(c["ok"] for c in checks)
        self._last_health_snapshot = snapshot
        if self._health_path is not None:
            try:
                self._health_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        return snapshot

    def _respond_status(self, event: CognitiveEvent) -> None:
        if self.kernel is None:
            return
        snap = self._write_health(reason="manual_status")
        lines = [
            "Runtime status:",
            f"- ok: {snap.get('ok')}",
            f"- mode: {'service' if snap.get('service_mode') else 'interactive'}",
            f"- uptime: {snap.get('uptime_seconds')}s",
            f"- pid: {snap.get('pid')}",
            f"- modules: {snap.get('module_count')}",
            f"- data: {snap.get('data_dir')}",
            f"- workspace: {snap.get('workspace')}",
            f"- heartbeat: {snap.get('heartbeat_file')}",
            f"- recent errors: {snap.get('recent_error_count')}",
        ]
        for check in snap.get("checks", []):
            mark = "✅" if check.get("ok") else "⚠️"
            lines.append(f"  {mark} {check.get('name')}: {check.get('detail')}")
        self.kernel.event_bus.emit(
            CognitiveEvent(type="response_generated", data={"text": "\n".join(lines), "source": "runtime_monitor"}, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    def _respond_self_test(self, event: CognitiveEvent) -> None:
        if self.kernel is None:
            return
        snap = self._write_health(reason="self_test")
        failures = [c for c in snap.get("checks", []) if not c.get("ok")]
        if failures:
            text = "Runtime self-test found issues:\n" + "\n".join(f"- {c.get('name')}: {c.get('detail')}" for c in failures)
        else:
            text = "Runtime self-test passed. Kernel, modules, data path, workspace and recent error budget look OK."
        self.kernel.event_bus.emit(
            CognitiveEvent(type="response_generated", data={"text": text, "source": "runtime_monitor"}, source_module=self.module_id),
            Priority.COGNITIVE,
        )

    def shutdown(self) -> None:
        if self.kernel is not None:
            cfg = getattr(self.kernel.config, "runtime", None)
            if bool(getattr(cfg, "auto_sleep_on_shutdown", True)):
                try:
                    self.kernel.event_bus.emit(
                        CognitiveEvent(type="memory_consolidation_requested", data={"reason": "runtime_shutdown", "force": False, "respond": False}, source_module=self.module_id),
                        Priority.BACKGROUND,
                    )
                except Exception:
                    pass
        self._write_heartbeat(reason="shutdown")
        self._write_health(reason="shutdown")
        try:
            if self._pid_path is not None and self._pid_path.exists():
                self._pid_path.unlink()
        except Exception:
            pass

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "uptime_seconds": round(time.time() - self.started_at, 2),
            "heartbeat_file": str(self._heartbeat_path) if self._heartbeat_path else "",
            "health_file": str(self._health_path) if self._health_path else "",
            "recent_error_count": len(self._recent_errors),
        })
        return d


def create_module() -> CognitiveModule:
    return RuntimeMonitorModule()
