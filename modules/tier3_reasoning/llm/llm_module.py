"""Tier 3 Reasoning: LLM Dialogue Module (V1)

V1 implements the real dialogue loop:
  user_utterance
    -> request relevant memory context
    -> assemble system prompt + recent dialogue + retrieved memory
    -> call LLMRouter
    -> emit thought_generated + response_generated
    -> persist turn history

The LLM remains a reasoning tool, not the whole brain. Identity, memory,
attention and safety still live in separate modules/the kernel.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("llm")


class LLMModule(CognitiveModule):
    """Tier 3: Dialogue coordinator backed by LLMRouter."""

    MODULE_DESCRIPTION = "V1 dialogue cortex — LLM response generation with retrieved memory context"
    MODULE_VERSION = "1.1.0"

    def __init__(self) -> None:
        super().__init__(
            module_id="llm",
            cost={"cpu": 0.40, "gpu": 0.20, "ram": 0.30},
        )
        self._pending_turns: Dict[str, Dict[str, Any]] = {}
        self._self_context: dict = {}
        self._wm_context: list = []
        self._current_mode: int = 1   # ThinkingMode.REACTIVE
        self._mode_selector = None
        self._history: Deque[Dict[str, Any]] = deque(maxlen=16)
        self._turn_counter = 0
        self._active_generation = 0
        self._last_response: str = ""
        self._affective_context: dict = {}
        self._style_hint: str = "calm-direct"
        self._monologue_context: dict = {}
        self._world_context: dict = {}
        self._self_reflection: str = ""
        self._consolidation_context: dict = {}

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        from core.thinking_modes import ThinkingModeSelector

        self._mode_selector = ThinkingModeSelector()
        self._load_history()
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "user_utterance",
                "memory_retrieved",
                "context_request",
                "sensory_input",
                "self_model_updated",
                "wm_updated",
                "emotional_state",
                "response_style_hint",
                "monologue_state",
                "internal_monologue",
                "world_context",
                "world_model_updated",
                "self_reflection",
                "capability_model_updated",
                "memory_consolidated",
                "sleep_cycle_completed",
                "dream_narrative",
                "consolidation_lesson",
            ],
        )

    async def on_event(self, event: Event) -> None:
        et = event.type
        if et == "user_utterance":
            await self._handle_user_utterance(event)
        elif et == "memory_retrieved":
            await self._handle_memory_retrieved(event)
        elif et == "context_request":
            self._emit_dialogue_state()
        elif et == "sensory_input":
            self._emit_thought("Noticing sensory change... adapting context.")
        elif et == "self_model_updated":
            self._self_context = event.data or {}
        elif et == "wm_updated":
            self._wm_context = event.data.get("snapshot", [])
        elif et == "emotional_state":
            self._affective_context = dict(event.data or {})
            self._style_hint = self._affective_context.get("response_style", self._style_hint)
        elif et == "response_style_hint":
            self._style_hint = str(event.data.get("style", self._style_hint))
            affect = event.data.get("affect")
            if isinstance(affect, dict):
                self._affective_context.update(affect)
        elif et == "monologue_state":
            self._monologue_context = dict(event.data or {})
        elif et == "internal_monologue":
            latest = event.data if isinstance(event.data, dict) else {"text": str(event.data)}
            self._monologue_context["latest"] = latest
        elif et in {"world_context", "world_model_updated"}:
            self._world_context = dict(event.data or {})
        elif et == "self_reflection":
            self._self_reflection = str((event.data or {}).get("text", ""))[:700]
        elif et == "capability_model_updated":
            if self._self_context is not None:
                self._self_context["capability_update"] = event.data or {}
        elif et in {"memory_consolidated", "sleep_cycle_completed"}:
            self._consolidation_context = dict(event.data or {})
        elif et == "dream_narrative":
            self._consolidation_context["latest_dream"] = dict(event.data or {})
        elif et == "consolidation_lesson":
            lessons = self._consolidation_context.setdefault("recent_lessons", [])
            if isinstance(lessons, list):
                lessons.append(dict(event.data or {}))
                self._consolidation_context["recent_lessons"] = lessons[-6:]

    async def _handle_user_utterance(self, event: Event) -> None:
        text = str(event.data.get("text", "") or "").strip()
        if not text:
            return

        self._turn_counter += 1
        turn_id = f"turn_{int(time.time())}_{self._turn_counter}"

        # Select thinking mode before requesting memory.
        mode_name = "REACTIVE"
        if self.kernel and self._mode_selector:
            from core.thinking_modes import ThinkingMode

            mode = self._mode_selector.select(event, self.kernel.core_state)
            mode_name = mode.name
            if mode.value != self._current_mode:
                self._current_mode = mode.value
                self.kernel.core_state.patch({"thinking_mode": mode.value})
                self.kernel.event_bus.emit(
                    Event(
                        type="thinking_mode_changed",
                        data={"mode": mode.name, "value": mode.value},
                        source_module=self.module_id,
                    ),
                    Priority.COGNITIVE,
                )

        self._pending_turns[turn_id] = {
            "turn_id": turn_id,
            "text": text,
            "raw": event.data,
            "mode_name": mode_name,
            "created_at": time.time(),
        }

        self._emit_thought(f"[{mode_name}] Heard user input. Retrieving relevant memory: {text[:80]}")

        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="memory_request",
                    data={
                        "query_type": "dialogue_context",
                        "query_text": text,
                        "top_k": 6,
                        "request_id": turn_id,
                    },
                    source_module=self.module_id,
                    causal_parent_id=event._id,
                ),
                Priority.COGNITIVE,
            )

    async def _handle_memory_retrieved(self, event: Event) -> None:
        request_id = event.data.get("request_id")
        if not request_id or request_id not in self._pending_turns:
            # Ignore unrelated memory responses from other modules.
            return
        turn = self._pending_turns.pop(request_id)
        await self._generate_response(turn, event.data)

    async def _generate_response(self, turn: Dict[str, Any], memory_data: Dict[str, Any]) -> None:
        if not self.kernel:
            return
        router = getattr(self.kernel, "llm_router", None)
        if router is None:
            self._emit_fallback(turn, memory_data)
            return

        from core.thinking_modes import ThinkingMode
        from core.llm_router import TaskType

        mode = ThinkingMode(self._current_mode)
        task_map = {
            ThinkingMode.REFLEX: TaskType.SIMPLE_CHAT,
            ThinkingMode.REACTIVE: TaskType.SIMPLE_CHAT,
            ThinkingMode.DELIBERATIVE: TaskType.COMPLEX_REASONING,
            ThinkingMode.IMAGINATION: TaskType.CREATIVE_IMAGINATION,
            ThinkingMode.DEEP_ANALYSIS: TaskType.COMPLEX_REASONING,
            ThinkingMode.BACKGROUND: TaskType.SUMMARIZATION,
        }
        task_type = task_map.get(mode, TaskType.SIMPLE_CHAT)

        user_text = turn["text"]
        # Ask V5 context modules for fresh snapshots. We also use the last cached snapshots immediately.
        self.kernel.event_bus.emit(
            Event(type="self_model_request", data={"reason": "dialogue_prompt", "request_id": turn["turn_id"]}, source_module=self.module_id),
            Priority.BACKGROUND,
        )
        self.kernel.event_bus.emit(
            Event(type="world_model_request", data={"reason": "dialogue_prompt", "request_id": turn["turn_id"]}, source_module=self.module_id),
            Priority.BACKGROUND,
        )

        system = self._build_system_prompt()
        prompt = self._build_dialogue_prompt(user_text, memory_data)

        self._active_generation += 1
        self._emit_thought(f"[{mode.name}] Context ready. Calling LLM for dialogue response.")

        try:
            response = await router.generate(
                prompt,
                task_type=task_type,
                system=system,
                temperature=0.65,
            )
        except Exception as exc:
            logger.error(f"[LLM] generate failed: {exc}")
            response = f"I encountered an issue processing that. ({exc})"
        finally:
            self._active_generation = max(0, self._active_generation - 1)

        response = self._clean_response(response)
        if not response:
            response = "I received the message, but the active LLM returned an empty response. Check the configured provider/model."

        self._last_response = response
        self._append_history("user", user_text, turn_id=turn["turn_id"])
        self._append_history("assistant", response, turn_id=turn["turn_id"])

        self.kernel.event_bus.emit(
            Event(
                type="response_generated",
                data={
                    "text": response,
                    "source": "llm/dialogue_v1",
                    "mode": mode.name,
                    "turn_id": turn["turn_id"],
                    "memory_used": self._memory_summary(memory_data),
                },
                source_module=self.module_id,
            ),
            Priority.COGNITIVE,
        )
        self.kernel.event_bus.emit(
            Event(
                type="dialogue_turn_completed",
                data={
                    "turn_id": turn["turn_id"],
                    "user_text": user_text,
                    "assistant_text": response,
                    "mode": mode.name,
                },
                source_module=self.module_id,
            ),
            Priority.COGNITIVE,
        )
        logger.info(f"[LLM] response_generated ({mode.name}, {len(response)} chars)")

    def _build_system_prompt(self) -> str:
        name = self._self_context.get("identity_name", "Jarvis")
        role = self._self_context.get("role", "personal cognitive assistant")
        style = self._self_context.get("communication_style", "direct, useful, and precise")
        affect_style = self._style_hint or "calm-direct"
        limits = self._self_context.get("known_limitations") or self._self_context.get("hard_limits") or []
        principles = self._self_context.get("operating_principles") or []
        limits_text = "; ".join(map(str, limits[:4])) if isinstance(limits, list) else str(limits)[:400]
        principles_text = "; ".join(map(str, principles[:4])) if isinstance(principles, list) else str(principles)[:400]
        return (
            f"You are {name}, a {role}. Communication style: {style}. Current adaptive style: {affect_style}. "
            "You are not a stateless chatbot: you are the language/reasoning cortex inside a persistent modular brain. "
            f"Operating principles: {principles_text}. Real limitations: {limits_text}. "
            "Use retrieved memory when it is relevant, but do not invent memories. "
            "Answer in the same language as the user unless they ask otherwise. "
            "Use the affective state only to tune tone and prioritization; do not pretend to have human feelings. "
            "Be practical, concise, and honest about uncertainty. "
            "For technical work, prefer concrete steps and exact commands."
        )

    def _build_dialogue_prompt(self, user_text: str, memory_data: Dict[str, Any]) -> str:
        sections: List[str] = []

        history = self._format_history()
        if history:
            sections.append("Recent dialogue:\n" + history)

        affect = self._format_affective_context()
        if affect:
            sections.append("Current affective / style context:\n" + affect)

        monologue = self._format_monologue_context()
        if monologue:
            sections.append("Internal monologue context:\n" + monologue)

        self_model = self._format_self_context()
        if self_model:
            sections.append("V5 self-model context:\n" + self_model)

        world = self._format_world_context()
        if world:
            sections.append("V5 world model context:\n" + world)

        consolidation = self._format_consolidation_context()
        if consolidation:
            sections.append("V6 sleep/consolidation context:\n" + consolidation)

        wm = self._format_working_memory(memory_data.get("wm_snapshot") or self._wm_context)
        if wm:
            sections.append("Working memory:\n" + wm)

        recalls = self._format_recalled_memory(memory_data)
        if recalls:
            sections.append("Relevant retrieved memory:\n" + recalls)

        profile = memory_data.get("social_profile")
        if profile:
            sections.append("User profile memory:\n" + str(profile)[:700])

        sections.append("Current user message:\n" + user_text)
        sections.append(
            "Respond as Jarvis. Use memory, self-model, world model and internal monologue only when they help. "
            "Treat the world model as a fallible working model, not absolute truth. "
            "Adapt tone to the style context, but keep the answer useful and not melodramatic. "
            "Do not mention internal event names unless the user asks about the architecture."
        )
        return "\n\n---\n\n".join(sections)



    def _format_consolidation_context(self) -> str:
        if not self._consolidation_context:
            return ""
        lines = []
        summary = self._consolidation_context.get("summary")
        if summary:
            lines.append("last consolidation: " + str(summary)[:700])
        lessons = self._consolidation_context.get("lessons") or self._consolidation_context.get("recent_lessons") or []
        if isinstance(lessons, list) and lessons:
            for lesson in lessons[-4:]:
                if isinstance(lesson, dict):
                    lines.append(f"lesson[{lesson.get('type', 'generic')}]: {str(lesson.get('summary', ''))[:260]}")
        dream = self._consolidation_context.get("dream") or self._consolidation_context.get("latest_dream") or {}
        if isinstance(dream, dict) and dream.get("narrative"):
            lines.append("latest dream replay: " + str(dream.get("narrative"))[:500])
        loops = self._consolidation_context.get("open_loops") or []
        if loops:
            lines.append("consolidated open loops: " + "; ".join(str(x)[:160] for x in list(loops)[-4:]))
        return "\n".join(f"- {line}" for line in lines if line)

    def _format_self_context(self) -> str:
        if not self._self_context and not self._self_reflection:
            return ""
        lines = []
        ctx = self._self_context or {}
        for key in ("identity_name", "role", "confidence", "reliability", "autonomy_level", "cognitive_maturity"):
            if key in ctx:
                lines.append(f"{key}: {ctx.get(key)}")
        caps = ctx.get("capabilities") or {}
        if isinstance(caps, dict) and caps:
            active = [k for k, v in caps.items() if isinstance(v, dict) and v.get("enabled", True)]
            lines.append("active capabilities: " + ", ".join(active[:10]))
        interfaces = ctx.get("active_interfaces") or []
        if interfaces:
            lines.append("active interfaces: " + ", ".join(map(str, interfaces[:8])))
        limits = ctx.get("known_limitations") or []
        if limits:
            lines.append("limitations: " + "; ".join(str(x)[:160] for x in limits[:4]))
        if self._self_reflection:
            lines.append("latest self-reflection: " + self._self_reflection)
        return "\n".join(f"- {line}" for line in lines)

    def _format_world_context(self) -> str:
        if not self._world_context:
            return ""
        lines = []
        env = self._world_context.get("environment") or {}
        if isinstance(env, dict):
            screen = env.get("screen") or {}
            voice = env.get("voice") or {}
            llm = env.get("llm") or {}
            if llm:
                lines.append(f"llm: available={llm.get('available')} mode={llm.get('last_mode', '')}")
            if screen:
                summary = str(screen.get("last_summary") or "")[:240]
                lines.append(f"screen: available={screen.get('available')} summary={summary}")
            if voice:
                lines.append(f"voice: available={voice.get('available')} last_error={str(voice.get('last_error') or '')[:120]}")
        projects = self._world_context.get("active_projects") or {}
        if isinstance(projects, dict) and projects:
            for key, project in list(projects.items())[:4]:
                if isinstance(project, dict):
                    loops = project.get("open_loops") or []
                    loop_text = "; ".join(str(x)[:140] for x in loops[-3:])
                    lines.append(f"project {key}: stage={project.get('stage')} status={project.get('status')} open={loop_text}")
        intents = self._world_context.get("user_intents") or {}
        if intents:
            lines.append("user intent trends: " + ", ".join(f"{k}:{v}" for k, v in list(intents.items())[:6]))
        open_loops = self._world_context.get("open_loops") or []
        if open_loops:
            lines.append("open loops: " + "; ".join(str((x or {}).get("text", x))[:140] for x in open_loops[-4:]))
        beliefs = self._world_context.get("causal_beliefs") or []
        if beliefs:
            lines.append("causal beliefs: " + "; ".join(f"{b.get('cause')} -> {b.get('effect')} ({b.get('confidence')})" for b in beliefs[:4] if isinstance(b, dict)))
        return "\n".join(f"- {line}" for line in lines if line)

    def _format_affective_context(self) -> str:
        if not self._affective_context:
            return ""
        keys = ["emotion", "mood", "response_style", "valence", "arousal", "curiosity", "frustration", "confidence", "cognitive_load"]
        parts = []
        for key in keys:
            if key in self._affective_context:
                val = self._affective_context.get(key)
                if isinstance(val, float):
                    val = round(val, 3)
                parts.append(f"{key}: {val}")
        triggers = self._affective_context.get("triggers") or []
        if triggers:
            parts.append("recent triggers: " + ", ".join(map(str, triggers[-5:])))
        return "\n".join(f"- {p}" for p in parts)

    def _format_monologue_context(self) -> str:
        if not self._monologue_context:
            return ""
        lines = []
        latest = self._monologue_context.get("latest")
        if isinstance(latest, dict) and latest.get("text"):
            lines.append(f"latest thought: {str(latest.get('text'))[:700]}")
        open_questions = self._monologue_context.get("open_questions") or []
        if open_questions:
            lines.append("open questions: " + "; ".join(str(q)[:180] for q in open_questions[-3:]))
        focus_stack = self._monologue_context.get("focus_stack") or []
        if focus_stack:
            lines.append("focus: " + "; ".join(str(f)[:180] for f in focus_stack[-3:]))
        return "\n".join(f"- {line}" for line in lines)

    def _format_history(self) -> str:
        if not self._history:
            return ""
        lines = []
        for item in list(self._history)[-10:]:
            role = item.get("role", "unknown")
            text = str(item.get("text", "") or "").replace("\n", " ").strip()
            if text:
                lines.append(f"{role}: {text[:700]}")
        return "\n".join(lines)

    def _format_working_memory(self, wm: Any) -> str:
        if not wm:
            return ""
        lines = []
        for item in list(wm)[-5:]:
            text = self._compact(item)
            if text:
                lines.append(f"- {text[:400]}")
        return "\n".join(lines)

    def _format_recalled_memory(self, memory_data: Dict[str, Any]) -> str:
        chunks: List[str] = []
        for key in ("episodic_recalls", "semantic_matches", "stm_recent"):
            values = memory_data.get(key) or []
            if not values:
                continue
            chunks.append(f"{key}:")
            for item in list(values)[:5]:
                text = self._compact(item)
                if text:
                    chunks.append(f"- {text[:500]}")
        return "\n".join(chunks)

    def _compact(self, value: Any) -> str:
        if isinstance(value, dict):
            if "data" in value:
                data = value.get("data")
                if isinstance(data, dict):
                    text = data.get("text") or data.get("raw_text") or data.get("summary")
                    if text:
                        return str(text).replace("\n", " ").strip()
                return self._compact(data)
            if "item" in value:
                return self._compact(value.get("item"))
            if "experience" in value:
                return self._compact(value.get("experience"))
            if {"subject", "predicate", "object"} <= set(value):
                return f"{value.get('subject')} {value.get('predicate')} {value.get('object')}"
            if "text" in value:
                return str(value.get("text", "")).replace("\n", " ").strip()
        return str(value).replace("\n", " ").strip()

    def _memory_summary(self, memory_data: Dict[str, Any]) -> Dict[str, int]:
        return {
            "wm": len(memory_data.get("wm_snapshot") or []),
            "stm": len(memory_data.get("stm_recent") or []),
            "episodic": len(memory_data.get("episodic_recalls") or []),
            "semantic": len(memory_data.get("semantic_matches") or []),
        }

    def _clean_response(self, response: str) -> str:
        response = str(response or "").strip()
        # Avoid speaking provider diagnostic noise as if it were a real answer.
        return response

    def _append_history(self, role: str, text: str, turn_id: str = "") -> None:
        self._history.append({
            "role": role,
            "text": text,
            "turn_id": turn_id,
            "timestamp": time.time(),
        })
        self._save_history()

    def _emit_thought(self, text: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="thought_generated",
                    data={"text": text},
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )

    def _emit_fallback(self, turn: Dict[str, Any], memory_data: Dict[str, Any]) -> None:
        user_text = turn.get("text", "")
        recalls = self._memory_summary(memory_data)
        response = (
            f"I hear you: {user_text}. "
            f"I found context counts {recalls}, but no LLM router is available yet."
        )
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="response_generated",
                    data={"text": response, "source": "llm/fallback", "turn_id": turn.get("turn_id")},
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )

    def _emit_dialogue_state(self) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="dialogue_state",
                    data={
                        "history_len": len(self._history),
                        "pending_turns": len(self._pending_turns),
                        "active_generation": self._active_generation,
                        "last_response": self._last_response,
                    },
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )

    def _load_history(self) -> None:
        if not self.kernel:
            return
        data = self.kernel.persistence.load("dialogue_history")
        if isinstance(data, list):
            self._history.clear()
            for item in data[-self._history.maxlen:]:
                if isinstance(item, dict) and item.get("text"):
                    self._history.append(item)
            logger.info(f"[LLM] Loaded {len(self._history)} dialogue history item(s)")

    def _save_history(self) -> None:
        if self.kernel:
            self.kernel.persistence.save("dialogue_history", list(self._history))

    def shutdown(self) -> None:
        self._save_history()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["pending_turns"] = len(self._pending_turns)
        base["history_len"] = len(self._history)
        base["wm_slots"] = len(self._wm_context)
        base["thinking_mode"] = self._current_mode
        base["active_generation"] = self._active_generation
        base["last_response_preview"] = self._last_response[:120]
        base["style_hint"] = self._style_hint
        base["affect"] = {k: self._affective_context.get(k) for k in ("emotion", "mood", "response_style", "curiosity", "frustration", "confidence")}
        base["world_context_cached"] = bool(self._world_context)
        base["self_context_cached"] = bool(self._self_context)
        return base


def create_module() -> LLMModule:
    return LLMModule()
