"""scripts/model_discovery.py — discover available AI models across providers.

V18.2 Model Discovery + Provider Catalog
- Ollama local models via /api/tags
- OpenAI-compatible /v1/models
- NVIDIA NIM preset (OpenAI-compatible base URL) + fallback catalog
- Anthropic models API
- Gemini models API
- manual/custom fallback helpers

This module is intentionally dependency-light: it uses urllib so doctor/catalog can
run before optional SDKs are installed. It never sends prompts; it only lists model
metadata where providers expose a listing endpoint.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ROLES = ["fast", "reason", "code", "critic", "vision", "embedding", "action"]

NVIDIA_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Small curated fallback catalog. NVIDIA's hosted catalog changes over time, so
# keep these as suggestions only. Users can still enter any model ID manually.
NVIDIA_FALLBACK_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "qwen/qwen2.5-7b-instruct",
    "qwen/qwen2.5-coder-7b-instruct",
    "qwen/qwen2.5-coder-32b-instruct",
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3.5-397b-a17b",
    "nvidia/llama-3.2-nv-embedqa-1b-v2",
]

OPENAI_FALLBACK_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1",
    "text-embedding-3-small",
]

ANTHROPIC_FALLBACK_MODELS = [
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-sonnet-4-5",
]

GEMINI_FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


@dataclass
class DiscoveredModel:
    provider: str
    model_id: str
    display_name: str = ""
    source: str = "api"  # api/local/catalog/manual
    available: bool = False
    model_type: str = "text"  # text/code/vision/embedding/audio
    suggested_roles: List[str] = field(default_factory=list)
    context_window: Optional[int] = None
    error: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def env_path(path: Path | None = None) -> Path:
    return path or (_root() / ".env")


def read_env(path: Path | None = None) -> Dict[str, str]:
    result: Dict[str, str] = {}
    p = env_path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            result[k.strip()] = v.strip()
    # Runtime env overrides .env for diagnostics.
    keys = [
        "OLLAMA_HOST", "OPENAI_BASE_URL", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY", "LLAMACPP_HOST", "NVIDIA_NIM_API_KEY",
        "NVIDIA_NIM_BASE_URL", "MODEL_PROFILE",
    ]
    keys += [f"MODEL_{r.upper()}_{suffix}" for r in ROLES for suffix in ("PROVIDER", "NAME")]
    for k in keys:
        if os.environ.get(k):
            result[k] = os.environ[k]
    return result


def write_env_updates(updates: Dict[str, str], path: Path | None = None) -> Path:
    p = env_path(path)
    existing = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
    update_keys = set(updates)
    kept: List[str] = []
    for line in existing:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.split("=", 1)[0].strip()
            if key in update_keys:
                continue
        kept.append(line)
    if kept and kept[-1] != "":
        kept.append("")
    kept.append("# === JAV Model Discovery / Catalog ===")
    for k in sorted(updates):
        kept.append(f"{k}={updates[k]}")
        os.environ[k] = updates[k]
    p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return p


def _http_json(url: str, headers: Dict[str, str] | None = None, timeout: float = 8.0) -> Tuple[bool, object, str]:
    try:
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return True, json.loads(raw), ""
    except Exception as exc:
        return False, None, str(exc)


def infer_model_type(model_id: str) -> str:
    m = (model_id or "").lower()
    if any(x in m for x in ("embed", "embedding", "nomic", "bge", "e5")):
        return "embedding"
    if any(x in m for x in ("coder", "code", "deepseek-coder", "codestral")):
        return "code"
    if any(x in m for x in ("vision", "vl", "llava", "moondream", "multimodal", "pixtral", "qwen2-vl", "qwen-vl")):
        return "vision"
    return "text"


def suggest_roles(model_id: str, provider: str = "") -> List[str]:
    m = (model_id or "").lower()
    typ = infer_model_type(model_id)
    roles: List[str] = []
    if typ == "embedding":
        roles.append("embedding")
    elif typ == "vision":
        roles.append("vision")
    elif typ == "code":
        roles += ["code", "action"]
    else:
        if any(x in m for x in ("70b", "122b", "405b", "reason", "nemotron", "sonnet", "opus", "pro")):
            roles += ["reason", "critic"]
        if any(x in m for x in ("mini", "3b", "7b", "8b", "flash", "haiku", "small")):
            roles += ["fast", "action"]
        if not roles:
            roles += ["fast", "reason"]
    # Add critic hint for judge/nemotron, action hint for instruct/tool models.
    if any(x in m for x in ("critic", "judge", "nemotron")) and "critic" not in roles:
        roles.append("critic")
    if any(x in m for x in ("instruct", "chat", "tool")) and "action" not in roles and typ == "text":
        roles.append("action")
    # Deduplicate preserving order.
    out: List[str] = []
    for r in roles:
        if r in ROLES and r not in out:
            out.append(r)
    return out


def _model(provider: str, model_id: str, *, source: str, available: bool, error: str = "", display_name: str = "") -> DiscoveredModel:
    return DiscoveredModel(
        provider=provider,
        model_id=model_id,
        display_name=display_name or model_id,
        source=source,
        available=available,
        model_type=infer_model_type(model_id),
        suggested_roles=suggest_roles(model_id, provider),
        error=error,
    )


def discover_ollama(env: Dict[str, str]) -> List[DiscoveredModel]:
    host = (env.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    ok, data, err = _http_json(f"{host}/api/tags", timeout=3.0)
    if not ok or not isinstance(data, dict):
        return [DiscoveredModel(provider="ollama", model_id="", source="local", available=False, error=f"Ollama not reachable at {host}: {err}")]
    models: List[DiscoveredModel] = []
    for item in data.get("models", []) or []:
        mid = str(item.get("name") or item.get("model") or "").strip()
        if mid:
            models.append(_model("ollama", mid, source="local", available=True))
    return sorted(models, key=lambda x: x.model_id)


def discover_openai_compatible(env: Dict[str, str], *, provider: str = "openai", base_url_key: str = "OPENAI_BASE_URL", key_name: str = "OPENAI_API_KEY") -> List[DiscoveredModel]:
    base = (env.get(base_url_key) or "https://api.openai.com/v1").rstrip("/")
    key = env.get(key_name) or ""
    if not key:
        fallback = OPENAI_FALLBACK_MODELS if provider == "openai" else []
        return [_model(provider, m, source="catalog", available=False, error=f"Set {key_name} to test/discover") for m in fallback] or [DiscoveredModel(provider=provider, model_id="", source="api", available=False, error=f"Set {key_name}")]
    headers = {"Authorization": f"Bearer {key}"}
    ok, data, err = _http_json(f"{base}/models", headers=headers, timeout=8.0)
    models: List[DiscoveredModel] = []
    if ok and isinstance(data, dict):
        for item in data.get("data", []) or []:
            mid = str(item.get("id") or item.get("model") or "").strip()
            if mid:
                models.append(_model(provider, mid, source="api", available=True))
    if models:
        return sorted(models, key=lambda x: x.model_id)
    return [DiscoveredModel(provider=provider, model_id="", source="api", available=False, error=f"/models unavailable at {base}: {err or 'empty response'}")]


def discover_nvidia(env: Dict[str, str]) -> List[DiscoveredModel]:
    # Prefer NVIDIA_NIM_API_KEY, fallback to OPENAI_API_KEY only if base URL is NVIDIA.
    key = env.get("NVIDIA_NIM_API_KEY") or (env.get("OPENAI_API_KEY") if "nvidia" in (env.get("OPENAI_BASE_URL") or "").lower() else "") or ""
    base = (env.get("NVIDIA_NIM_BASE_URL") or NVIDIA_DEFAULT_BASE_URL).rstrip("/")
    if not key:
        return [_model("nvidia", m, source="catalog", available=False, error="Set NVIDIA_NIM_API_KEY") for m in NVIDIA_FALLBACK_MODELS]
    items = discover_openai_compatible({"OPENAI_BASE_URL": base, "OPENAI_API_KEY": key}, provider="nvidia", base_url_key="OPENAI_BASE_URL", key_name="OPENAI_API_KEY")
    if len(items) == 1 and not items[0].model_id:
        # Add fallback catalog with API-key-present status but not verified.
        return [_model("nvidia", m, source="catalog", available=False, error=items[0].error) for m in NVIDIA_FALLBACK_MODELS]
    return items


def discover_anthropic(env: Dict[str, str]) -> List[DiscoveredModel]:
    key = env.get("ANTHROPIC_API_KEY") or ""
    if not key:
        return [_model("anthropic", m, source="catalog", available=False, error="Set ANTHROPIC_API_KEY") for m in ANTHROPIC_FALLBACK_MODELS]
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    ok, data, err = _http_json("https://api.anthropic.com/v1/models", headers=headers, timeout=8.0)
    models: List[DiscoveredModel] = []
    if ok and isinstance(data, dict):
        for item in data.get("data", []) or []:
            mid = str(item.get("id") or "").strip()
            if mid:
                models.append(_model("anthropic", mid, source="api", available=True))
    return sorted(models, key=lambda x: x.model_id) if models else [_model("anthropic", m, source="catalog", available=False, error=err or "models API returned no models") for m in ANTHROPIC_FALLBACK_MODELS]


def discover_gemini(env: Dict[str, str]) -> List[DiscoveredModel]:
    key = env.get("GEMINI_API_KEY") or ""
    if not key:
        return [_model("gemini", m, source="catalog", available=False, error="Set GEMINI_API_KEY") for m in GEMINI_FALLBACK_MODELS]
    url = "https://generativelanguage.googleapis.com/v1beta/models?" + urllib.parse.urlencode({"key": key})
    ok, data, err = _http_json(url, timeout=8.0)
    models: List[DiscoveredModel] = []
    if ok and isinstance(data, dict):
        for item in data.get("models", []) or []:
            name = str(item.get("name") or "").strip()
            mid = name.split("/", 1)[1] if name.startswith("models/") else name
            methods = item.get("supportedGenerationMethods") or []
            if mid and (not methods or "generateContent" in methods or "embedContent" in methods):
                models.append(_model("gemini", mid, source="api", available=True, display_name=item.get("displayName") or mid))
    return sorted(models, key=lambda x: x.model_id) if models else [_model("gemini", m, source="catalog", available=False, error=err or "models API returned no models") for m in GEMINI_FALLBACK_MODELS]


def discover_llamacpp(env: Dict[str, str]) -> List[DiscoveredModel]:
    host = (env.get("LLAMACPP_HOST") or "http://localhost:8080").rstrip("/")
    ok, data, err = _http_json(f"{host}/props", timeout=3.0)
    if ok and isinstance(data, dict):
        mid = str(data.get("model_path") or data.get("model") or "server-default")
        mid = Path(mid).name if mid else "server-default"
        return [_model("llamacpp", mid, source="api", available=True)]
    return [DiscoveredModel(provider="llamacpp", model_id="server-default", source="manual", available=False, error=f"llama.cpp server not reachable at {host}: {err}")]


def discover_models(providers: Iterable[str] | None = None, env: Dict[str, str] | None = None) -> List[DiscoveredModel]:
    env = env or read_env()
    providers = [p.lower().strip() for p in (providers or ["ollama", "nvidia", "openai", "anthropic", "gemini", "llamacpp"]) if p]
    out: List[DiscoveredModel] = []
    for p in providers:
        try:
            if p == "ollama":
                out.extend(discover_ollama(env))
            elif p in {"openai", "openai_compatible"}:
                out.extend(discover_openai_compatible(env, provider="openai"))
            elif p in {"nvidia", "nvidia_nim", "nim"}:
                out.extend(discover_nvidia(env))
            elif p == "anthropic":
                out.extend(discover_anthropic(env))
            elif p == "gemini":
                out.extend(discover_gemini(env))
            elif p in {"llamacpp", "llama.cpp"}:
                out.extend(discover_llamacpp(env))
        except Exception as exc:
            out.append(DiscoveredModel(provider=p, model_id="", source="api", available=False, error=repr(exc)))
    return out


def format_catalog(models: List[DiscoveredModel]) -> str:
    lines = ["JAV Model Discovery Catalog", "=" * 31]
    if not models:
        return "\n".join(lines + ["No models discovered."])
    lines.append(f"{'Provider':<10} {'Status':<8} {'Type':<9} {'Roles':<26} Model")
    lines.append("-" * 96)
    for m in models:
        status = "ready" if m.available else ("catalog" if m.source == "catalog" else "warn")
        roles = ",".join(m.suggested_roles) or "-"
        model = m.model_id or "(none)"
        if m.error and not m.available:
            model += f"  — {m.error[:90]}"
        lines.append(f"{m.provider:<10} {status:<8} {m.model_type:<9} {roles:<26} {model}")
    return "\n".join(lines)


def assign_role(role: str, provider: str, model_id: str, env_file: Path | None = None) -> Path:
    role = role.lower().strip()
    if role not in ROLES:
        raise ValueError(f"Unknown role '{role}'. Expected one of: {', '.join(ROLES)}")
    provider = provider.lower().replace("-", "_").strip()
    # Router accepts nvidia as provider after V18.2.
    updates = {
        "MODEL_PROFILE": "custom",
        f"MODEL_{role.upper()}_PROVIDER": provider,
        f"MODEL_{role.upper()}_NAME": model_id.strip(),
    }
    # Convenience: NVIDIA role assignment also fills OpenAI-compatible URL fields.
    if provider in {"nvidia", "nvidia_nim", "nim"}:
        updates.setdefault("NVIDIA_NIM_BASE_URL", NVIDIA_DEFAULT_BASE_URL)
    return write_env_updates(updates, env_file)


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "assign":
        if len(argv) < 4:
            print("Usage: python scripts/model_discovery.py assign <role> <provider> <model_id>")
            return 2
        path = assign_role(argv[1], argv[2], " ".join(argv[3:]))
        print(f"Saved role assignment to {path}")
        return 0
    providers = None
    if argv:
        providers = [x.strip() for x in " ".join(argv).replace(",", " ").split() if x.strip()]
    models = discover_models(providers=providers)
    print(format_catalog(models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
