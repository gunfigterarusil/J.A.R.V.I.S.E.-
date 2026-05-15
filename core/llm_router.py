"""core/llm_router.py — Multi-LLM provider abstraction and routing.

The LLMRouter selects the appropriate AI provider based on task type,
availability, and configuration.  The brain never calls an LLM directly —
it always goes through this router.

All providers are optional: if an SDK is missing or a service is unreachable,
that provider marks itself unavailable and the router falls back to the next
configured option, ultimately landing on NullProvider which always responds.

Usage in modules:
    response = await self.kernel.llm_router.generate(prompt, task_type=TaskType.SIMPLE_CHAT)
    theories = await self.kernel.llm_router.imagine(seed=problem, context=ctx)
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("core.llm_router")


# ---------------------------------------------------------------------------
# Task types
# ---------------------------------------------------------------------------
class TaskType(Enum):
    SIMPLE_CHAT = "simple_chat"
    COMPLEX_REASONING = "complex_reasoning"
    SUMMARIZATION = "summarization"
    MEMORY_COMPRESSION = "memory_compression"
    CREATIVE_IMAGINATION = "creative_imagination"
    PLANNING = "planning"
    EMBEDDING = "embedding"


# ---------------------------------------------------------------------------
# Provider abstract base
# ---------------------------------------------------------------------------
class LLMProvider(ABC):
    """Swappable AI backend.  Every provider must implement generate() and imagine()."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def is_available(self) -> bool:
        return False

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", **kwargs) -> str: ...

    async def imagine(self, seed: str, context: dict) -> List[dict]:
        """Generate competing theories.  Returns list of Theory-like dicts."""
        prompt = _build_imagine_prompt(seed, context)
        raw = await self.generate(prompt, system=_IMAGINATION_SYSTEM)
        return _parse_theories(raw, seed)

    async def summarize(self, text: str) -> str:
        return await self.generate(
            f"Summarize the following concisely:\n\n{text}",
            system="You are a precise summarizer. Be brief.",
        )

    async def reason(self, problem: str, context: dict) -> dict:
        ctx_str = json.dumps(context, default=str)[:800]
        prompt = f"Problem: {problem}\n\nContext: {ctx_str}\n\nProvide structured reasoning."
        raw = await self.generate(prompt, system=_REASONING_SYSTEM)
        return {"reasoning": raw, "problem": problem}


# ---------------------------------------------------------------------------
# NullProvider — always available, deterministic stubs
# ---------------------------------------------------------------------------
class NullProvider(LLMProvider):
    """Fallback when no real provider is configured.
    Returns structured low-confidence stubs — never random noise.
    """

    @property
    def name(self) -> str:
        return "null"

    @property
    def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        return (
            "[NullProvider] No LLM configured. "
            "Configure a provider in config.llm to enable real reasoning."
        )

    async def imagine(self, seed: str, context: dict) -> List[dict]:
        return [
            {
                "theory": f"Hypothesis A: The issue may be related to '{seed[:60]}'.",
                "confidence": 0.3,
                "risk": 0.2,
                "evidence": [],
                "missing_evidence": ["Real LLM analysis needed"],
                "possible_tests": ["Enable an LLM provider for full analysis"],
                "predicted_outcomes": ["Uncertain without reasoning engine"],
                "alternative_explanations": [],
            }
        ]


# ---------------------------------------------------------------------------
# OllamaProvider — local Ollama server (no API key required)
# ---------------------------------------------------------------------------
class OllamaProvider(LLMProvider):
    """Connects to a local Ollama instance at http://localhost:11434."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.2",
                 timeout: float = 60.0) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return f"ollama/{self._model}"

    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._available = self._check_available()
        return self._available

    def _check_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        try:
            import urllib.request, urllib.error
            payload = json.dumps({
                "model": self._model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"temperature": kwargs.get("temperature", 0.7)},
            }).encode()
            req = urllib.request.Request(
                f"{self._host}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            loop = asyncio.get_event_loop()
            def _call():
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    return json.loads(r.read())
            result = await loop.run_in_executor(None, _call)
            return result.get("response", "")
        except Exception as exc:
            logger.error(f"[Ollama] generate failed: {exc}")
            return f"[Ollama error: {exc}]"


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider — OpenAI, LM Studio, vLLM, etc.
# ---------------------------------------------------------------------------
class OpenAICompatibleProvider(LLMProvider):
    """Works with any OpenAI-compatible API (OpenAI, LM Studio, vLLM, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4o",
                 base_url: str = "https://api.openai.com/v1",
                 timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._client = None

    @property
    def name(self) -> str:
        return f"openai/{self._model}"

    @property
    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        try:
            client = self._get_client()
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=kwargs.get("max_tokens", 2048),
                temperature=kwargs.get("temperature", 0.7),
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error(f"[OpenAI] generate failed: {exc}")
            return f"[OpenAI error: {exc}]"


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------
class GeminiProvider(LLMProvider):
    """Google Gemini via google-generativeai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash",
                 timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = None

    @property
    def name(self) -> str:
        return f"gemini/{self._model}"

    @property
    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import google.generativeai  # noqa: F401
            return True
        except ImportError:
            return False

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(
                self._model,
                system_instruction=system or None,
            )
            loop = asyncio.get_event_loop()
            full_prompt = prompt
            resp = await loop.run_in_executor(
                None, lambda: model.generate_content(full_prompt)
            )
            return resp.text or ""
        except Exception as exc:
            logger.error(f"[Gemini] generate failed: {exc}")
            return f"[Gemini error: {exc}]"


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------
class AnthropicProvider(LLMProvider):
    """Anthropic Claude via anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6",
                 timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = None

    @property
    def name(self) -> str:
        return f"anthropic/{self._model}"

    @property
    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        try:
            client = self._get_client()
            kwargs_msg: Dict[str, Any] = {
                "model": self._model,
                "max_tokens": kwargs.get("max_tokens", 2048),
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs_msg["system"] = system
            response = await client.messages.create(**kwargs_msg)
            return response.content[0].text if response.content else ""
        except Exception as exc:
            logger.error(f"[Anthropic] generate failed: {exc}")
            return f"[Anthropic error: {exc}]"


# ---------------------------------------------------------------------------
# LlamaCppProvider — llama.cpp HTTP server
# ---------------------------------------------------------------------------
class LlamaCppProvider(LLMProvider):
    """llama.cpp server (OpenAI-compatible /v1/completions endpoint)."""

    def __init__(self, host: str = "http://localhost:8080", timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def is_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._host}/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        try:
            import urllib.request
            full = f"{system}\n\n{prompt}" if system else prompt
            payload = json.dumps({
                "prompt": full,
                "n_predict": kwargs.get("max_tokens", 1024),
                "temperature": kwargs.get("temperature", 0.7),
                "stop": kwargs.get("stop", []),
            }).encode()
            req = urllib.request.Request(
                f"{self._host}/completion",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            loop = asyncio.get_event_loop()
            def _call():
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    return json.loads(r.read())
            result = await loop.run_in_executor(None, _call)
            return result.get("content", "")
        except Exception as exc:
            logger.error(f"[LlamaCpp] generate failed: {exc}")
            return f"[LlamaCpp error: {exc}]"


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------
_DEFAULT_ROUTING = {
    TaskType.SIMPLE_CHAT: ["ollama", "openai", "gemini", "anthropic", "llamacpp"],
    TaskType.COMPLEX_REASONING: ["ollama", "anthropic", "openai", "gemini", "llamacpp"],
    TaskType.CREATIVE_IMAGINATION: ["ollama", "anthropic", "openai", "gemini", "llamacpp"],
    TaskType.PLANNING: ["ollama", "openai", "anthropic", "gemini", "llamacpp"],
    TaskType.SUMMARIZATION: ["ollama", "openai", "gemini", "anthropic", "llamacpp"],
    TaskType.MEMORY_COMPRESSION: ["ollama", "openai", "gemini", "llamacpp"],
    TaskType.EMBEDDING: ["openai", "ollama"],
}


class LLMRouter:
    """Routes LLM calls to the best available provider for each task type."""

    def __init__(self, config: Any = None) -> None:
        self._providers: Dict[str, LLMProvider] = {}
        self._null = NullProvider()
        self._routing: Dict[TaskType, List[str]] = dict(_DEFAULT_ROUTING)
        self._config = config
        self._setup_from_config(config)

    def _setup_from_config(self, config: Any) -> None:
        if config is None:
            return
        # Ollama
        ollama_model = getattr(config, "ollama_model", "llama3.2")
        ollama_host = getattr(config, "ollama_host", "http://localhost:11434")
        self.register_provider("ollama", OllamaProvider(ollama_host, ollama_model))

        # OpenAI-compatible
        openai_key = getattr(config, "openai_api_key", "")
        if openai_key:
            self.register_provider("openai", OpenAICompatibleProvider(
                api_key=openai_key,
                model=getattr(config, "openai_model", "gpt-4o"),
                base_url=getattr(config, "openai_base_url", "https://api.openai.com/v1"),
            ))

        # Gemini
        gemini_key = getattr(config, "gemini_api_key", "")
        if gemini_key:
            self.register_provider("gemini", GeminiProvider(
                api_key=gemini_key,
                model=getattr(config, "gemini_model", "gemini-2.0-flash"),
            ))

        # Anthropic
        anthropic_key = getattr(config, "anthropic_api_key", "")
        if anthropic_key:
            self.register_provider("anthropic", AnthropicProvider(
                api_key=anthropic_key,
                model=getattr(config, "anthropic_model", "claude-sonnet-4-6"),
            ))

        # llama.cpp
        llamacpp_host = getattr(config, "llamacpp_host", "http://localhost:8080")
        self.register_provider("llamacpp", LlamaCppProvider(llamacpp_host))

        # Override routing if config specifies preferred providers per task
        routing_cfg = getattr(config, "routing", {})
        for task_str, provider_name in routing_cfg.items():
            try:
                task = TaskType(task_str)
                self._routing[task] = [provider_name] + [
                    p for p in self._routing.get(task, []) if p != provider_name
                ]
            except ValueError:
                pass

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        self._providers[name] = provider
        logger.debug(f"[LLMRouter] Registered provider: {name} "
                     f"(available={provider.is_available})")

    def route(self, task_type: TaskType) -> LLMProvider:
        """Return the best available provider for this task type."""
        preference = self._routing.get(task_type, list(self._providers.keys()))
        for name in preference:
            provider = self._providers.get(name)
            if provider and provider.is_available:
                return provider
        # Fallback: any available
        for provider in self._providers.values():
            if provider.is_available:
                return provider
        return self._null

    def available_providers(self) -> List[str]:
        result = []
        for name, p in self._providers.items():
            if p.is_available:
                result.append(name)
        if not result:
            result.append("null")
        return result

    async def generate(self, prompt: str,
                       task_type: TaskType = TaskType.SIMPLE_CHAT,
                       system: str = "",
                       **kwargs) -> str:
        provider = self.route(task_type)
        logger.debug(f"[LLMRouter] {task_type.value} → {provider.name}")
        return await provider.generate(prompt, system=system, **kwargs)

    async def imagine(self, seed: str, context: dict,
                      task_type: TaskType = TaskType.CREATIVE_IMAGINATION) -> List[dict]:
        provider = self.route(task_type)
        logger.debug(f"[LLMRouter] imagine → {provider.name}")
        return await provider.imagine(seed, context)

    async def summarize(self, text: str) -> str:
        return await self.route(TaskType.SUMMARIZATION).summarize(text)

    async def reason(self, problem: str, context: dict) -> dict:
        return await self.route(TaskType.COMPLEX_REASONING).reason(problem, context)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------
_IMAGINATION_SYSTEM = (
    "You are an imagination engine for a cognitive AI. "
    "Generate multiple competing hypotheses or theories to explain a problem. "
    "Return a JSON array of theory objects. Each object must have: "
    "theory (string), confidence (0-1), risk (0-1), evidence (list), "
    "missing_evidence (list), possible_tests (list), predicted_outcomes (list), "
    "alternative_explanations (list). "
    "Be creative but grounded. Separate facts from speculation."
)

_REASONING_SYSTEM = (
    "You are a structured reasoning engine. "
    "Analyze problems systematically. Distinguish known facts from assumptions. "
    "Always consider multiple explanations before concluding."
)


def _build_imagine_prompt(seed: str, context: dict) -> str:
    ctx_str = json.dumps(context, default=str)[:600]
    return (
        f"Generate 3-5 competing hypotheses for this problem:\n\n"
        f"PROBLEM: {seed}\n\n"
        f"CONTEXT: {ctx_str}\n\n"
        f"Return a JSON array of theory objects. "
        f"Rank by confidence descending. Clearly mark what is known vs assumed."
    )


def _parse_theories(raw: str, seed: str) -> List[dict]:
    """Try to parse LLM output as a JSON list of theories. Fallback on error."""
    raw = raw.strip()
    # Try to extract JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1:
        try:
            data = json.loads(raw[start:end + 1])
            if isinstance(data, list) and data:
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: wrap raw text as a single theory
    return [{
        "theory": raw[:300] if raw else f"Unable to parse theories for: {seed[:60]}",
        "confidence": 0.4,
        "risk": 0.3,
        "evidence": [],
        "missing_evidence": ["Structured JSON parse failed"],
        "possible_tests": [],
        "predicted_outcomes": [],
        "alternative_explanations": [],
    }]
