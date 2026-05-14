"""Tier 3: LLM Module
Simulates language model cognition: reasoning, planning, and response generation.
No external APIs — purely self-contained stubs that emit cognitive events via EventBus.
"""
from __future__ import annotations

import time
import logging
from typing import Dict, Any

from kernel_main import CognitiveModule, Event, Priority

logger = logging.getLogger("llm")


class LLMModule(CognitiveModule):
    """
    Tier 3: High-level cognition accelerator (placeholder).
    Emulates:
    - Abstract reasoning via 'thought_generated'
    - Planning via 'plan_generated'
    - Response via 'response_generated'
    - Internal monologue via 'internal_monologue'
    """

    def __init__(self) -> None:
        super().__init__(
            module_id="llm",
            cost={"cpu": 0.40, "gpu": 0.20, "ram": 0.30},
        )
        self._last_monologue = 0.0
        self._monologue_interval = 5.0
        self._pending_input: str | None = None

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "user_utterance",
                "memory_retrieved",
                "context_request",
                "sensory_input",
            ],
        )

    async def on_event(self, event: Event) -> None:
        et = event.type
        if et == "user_utterance":
            text = event.data.get("text", "")
            self._pending_input = text
            # Request context from memory before generating response
            if self.kernel:
                self.kernel.event_bus.emit(
                    Event(
                        type="memory_request",
                        data={"query_type": "semantic", "subject": text},
                    ),
                    Priority.COGNITIVE,
                )
                logger.info(f"[LLM] Received user_utterance, requesting memory context")
        elif et == "memory_retrieved":
            if self._pending_input:
                # Simulate reasoning + response generation
                self._generate_response(self._pending_input, event.data)
                self._pending_input = None
        elif et == "sensory_input":
            # Brief reflection on sensory change
            self._emit_thought("Noticing sensory change... adapting.")

    def _generate_response(self, user_text: str, memory_data: Dict[str, Any]) -> None:
        # Stub: generate deterministic text based on input length
        length = len(user_text)
        if length < 10:
            response = f"I hear you say: '{user_text}'. Tell me more?"
        elif length < 30:
            response = f"Interesting. Regarding '{user_text}', my thoughts are forming."
        else:
            response = f"You've shared quite a bit. I need to process this deeply."

        if self.kernel:
            # Emit thought first (reasoning)
            self.kernel.event_bus.emit(
                Event(type="thought_generated", data={"text": f"Thinking about: {user_text}"}),
                Priority.COGNITIVE,
            )
            # Then emit response
            self.kernel.event_bus.emit(
                Event(type="response_generated", data={"text": response, "source": "llm"}),
                Priority.COGNITIVE,
            )
            logger.info(f"[LLM] response_generated: {response}")

    def _emit_thought(self, text: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(type="thought_generated", data={"text": text}),
                Priority.COGNITIVE,
            )

    def update(self, dt: float) -> None:
        # Periodic internal monologue when idle
        now = time.time()
        if now - self._last_monologue >= self._monologue_interval:
            self._last_monologue = now
            self._emit_internal_monologue()

    def _emit_internal_monologue(self) -> None:
        import random
        phrases = [
            "Wondering about the nature of existence...",
            "Processing recent memories...",
            "Should I initiate conversation?",
            "Feeling curious about user's intent.",
            "Re-evaluating priorities...",
        ]
        text = random.choice(phrases)
        if self.kernel:
            self.kernel.event_bus.emit(
                Event(type="internal_monologue", data={"text": text}),
                Priority.BACKGROUND,
            )
            logger.info(f"[LLM] internal_monologue: {text}")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["pending_input"] = self._pending_input is not None
        return base
