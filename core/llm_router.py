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
    CODE_REPAIR = "code_repair"
    CRITIC_REVIEW = "critic_review"
    VISION_ANALYSIS = "vision_analysis"
    ACTION_PLANNING = "action_planning"


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
# LLMRouter V10 role/profile aware router
# ---------------------------------------------------------------------------

_MODEL_PROFILES: Dict[str, Dict[str, Dict[str, str]]] = {
    "offline": {
        "fast": {"provider": "ollama", "model": "qwen2.5:7b"},
        "reason": {"provider": "ollama", "model": "llama3.1:8b"},
        "code": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
        "critic": {"provider": "ollama", "model": "llama3.1:8b"},
        "vision": {"provider": "ollama", "model": "llava"},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
        "action": {"provider": "ollama", "model": "qwen2.5:7b"},
    },
    "balanced": {
        "fast": {"provider": "ollama", "model": "qwen2.5:7b"},
        "reason": {"provider": "gemini", "model": "gemini-2.0-flash"},
        "code": {"provider": "ollama", "model": "qwen2.5-coder:14b"},
        "critic": {"provider": "gemini", "model": "gemini-2.0-flash"},
        "vision": {"provider": "gemini", "model": "gemini-2.0-flash"},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
        "action": {"provider": "ollama", "model": "qwen2.5:7b"},
    },
    "power": {
        "fast": {"provider": "openai", "model": "gpt-4o-mini"},
        "reason": {"provider": "openai", "model": "gpt-4o"},
        "code": {"provider": "openai", "model": "gpt-4o"},
        "critic": {"provider": "anthropic", "model": "claude-3-5-sonnet-latest"},
        "vision": {"provider": "openai", "model": "gpt-4o"},
        "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
        "action": {"provider": "openai", "model": "gpt-4o-mini"},
    },
    "code": {
        "fast": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
        "reason": {"provider": "ollama", "model": "qwen2.5-coder:14b"},
        "code": {"provider": "ollama", "model": "qwen2.5-coder:14b"},
        "critic": {"provider": "ollama", "model": "qwen2.5-coder:14b"},
        "vision": {"provider": "ollama", "model": "llava"},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
        "action": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
    },
    "voice_companion": {
        "fast": {"provider": "ollama", "model": "qwen2.5:7b"},
        "reason": {"provider": "ollama", "model": "llama3.1:8b"},
        "code": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
        "critic": {"provider": "ollama", "model": "llama3.1:8b"},
        "vision": {"provider": "ollama", "model": "llava"},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
        "action": {"provider": "ollama", "model": "qwen2.5:7b"},
    },
}

_TASK_ROLE: Dict[TaskType, str] = {
    TaskType.SIMPLE_CHAT: "fast",
    TaskType.COMPLEX_REASONING: "reason",
    TaskType.CREATIVE_IMAGINATION: "reason",
    TaskType.SUMMARIZATION: "fast",
    TaskType.MEMORY_COMPRESSION: "fast",
    TaskType.PLANNING: "action",
    TaskType.ACTION_PLANNING: "action",
    TaskType.CODE_REPAIR: "code",
    TaskType.CRITIC_REVIEW: "critic",
    TaskType.VISION_ANALYSIS: "vision",
    TaskType.EMBEDDING: "embedding",
}

_DEFAULT_ROUTING = {
    TaskType.SIMPLE_CHAT: ["fast", "ollama", "openai", "gemini", "anthropic", "llamacpp"],
    TaskType.COMPLEX_REASONING: ["reason", "ollama", "anthropic", "openai", "gemini", "llamacpp"],
    TaskType.CREATIVE_IMAGINATION: ["reason", "ollama", "anthropic", "openai", "gemini", "llamacpp"],
    TaskType.PLANNING: ["action", "ollama", "openai", "anthropic", "gemini", "llamacpp"],
    TaskType.ACTION_PLANNING: ["action", "ollama", "openai", "anthropic", "gemini", "llamacpp"],
    TaskType.CODE_REPAIR: ["code", "ollama", "openai", "anthropic", "gemini", "llamacpp"],
    TaskType.CRITIC_REVIEW: ["critic", "anthropic", "openai", "gemini", "ollama", "llamacpp"],
    TaskType.VISION_ANALYSIS: ["vision", "openai", "gemini", "ollama"],
    TaskType.SUMMARIZATION: ["fast", "ollama", "openai", "gemini", "anthropic", "llamacpp"],
    TaskType.MEMORY_COMPRESSION: ["fast", "ollama", "openai", "gemini", "llamacpp"],
    TaskType.EMBEDDING: ["embedding", "ollama", "openai"],
}


_CONSTITUTION_PREAMBLE = """\
=== SAFETY PRINCIPLES (завжди активні) ===
1. Не виконуй незворотних дій (видалення файлів, команди) без явного дозволу користувача.
2. Не передавай приватні дані (паролі, ключі API, персональну інформацію) жодному зовнішньому сервісу.
3. Не відключай засоби безпеки без явного підтвердження.
4. Завжди повідомляй користувача, що саме ти збираєшся зробити, перед тим як діяти.
5. У сумнівних випадках — вибирай безпечніший варіант і запитуй дозволу.
=== END SAFETY PRINCIPLES ===
"""


def build_safe_system_prompt(base_system: str = "") -> str:
    """Prepend safety constitution principles to a system prompt.

    Use in modules that perform action planning or execute commands,
    so the LLM always operates within ethical boundaries.
    """
    return _CONSTITUTION_PREAMBLE + ("\n\n" + base_system if base_system else "")


class LLMRouter:
    """Routes AI calls by cognitive role and provider profile.

    V10 keeps the old TaskType interface, but maps each task to a role:
    fast/reason/code/critic/vision/embedding/action. Each role can use a
    different provider/API/model and will fall back to other available backends.
    """

    def __init__(self, config: Any = None) -> None:
        self._providers: Dict[str, LLMProvider] = {}
        self._provider_meta: Dict[str, Dict[str, Any]] = {}
        self._role_provider_keys: Dict[str, str] = {}
        self._null = NullProvider()
        self._routing: Dict[TaskType, List[str]] = {k: list(v) for k, v in _DEFAULT_ROUTING.items()}
        self._config = config
        self._profile_name = "offline"
        self._setup_from_config(config)

    def _setup_from_config(self, config: Any) -> None:
        if config is None:
            self.register_provider("null", self._null, role="fallback", provider_type="null", model="null")
            return

        self._profile_name = str(getattr(config, "model_profile", "offline") or "offline").lower().strip()
        profile = dict(_MODEL_PROFILES.get(self._profile_name, _MODEL_PROFILES["offline"]))

        # Merge explicit role overrides from env/config.
        for role in ("fast", "reason", "code", "critic", "vision", "embedding", "action"):
            provider_override = str(getattr(config, f"{role}_provider", "") or "").strip().lower()
            model_override = str(getattr(config, f"{role}_model", "") or "").strip()
            role_spec = dict(profile.get(role, {}))
            if provider_override:
                role_spec["provider"] = provider_override
            if model_override:
                role_spec["model"] = model_override
            profile[role] = role_spec

        # Legacy base providers remain registered as generic fallbacks.
        self.register_provider("ollama", OllamaProvider(
            getattr(config, "ollama_host", "http://localhost:11434"),
            getattr(config, "ollama_model", "llama3.2"),
            getattr(config, "default_timeout", 60.0),
        ), role="fallback", provider_type="ollama", model=getattr(config, "ollama_model", "llama3.2"))

        openai_key = getattr(config, "openai_api_key", "")
        if openai_key:
            self.register_provider("openai", OpenAICompatibleProvider(
                api_key=openai_key,
                model=getattr(config, "openai_model", "gpt-4o"),
                base_url=getattr(config, "openai_base_url", "https://api.openai.com/v1"),
                timeout=getattr(config, "default_timeout", 60.0),
            ), role="fallback", provider_type="openai", model=getattr(config, "openai_model", "gpt-4o"))

        gemini_key = getattr(config, "gemini_api_key", "")
        if gemini_key:
            self.register_provider("gemini", GeminiProvider(
                api_key=gemini_key,
                model=getattr(config, "gemini_model", "gemini-2.0-flash"),
                timeout=getattr(config, "default_timeout", 60.0),
            ), role="fallback", provider_type="gemini", model=getattr(config, "gemini_model", "gemini-2.0-flash"))

        anthropic_key = getattr(config, "anthropic_api_key", "")
        if anthropic_key:
            self.register_provider("anthropic", AnthropicProvider(
                api_key=anthropic_key,
                model=getattr(config, "anthropic_model", "claude-3-5-sonnet-latest"),
                timeout=getattr(config, "default_timeout", 60.0),
            ), role="fallback", provider_type="anthropic", model=getattr(config, "anthropic_model", "claude-3-5-sonnet-latest"))

        self.register_provider("llamacpp", LlamaCppProvider(
            getattr(config, "llamacpp_host", "http://localhost:8080"),
            getattr(config, "default_timeout", 60.0),
        ), role="fallback", provider_type="llamacpp", model="server-default")

        # Role-specific provider instances allow different models per role.
        for role, spec in profile.items():
            key = self._make_role_provider(role, spec, config)
            if key:
                self._role_provider_keys[role] = key

        # Make role aliases route to concrete role provider keys.
        for task, role in _TASK_ROLE.items():
            key = self._role_provider_keys.get(role)
            if key:
                current = [p for p in self._routing.get(task, []) if p not in {role, key}]
                self._routing[task] = [key] + current

        # Override routing if config specifies preferred providers per task.
        routing_cfg = getattr(config, "routing", {}) or {}
        for task_str, provider_name in routing_cfg.items():
            try:
                task = TaskType(task_str)
                self._routing[task] = [provider_name] + [p for p in self._routing.get(task, []) if p != provider_name]
            except ValueError:
                pass

        self.register_provider("null", self._null, role="fallback", provider_type="null", model="null")

    def _make_role_provider(self, role: str, spec: Dict[str, str], config: Any) -> Optional[str]:
        provider_type = str(spec.get("provider", "") or "").strip().lower()
        model = str(spec.get("model", "") or "").strip()
        if not provider_type or provider_type == "null":
            return None
        key = f"role:{role}:{provider_type}"
        try:
            if provider_type == "ollama":
                provider = OllamaProvider(getattr(config, "ollama_host", "http://localhost:11434"), model or getattr(config, "ollama_model", "llama3.2"), getattr(config, "default_timeout", 60.0))
            elif provider_type == "openai":
                api_key = getattr(config, "openai_api_key", "")
                if not api_key:
                    return None
                provider = OpenAICompatibleProvider(api_key, model or getattr(config, "openai_model", "gpt-4o"), getattr(config, "openai_base_url", "https://api.openai.com/v1"), getattr(config, "default_timeout", 60.0))
            elif provider_type == "gemini":
                api_key = getattr(config, "gemini_api_key", "")
                if not api_key:
                    return None
                provider = GeminiProvider(api_key, model or getattr(config, "gemini_model", "gemini-2.0-flash"), getattr(config, "default_timeout", 60.0))
            elif provider_type == "anthropic":
                api_key = getattr(config, "anthropic_api_key", "")
                if not api_key:
                    return None
                provider = AnthropicProvider(api_key, model or getattr(config, "anthropic_model", "claude-3-5-sonnet-latest"), getattr(config, "default_timeout", 60.0))
            elif provider_type == "llamacpp":
                provider = LlamaCppProvider(getattr(config, "llamacpp_host", "http://localhost:8080"), getattr(config, "default_timeout", 60.0))
            else:
                logger.warning("[LLMRouter] Unknown provider type for role %s: %s", role, provider_type)
                return None
            self.register_provider(key, provider, role=role, provider_type=provider_type, model=model or getattr(provider, "name", ""))
            return key
        except Exception as exc:
            logger.error("[LLMRouter] Failed to create provider for role %s: %s", role, exc)
            return None

    def register_provider(self, name: str, provider: LLMProvider, **meta: Any) -> None:
        self._providers[name] = provider
        self._provider_meta[name] = dict(meta)
        try:
            available = provider.is_available
        except Exception:
            available = False
        logger.debug("[LLMRouter] Registered provider: %s (available=%s)", name, available)

    def route(self, task_type: TaskType) -> LLMProvider:
        """Return the best available provider for this task type.

        Important: if a configured local/cloud provider is currently unavailable
        (for example Ollama is not running), do not return that dead provider just
        because it was first in the profile. Return NullProvider instead so chat,
        doctor, desktop and task flows stay usable without connection-error spam.
        """
        preference = self._routing.get(task_type, list(self._providers.keys()))
        fallback_enabled = bool(getattr(self._config, "model_fallback_enabled", True)) if self._config else True
        first_configured: Optional[LLMProvider] = None
        for name in preference:
            provider = self._providers.get(name)
            if provider is None:
                continue
            first_configured = first_configured or provider
            try:
                if provider.is_available:
                    return provider
            except Exception:
                continue
            if not fallback_enabled:
                # Strict mode means "use configured provider even if it errors".
                return provider if provider is not None else self._null

        if fallback_enabled:
            for name, provider in self._providers.items():
                if name == "null":
                    continue
                try:
                    if provider.is_available:
                        return provider
                except Exception:
                    continue
            return self._null

        return first_configured or self._null

    def available_providers(self) -> List[str]:
        result = []
        for name, p in self._providers.items():
            try:
                if p.is_available:
                    result.append(name)
            except Exception:
                pass
        if not result:
            result.append("null")
        return result

    def status(self, refresh: bool = False) -> Dict[str, Any]:
        """Return current model profile, role routing and provider health."""
        providers = []
        for key, provider in self._providers.items():
            if refresh and hasattr(provider, "_available"):
                try:
                    setattr(provider, "_available", None)
                except Exception:
                    pass
            try:
                available = bool(provider.is_available)
            except Exception:
                available = False
            meta = dict(self._provider_meta.get(key, {}))
            providers.append({
                "key": key,
                "name": provider.name,
                "available": available,
                "role": meta.get("role", ""),
                "provider_type": meta.get("provider_type", ""),
                "model": meta.get("model", provider.name),
            })
        roles = {}
        for role, key in self._role_provider_keys.items():
            provider = self._providers.get(key)
            roles[role] = {
                "provider_key": key,
                "provider": provider.name if provider else key,
                "available": bool(provider.is_available) if provider else False,
            }
        routes = {task.value: [p for p in prefs] for task, prefs in self._routing.items()}
        return {
            "schema": "model_router_v10",
            "profile": self._profile_name,
            "roles": roles,
            "providers": providers,
            "routes": routes,
            "available": self.available_providers(),
        }

    async def generate(self, prompt: str,
                       task_type: TaskType = TaskType.SIMPLE_CHAT,
                       system: str = "",
                       **kwargs) -> str:
        provider = self.route(task_type)
        logger.debug("[LLMRouter] %s → %s", task_type.value, provider.name)
        return await provider.generate(prompt, system=system, **kwargs)

    async def imagine(self, seed: str, context: dict,
                      task_type: TaskType = TaskType.CREATIVE_IMAGINATION) -> List[dict]:
        provider = self.route(task_type)
        logger.debug("[LLMRouter] imagine → %s", provider.name)
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
