"""V11 Proactive Companion module.

Turns important runtime/system/task events into helpful, interrupt-aware
notifications. It is intentionally conservative: it has cooldowns, importance
thresholds and a quiet-hours option so the assistant does not spam the user.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from core.module_base import CognitiveModule
from core.event_bus import CognitiveEvent, Priority


class ProactiveAssistantModule(CognitiveModule):
    MODULE_ID = "proactive_assistant"
    MODULE_DESCRIPTION = "V11 proactive companion: alerts, summaries and helpful suggestions"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(self.MODULE_ID, cost={"cpu": 0.03, "gpu": 0.0, "ram": 0.02})
        self.enabled = True
        self._last_notify_by_kind: Dict[str, float] = {}
        self._events: List[Dict[str, Any]] = []
        self._last_daily_summary = 0.0
        self._state_path: Path | None = None
        self._started_at = time.time()

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "proactive", None)
        self.enabled = bool(getattr(cfg, "enabled", True)) if cfg else True
        data_dir = Path(getattr(kernel.config, "persistence_dir", "~/.jarvis_brain")).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = data_dir / "proactive_v11_state.json"
        self._load_state()
        if self._last_daily_summary <= 0:
            self._last_daily_summary = time.time()
        kernel.event_bus.register_consumer(self.module_id, [
            "system_alert",
            "system_snapshot",
            "runtime_health",
            "task_chain_error",
            "task_chain_completed",
            "code_repair_error",
            "code_repair_proposal",
            "gui_task_error",
            "web_learning_error",
            "action_error",
            "tts_error",
            "screen_error",
            "model_router_status",
            "proactive_status_requested",
            "daily_summary_requested",
            "kernel_started",
        ])

    async def tick(self, dt: float) -> None:
        if not self.enabled or self.kernel is None:
            return
        cfg = getattr(self.kernel.config, "proactive", None)
        if not bool(getattr(cfg, "daily_summary_enabled", True)):
            return
        interval = float(getattr(cfg, "daily_summary_interval_seconds", 86400.0))
        now = time.time()
        if now - self._last_daily_summary >= interval:
            self._last_daily_summary = now
            self._emit_daily_summary(auto=True)
            self._save_state()

    async def on_event(self, event: CognitiveEvent) -> None:
        if not self.enabled:
            return
        if event.type == "kernel_started":
            self._remember("kernel_started", "info", "JAV started", "Kernel started and proactive companion is online.", event)
            return
        if event.type == "proactive_status_requested":
            self._respond_status()
            return
        if event.type == "daily_summary_requested":
            self._emit_daily_summary(auto=False)
            return
        if event.type == "system_alert":
            sev = str(event.data.get("severity", "info"))
            title = str(event.data.get("title", "System alert"))
            detail = str(event.data.get("detail", ""))
            self._maybe_notify(kind=str(event.data.get("kind", "system_alert")), severity=sev, title=title, detail=detail, event=event)
            return
        if event.type.endswith("_error") or event.type in {"action_error", "tts_error", "screen_error", "web_learning_error", "code_repair_error", "task_chain_error", "gui_task_error"}:
            self._maybe_notify(kind=event.type, severity="warning", title=f"{event.type.replace('_', ' ')}", detail=self._short(event.data), event=event)
            return
        if event.type in {"task_chain_completed", "code_repair_proposal"}:
            if bool(getattr(self._cfg(), "notify_task_progress", True)):
                self._maybe_notify(kind=event.type, severity="info", title=event.type.replace("_", " ").title(), detail=self._short(event.data), event=event)
            return
        if event.type == "runtime_health":
            # RuntimeMonitor already has checks; only notify if unhealthy.
            if event.data.get("ok") is False:
                failures = [c for c in event.data.get("checks", []) if not c.get("ok")]
                detail = "; ".join(f"{c.get('name')}: {c.get('detail')}" for c in failures[:5])
                self._maybe_notify("runtime_unhealthy", "warning", "Runtime health issue", detail, event)
            return

    def _cfg(self) -> Any:
        return getattr(getattr(self, "kernel", None).config, "proactive", None) if self.kernel else None

    def _importance(self, severity: str, title: str, detail: str) -> float:
        base = {"critical": 0.95, "warning": 0.7, "info": 0.45}.get(severity, 0.4)
        text = f"{title} {detail}".lower()
        if any(w in text for w in ["disk", "crash", "failed", "error", "temperature", "memory", "ram", "cpu"]):
            base += 0.1
        return min(1.0, base)

    def _maybe_notify(self, kind: str, severity: str, title: str, detail: str, event: CognitiveEvent) -> None:
        if self.kernel is None:
            return
        cfg = self._cfg()
        threshold = float(getattr(cfg, "min_importance", 0.55)) if cfg else 0.55
        cooldown = float(getattr(cfg, "cooldown_seconds", 300.0)) if cfg else 300.0
        importance = self._importance(severity, title, detail)
        self._remember(kind, severity, title, detail, event, importance=importance)
        if importance < threshold:
            return
        if bool(getattr(cfg, "do_not_disturb", False)):
            return
        now = time.time()
        # Avoid stealing the first CLI/Desktop response during startup checks.
        # The signal is still remembered and visible via /proactive or /system.
        startup_grace = float(getattr(cfg, "startup_grace_seconds", 15.0) or 0.0)
        if now - self._started_at < startup_grace and severity != "critical":
            return
        if now - self._last_notify_by_kind.get(kind, 0.0) < cooldown:
            return
        self._last_notify_by_kind[kind] = now
        text = self._compose_message(severity, title, detail)
        payload = {
            "kind": kind,
            "severity": severity,
            "importance": round(importance, 2),
            "title": title,
            "detail": detail,
            "text": text,
            "timestamp": now,
            "suggested_action": self._suggest_action(kind, title, detail),
        }
        self.kernel.event_bus.emit(CognitiveEvent(type="proactive_notification", data=payload, source_module=self.module_id), Priority.COGNITIVE)
        if bool(getattr(cfg, "speak_notifications", False)):
            self.kernel.event_bus.emit(CognitiveEvent(type="response_generated", data={"text": text, "source": self.module_id, "proactive": True}, source_module=self.module_id), Priority.COGNITIVE)
        elif bool(getattr(cfg, "chat_notifications", True)):
            # In chat/desktop this becomes visible; in service mode it is still logged by event stream.
            self.kernel.event_bus.emit(CognitiveEvent(type="response_generated", data={"text": text, "source": self.module_id, "proactive": True}, source_module=self.module_id), Priority.COGNITIVE)
        self._save_state()

    def _compose_message(self, severity: str, title: str, detail: str) -> str:
        prefix = "Важливо" if severity == "critical" else "Помітив проблему" if severity == "warning" else "Звернув увагу"
        suggestion = self._suggest_action("", title, detail)
        msg = f"{prefix}: {title}. {detail}".strip()
        if suggestion:
            msg += f"\nМожу допомогти: {suggestion}"
        return msg

    def _suggest_action(self, kind: str, title: str, detail: str) -> str:
        text = f"{kind} {title} {detail}".lower()
        if "ollama" in text or "model" in text:
            return "перевірити статус моделей або запустити Ollama. Напиши: 'покажи статус моделей'."
        if "disk" in text or "space" in text:
            return "показати стан пам’яті/диска і запропонувати очищення логів."
        if "internet" in text or "network" in text:
            return "перевірити мережу перед web learning."
        if "task" in text:
            return "показати статус задачі або продовжити іншим шляхом."
        if "repair" in text or "code" in text:
            return "запустити repair-agent або показати proposal."
        return "запусти /system або /diagnose-system для деталей."

    def _remember(self, kind: str, severity: str, title: str, detail: str, event: CognitiveEvent, importance: float | None = None) -> None:
        item = {
            "kind": kind,
            "severity": severity,
            "title": title,
            "detail": detail,
            "importance": importance if importance is not None else self._importance(severity, title, detail),
            "timestamp": time.time(),
            "source_event": event.type,
            "source_module": event.source_module,
        }
        self._events.append(item)
        self._events = self._events[-300:]

    def _respond_status(self) -> None:
        if self.kernel is None:
            return
        recent = self._events[-8:]
        lines = ["Proactive companion V11:", f"- enabled: {self.enabled}", f"- tracked events: {len(self._events)}", f"- notification kinds on cooldown: {len(self._last_notify_by_kind)}"]
        if recent:
            lines.append("Recent proactive signals:")
            for e in reversed(recent):
                lines.append(f"- [{e.get('severity')}] {e.get('title')}: {e.get('detail')}")
        else:
            lines.append("Recent proactive signals: none")
        self.kernel.event_bus.emit(CognitiveEvent(type="response_generated", data={"text": "\n".join(lines), "source": self.module_id}, source_module=self.module_id), Priority.COGNITIVE)

    def _emit_daily_summary(self, auto: bool) -> None:
        if self.kernel is None:
            return
        now = time.time()
        since = now - 86400.0
        events = [e for e in self._events if float(e.get("timestamp", 0)) >= since]
        warnings = [e for e in events if e.get("severity") in {"warning", "critical"}]
        lines = ["Daily companion summary:" if auto else "Companion summary:", f"- signals in last 24h: {len(events)}", f"- warnings/critical: {len(warnings)}"]
        if warnings:
            lines.append("Top issues:")
            for e in warnings[-8:]:
                lines.append(f"- {e.get('title')}: {e.get('detail')}")
        else:
            lines.append("No major issues tracked.")
        lines.append("Next: say 'перевір систему' or 'покажи proactive status' for details.")
        self.kernel.event_bus.emit(CognitiveEvent(type="proactive_daily_summary", data={"text": "\n".join(lines), "auto": auto}, source_module=self.module_id), Priority.COGNITIVE)
        if not auto or bool(getattr(self._cfg(), "chat_notifications", True)):
            self.kernel.event_bus.emit(CognitiveEvent(type="response_generated", data={"text": "\n".join(lines), "source": self.module_id}, source_module=self.module_id), Priority.COGNITIVE)

    def _short(self, data: Any) -> str:
        try:
            s = json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            s = str(data)
        return s[:700] + ("..." if len(s) > 700 else "")

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._events = list(data.get("events") or [])[-300:]
            self._last_notify_by_kind = {str(k): float(v) for k, v in (data.get("last_notify_by_kind") or {}).items()}
            self._last_daily_summary = float(data.get("last_daily_summary") or 0.0)
        except Exception:
            pass

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            self._state_path.write_text(json.dumps({"events": self._events[-300:], "last_notify_by_kind": self._last_notify_by_kind, "last_daily_summary": self._last_daily_summary}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def shutdown(self) -> None:
        self._save_state()

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"enabled": self.enabled, "tracked_events": len(self._events), "recent": self._events[-5:]})
        return d


def create_module() -> CognitiveModule:
    return ProactiveAssistantModule()
