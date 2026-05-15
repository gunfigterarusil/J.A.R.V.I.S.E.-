"""V11 System Monitor module.

Monitors the local machine, storage paths, model/router availability and runtime
health. Emits structured snapshots and alerts that the proactive companion can
turn into useful, non-spammy messages.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.module_base import CognitiveModule
from core.event_bus import CognitiveEvent, Priority

try:  # optional but recommended
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore


class SystemMonitorModule(CognitiveModule):
    MODULE_ID = "system_monitor"
    MODULE_DESCRIPTION = "V11 system/resource/model monitor for proactive companionship"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(self.MODULE_ID, cost={"cpu": 0.03, "gpu": 0.0, "ram": 0.02})
        self._last_snapshot_at = 0.0
        self._last_alert_at: Dict[str, float] = {}
        self._last_snapshot: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(self.module_id, [
            "system_status_requested",
            "system_monitor_snapshot_requested",
            "system_diagnose_requested",
            "kernel_started",
        ])
        self._emit_snapshot(reason="startup", respond=False)

    async def tick(self, dt: float) -> None:
        if self.kernel is None:
            return
        cfg = getattr(self.kernel.config, "system_monitor", None)
        if cfg is not None and not bool(getattr(cfg, "enabled", True)):
            return
        interval = float(getattr(cfg, "interval_seconds", 20.0)) if cfg else 20.0
        now = time.time()
        if now - self._last_snapshot_at >= interval:
            self._emit_snapshot(reason="periodic", respond=False)
            self._last_snapshot_at = now

    async def on_event(self, event: CognitiveEvent) -> None:
        if event.type == "kernel_started":
            self._emit_snapshot(reason="kernel_started", respond=False)
            return
        if event.type in {"system_status_requested", "system_monitor_snapshot_requested"}:
            self._emit_snapshot(reason="manual", respond=bool(event.data.get("respond", True)))
            return
        if event.type == "system_diagnose_requested":
            self._emit_snapshot(reason="diagnose", respond=True, diagnose=True)
            return

    def _cfg(self) -> Any:
        return getattr(getattr(self, "kernel", None).config, "system_monitor", None) if self.kernel else None

    def _disk_usage(self, path: Path) -> Dict[str, Any]:
        try:
            path.mkdir(parents=True, exist_ok=True) if not path.exists() else None
            usage = shutil.disk_usage(str(path))
            total_gb = usage.total / (1024 ** 3) if usage.total else 0.0
            used_gb = usage.used / (1024 ** 3) if usage.total else 0.0
            free_gb = usage.free / (1024 ** 3) if usage.total else 0.0
            # Some virtual/sandbox filesystems report absurd capacities. Do not
            # show scary/incorrect alerts based on them.
            if total_gb <= 0 or total_gb > 10_000_000:
                return {
                    "path": str(path),
                    "exists": path.exists(),
                    "unknown": True,
                    "total_gb": "unknown",
                    "used_gb": "unknown",
                    "free_gb": "unknown",
                    "used_percent": None,
                    "detail": "filesystem reported unrealistic capacity",
                }
            used_pct = (usage.used / usage.total * 100.0) if usage.total else 0.0
            return {
                "path": str(path),
                "exists": path.exists(),
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "used_percent": round(used_pct, 1),
            }
        except Exception as exc:
            return {"path": str(path), "exists": path.exists(), "error": str(exc)}

    def _internet_ok(self, timeout: float) -> Dict[str, Any]:
        host = "1.1.1.1"
        try:
            socket.create_connection((host, 53), timeout=timeout).close()
            return {"ok": True, "probe": host}
        except Exception as exc:
            return {"ok": False, "probe": host, "error": str(exc)[:160]}

    def _url_ok(self, url: str, timeout: float) -> Dict[str, Any]:
        if not url:
            return {"ok": False, "url": url, "error": "no url configured"}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JAV-SystemMonitor/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - configured health check URL
                return {"ok": 200 <= int(resp.status) < 500, "url": url, "status": int(resp.status)}
        except Exception as exc:
            return {"ok": False, "url": url, "error": str(exc)[:220]}

    def _model_status(self) -> Dict[str, Any]:
        router = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if router is None or not hasattr(router, "status"):
            return {"available": False, "error": "model router unavailable"}
        try:
            status = router.status(refresh=False)
            roles = status.get("roles") or {}
            unavailable = [r for r, info in roles.items() if not (info or {}).get("available", False)]
            return {
                "profile": status.get("profile"),
                "available_providers": status.get("available") or [],
                "role_count": len(roles),
                "unavailable_roles": unavailable,
                "roles": {k: {"provider": (v or {}).get("provider"), "available": (v or {}).get("available", False)} for k, v in roles.items()},
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)[:220]}

    def _collect(self, reason: str) -> Dict[str, Any]:
        cfg = self._cfg()
        data_dir = Path(getattr(getattr(self.kernel, "config", None), "persistence_dir", "~/.jarvis_brain")).expanduser() if self.kernel else Path("~/.jarvis_brain").expanduser()
        workspace = Path(getattr(getattr(getattr(self.kernel, "config", None), "actions", None), "workspace_path", "~/jarvis_workspace")).expanduser() if self.kernel else Path("~/jarvis_workspace").expanduser()
        snap: Dict[str, Any] = {
            "version": "V11",
            "reason": reason,
            "timestamp": time.time(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "pid": os.getpid(),
            "data_dir": str(data_dir),
            "workspace": str(workspace),
            "psutil_available": bool(psutil),
        }
        if psutil:
            try:
                snap["cpu_percent"] = float(psutil.cpu_percent(interval=None))
                vm = psutil.virtual_memory()
                snap["memory"] = {"total_gb": round(vm.total / (1024 ** 3), 2), "used_percent": round(float(vm.percent), 1), "available_gb": round(vm.available / (1024 ** 3), 2)}
                try:
                    temps = psutil.sensors_temperatures(fahrenheit=False) or {}
                    flat_temps = []
                    for name, entries in temps.items():
                        for e in entries[:3]:
                            cur = getattr(e, "current", None)
                            if cur is not None:
                                flat_temps.append({"sensor": name, "label": getattr(e, "label", ""), "current_c": round(float(cur), 1)})
                    snap["temperatures"] = flat_temps[:10]
                except Exception:
                    snap["temperatures"] = []
            except Exception as exc:
                snap["psutil_error"] = str(exc)[:220]
        else:
            snap["cpu_percent"] = None
            snap["memory"] = {"used_percent": None}
            snap["temperatures"] = []

        snap["data_disk"] = self._disk_usage(data_dir)
        snap["workspace_disk"] = self._disk_usage(workspace)
        portable_root = data_dir.parents[1] if len(data_dir.parents) > 1 and "data" in str(data_dir) else data_dir
        snap["portable_root_disk"] = self._disk_usage(portable_root)
        timeout = float(getattr(cfg, "network_timeout_seconds", 3.0)) if cfg else 3.0
        if bool(getattr(cfg, "check_network", True)) if cfg else True:
            snap["internet"] = self._internet_ok(timeout)
        else:
            snap["internet"] = {"ok": None, "disabled": True}
        if bool(getattr(cfg, "check_ollama", True)) if cfg else True:
            ollama_host = getattr(getattr(self.kernel.config, "llm", None), "ollama_host", "http://localhost:11434") if self.kernel else "http://localhost:11434"
            snap["ollama"] = self._url_ok(str(ollama_host).rstrip("/") + "/api/tags", timeout)
        else:
            snap["ollama"] = {"ok": None, "disabled": True}
        if bool(getattr(cfg, "check_models", True)) if cfg else True:
            snap["models"] = self._model_status()
        else:
            snap["models"] = {"disabled": True}
        snap["alerts"] = self._alerts_from_snapshot(snap)
        snap["ok"] = not any(a.get("severity") in {"critical", "warning"} for a in snap["alerts"])
        return snap

    def _alerts_from_snapshot(self, snap: Dict[str, Any]) -> List[Dict[str, Any]]:
        cfg = self._cfg()
        cpu_warn = float(getattr(cfg, "cpu_warn_percent", 90.0)) if cfg else 90.0
        mem_warn = float(getattr(cfg, "memory_warn_percent", 88.0)) if cfg else 88.0
        disk_warn = float(getattr(cfg, "disk_warn_percent", 90.0)) if cfg else 90.0
        temp_warn = float(getattr(cfg, "temp_warn_c", 85.0)) if cfg else 85.0
        alerts: List[Dict[str, Any]] = []
        cpu = snap.get("cpu_percent")
        if isinstance(cpu, (int, float)) and cpu >= cpu_warn:
            alerts.append({"kind": "cpu_high", "severity": "warning", "title": "High CPU usage", "detail": f"CPU is {cpu:.1f}%"})
        mem = (snap.get("memory") or {}).get("used_percent")
        if isinstance(mem, (int, float)) and mem >= mem_warn:
            alerts.append({"kind": "memory_high", "severity": "warning", "title": "High memory usage", "detail": f"RAM is {mem:.1f}% used"})
        for key in ["data_disk", "workspace_disk", "portable_root_disk"]:
            used = (snap.get(key) or {}).get("used_percent")
            if isinstance(used, (int, float)) and used >= disk_warn:
                alerts.append({"kind": f"{key}_full", "severity": "critical" if used >= 97 else "warning", "title": "Disk space is low", "detail": f"{key} is {used:.1f}% used"})
        for t in snap.get("temperatures") or []:
            cur = t.get("current_c")
            if isinstance(cur, (int, float)) and cur >= temp_warn:
                alerts.append({"kind": "temperature_high", "severity": "warning", "title": "High temperature", "detail": f"{t.get('sensor')} {t.get('label')} is {cur:.1f}°C"})
        if (snap.get("internet") or {}).get("ok") is False:
            alerts.append({"kind": "internet_down", "severity": "warning", "title": "Internet check failed", "detail": (snap.get("internet") or {}).get("error", "network unavailable")})
        if (snap.get("ollama") or {}).get("ok") is False:
            alerts.append({"kind": "ollama_down", "severity": "info", "title": "Ollama is not responding", "detail": (snap.get("ollama") or {}).get("error", "Ollama API unavailable")})
        models = snap.get("models") or {}
        unavailable = models.get("unavailable_roles") or []
        if unavailable:
            alerts.append({"kind": "models_unavailable", "severity": "info", "title": "Some model roles are unavailable", "detail": ", ".join(map(str, unavailable[:8]))})
        return alerts

    def _emit_snapshot(self, reason: str, respond: bool, diagnose: bool = False) -> None:
        if self.kernel is None:
            return
        snap = self._collect(reason)
        self._last_snapshot = snap
        self._history.append(snap)
        self._history = self._history[-120:]
        self.kernel.event_bus.emit(CognitiveEvent(type="system_snapshot", data=snap, source_module=self.module_id), Priority.BACKGROUND)
        self._emit_alerts(snap)
        if respond or diagnose:
            self.kernel.event_bus.emit(
                CognitiveEvent(type="response_generated", data={"text": self._format_snapshot(snap, diagnose=diagnose), "source": self.module_id}, source_module=self.module_id),
                Priority.COGNITIVE,
            )

    def _emit_alerts(self, snap: Dict[str, Any]) -> None:
        if self.kernel is None:
            return
        cfg = self._cfg()
        cooldown = float(getattr(cfg, "alert_cooldown_seconds", 300.0)) if cfg else 300.0
        now = time.time()
        for alert in snap.get("alerts") or []:
            key = str(alert.get("kind", "alert"))
            last = self._last_alert_at.get(key, 0.0)
            if now - last < cooldown:
                continue
            self._last_alert_at[key] = now
            data = dict(alert)
            data.update({"snapshot_timestamp": snap.get("timestamp"), "data_dir": snap.get("data_dir"), "workspace": snap.get("workspace")})
            self.kernel.event_bus.emit(CognitiveEvent(type="system_alert", data=data, source_module=self.module_id), Priority.COGNITIVE)

    def _format_snapshot(self, snap: Dict[str, Any], diagnose: bool = False) -> str:
        lines = ["System monitor V11:" if not diagnose else "System diagnosis V11:"]
        lines.append(f"- ok: {snap.get('ok')}")
        cpu = snap.get("cpu_percent")
        lines.append(f"- CPU: {cpu if cpu is not None else 'n/a'}%")
        mem = snap.get("memory") or {}
        lines.append(f"- RAM: {mem.get('used_percent', 'n/a')}% used, available {mem.get('available_gb', 'n/a')} GB")
        for key, label in [("data_disk", "memory disk"), ("workspace_disk", "workspace disk"), ("portable_root_disk", "portable/root disk")]:
            d = snap.get(key) or {}
            if "error" in d:
                lines.append(f"- {label}: error {d.get('error')}")
            elif d.get("unknown"):
                lines.append(f"- {label}: unknown ({d.get('detail', 'unsupported filesystem')})")
            else:
                lines.append(f"- {label}: {d.get('used_percent', 'n/a')}% used, free {d.get('free_gb', 'n/a')} GB")
        lines.append(f"- Internet: {(snap.get('internet') or {}).get('ok')}")
        lines.append(f"- Ollama: {(snap.get('ollama') or {}).get('ok')}")
        models = snap.get("models") or {}
        if models:
            lines.append(f"- Model profile: {models.get('profile', 'n/a')}; unavailable roles: {', '.join(models.get('unavailable_roles') or []) or 'none'}")
        alerts = snap.get("alerts") or []
        if alerts:
            lines.append("Alerts:")
            for a in alerts[:8]:
                lines.append(f"  - [{a.get('severity')}] {a.get('title')}: {a.get('detail')}")
        else:
            lines.append("Alerts: none")
        if diagnose:
            lines.append("Suggested next steps:")
            if (snap.get("ollama") or {}).get("ok") is False:
                lines.append("- Start/check Ollama if you rely on local models: ollama serve")
            if (snap.get("internet") or {}).get("ok") is False:
                lines.append("- Check network/VPN/DNS before web learning tasks.")
            if any("disk" in str(a.get("kind")) for a in alerts):
                lines.append("- Free disk space or move JARVIS_DATA_DIR/workspace to a larger drive.")
            if not alerts:
                lines.append("- No obvious system issue detected.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"last_snapshot": self._last_snapshot, "history_count": len(self._history)})
        return d


def create_module() -> CognitiveModule:
    return SystemMonitorModule()
