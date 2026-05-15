"""Tier 3 Reasoning: LLM Module

The LLM is the reasoning accelerator — language cortex and planning engine.
It does NOT own identity, memory, goals, or continuity.

It receives context assembled from the kernel state and calls the LLMRouter
to produce thoughts and responses.  ThinkingModeSelector determines how
deeply to reason for each input.

Emits:
  - thought_generated      (COGNITIVE)
  - response_generated     (COGNITIVE)
  - thinking_mode_changed  (COGNITIVE)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority

logger = logging.getLogger("llm")


class LLMModule(CognitiveModule):
    """Tier 3: Reasoning accelerator backed by LLMRouter."""

    MODULE_DESCRIPTION = "Language cortex — reasoning, planning, response generation"

    def __init__(self) -> None:
        super().__init__(
            module_id="llm",
            cost={"cpu": 0.40, "gpu": 0.20, "ram": 0.30},
        )
        self._pending_input: Optional[str] = None
        self._self_context: dict = {}
        self._wm_context: list = []
        self._current_mode: int = 1   # ThinkingMode.REACTIVE
        self._mode_selector = None

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        from core.thinking_modes import ThinkingModeSelector
        self._mode_selector = ThinkingModeSelector()
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "user_utterance",
                "memory_retrieved",
                "context_request",
                "sensory_input",
                "self_model_updated",
                "wm_updated",
            ],
        )

    async def on_event(self, event: Event) -> None:
        et = event.type
        if et == "user_utterance":
            text = event.data.get("text", "")
            self._pending_input = text
            # Select thinking mode before doing anything
            if self.kernel and self._mode_selector:
                from core.thinking_modes import ThinkingMode
                mode = self._mode_selector.select(event, self.kernel.core_state)
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
            # Request memory context before generating response
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="memory_request",
                        data={"query_type": "semantic", "subject": text},
                        source_module=self.module_id,
                    ),
                    Priority.COGNITIVE,
                )
        elif et == "memory_retrieved":
            if self._pending_input:
                asyncio.ensure_future(
                    self._generate_response(self._pending_input, event.data)
                )
                self._pending_input = None
        elif et == "sensory_input":
            self._emit_thought("Noticing sensory change... adapting context.")
        elif et == "self_model_updated":
            self._self_context = event.data
        elif et == "wm_updated":
            self._wm_context = event.data.get("snapshot", [])

    async def _generate_response(
        self, user_text: str, memory_data: Dict[str, Any]
    ) -> None:
        if not self.kernel:
            return
        router = getattr(self.kernel, "llm_router", None)
        if router is None:
            self._emit_fallback(user_text)
            return

        from core.thinking_modes import ThinkingMode
        from core.llm_router import TaskType

        mode = ThinkingMode(self._current_mode)

        # Select task type based on thinking mode
        task_map = {
            ThinkingMode.REFLEX: TaskType.SIMPLE_CHAT,
            ThinkingMode.REACTIVE: TaskType.SIMPLE_CHAT,
            ThinkingMode.DELIBERATIVE: TaskType.COMPLEX_REASONING,
            ThinkingMode.IMAGINATION: TaskType.CREATIVE_IMAGINATION,
            ThinkingMode.DEEP_ANALYSIS: TaskType.COMPLEX_REASONING,
            ThinkingMode.BACKGROUND: TaskType.SUMMARIZATION,
        }
        task_type = task_map.get(mode, TaskType.SIMPLE_CHAT)

        # Assemble context
        system = self._build_system_prompt()
        prompt = self._build_prompt(user_text, memory_data)

        # Emit thought before calling LLM
        self._emit_thought(f"[{mode.name}] Processing: {user_text[:60]}")

        try:
            response = await router.generate(prompt, task_type=task_type, system=system)
        except Exception as exc:
            logger.error(f"[LLM] generate failed: {exc}")
            response = f"I encountered an issue processing that. ({exc})"

        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="response_generated",
                    data={"text": response, "source": "llm", "mode": mode.name},
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )
            logger.info(f"[LLM] response_generated ({mode.name}, {len(response)} chars)")

    def _build_system_prompt(self) -> str:
        parts = []
        name = self._self_context.get("identity_name", "Jarvis")
        role = self._self_context.get("role", "cognitive assistant")
        style = self._self_context.get("communication_style", "thoughtful and precise")
        parts.append(f"You are {name}, a {role}. Communication style: {style}.")
        parts.append(
            "You are a cognitive reasoning module — not a simple chatbot. "
            "Think in possibilities, not single answers. "
            "Distinguish facts from assumptions. Never hallucinate with confidence."
        )
        if self._wm_context:
            wm_items = [
                str(item.get("data", item))[:50]
                for item in self._wm_context[:3]
                if item
            ]
            if wm_items:
                parts.append(f"Currently holding in mind: {'; '.join(wm_items)}")
        return " ".join(parts)

    def _build_prompt(self, user_text: str, memory_data: Dict[str, Any]) -> str:
        prompt = user_text
        mem_items = memory_data.get("items", [])
        if mem_items:
            mem_str = "\n".join(f"- {str(m)[:80]}" for m in mem_items[:3])
            prompt = f"Relevant memory:\n{mem_str}\n\nUser: {user_text}"
        return prompt

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

    def _emit_fallback(self, user_text: str) -> None:
        length = len(user_text)
        if length < 10:
            response = f"I hear you: '{user_text}'. Tell me more?"
        elif length < 30:
            response = f"Interesting. Regarding '{user_text}', my thoughts are forming."
        else:
            response = "You've shared quite a bit. I need to process this carefully."
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(
                    type="response_generated",
                    data={"text": response, "source": "llm/fallback"},
                    source_module=self.module_id,
                ),
                Priority.COGNITIVE,
            )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["pending_input"] = self._pending_input is not None
        base["wm_slots"] = len(self._wm_context)
        base["thinking_mode"] = self._current_mode
        return base


def create_module() -> LLMModule:
    return LLMModule()
