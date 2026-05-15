"""scripts/model_setup.py — model provider diagnostics and setup helpers.

This module is safe to run without API keys or Ollama. It never sends prompts to
cloud providers; it only checks whether configuration exists and whether local
Ollama is reachable / has the requested models pulled.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

ROLES = ["fast", "reason", "code", "critic", "vision", "embedding", "action"]

DEFAULT_PROFILE_MODELS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "offline": {
        "fast": ("ollama", "qwen2.5:7b"),
        "reason": ("ollama", "llama3.1:8b"),
        "code": ("ollama", "qwen2.5-coder:7b"),
        "critic": ("ollama", "llama3.1:8b"),
        "vision": ("ollama", "llava"),
        "embedding": ("ollama", "nomic-embed-text"),
        "action": ("ollama", "qwen2.5:7b"),
    },
    "low_ram": {
        "fast": ("ollama", "qwen2.5:3b"),
        "reason": ("ollama", "llama3.2:3b"),
        "code": ("ollama", "qwen2.5-coder:3b"),
        "critic": ("ollama", "llama3.2:3b"),
        "vision": ("ollama", "llava"),
        "embedding": ("ollama", "nomic-embed-text"),
        "action": ("ollama", "qwen2.5:3b"),
    },
    "hybrid": {
        "fast": ("ollama", "qwen2.5:7b"),
        "reason": ("gemini", "gemini-2.0-flash"),
        "code": ("ollama", "qwen2.5-coder:7b"),
        "critic": ("gemini", "gemini-2.0-flash"),
        "vision": ("gemini", "gemini-2.0-flash"),
        "embedding": ("ollama", "nomic-embed-text"),
        "action": ("ollama", "qwen2.5:7b"),
    },
    "cloud": {
        "fast": ("openai", "gpt-4o-mini"),
        "reason": ("openai", "gpt-4o"),
        "code": ("openai", "gpt-4o"),
        "critic": ("anthropic", "claude-3-5-sonnet-latest"),
        "vision": ("openai", "gpt-4o"),
        "embedding": ("openai", "text-embedding-3-small"),
        "action": ("openai", "gpt-4o-mini"),
    },
    "code": {
        "fast": ("ollama", "qwen2.5-coder:7b"),
        "reason": ("ollama", "qwen2.5-coder:14b"),
        "code": ("ollama", "qwen2.5-coder:14b"),
        "critic": ("ollama", "qwen2.5-coder:14b"),
        "vision": ("ollama", "llava"),
        "embedding": ("ollama", "nomic-embed-text"),
        "action": ("ollama", "qwen2.5-coder:7b"),
    },
    "voice_companion": {
        "fast": ("ollama", "qwen2.5:3b"),
        "reason": ("ollama", "qwen2.5:7b"),
        "code": ("ollama", "qwen2.5-coder:7b"),
        "critic": ("ollama", "qwen2.5:7b"),
        "vision": ("ollama", "llava"),
        "embedding": ("ollama", "nomic-embed-text"),
        "action": ("ollama", "qwen2.5:3b"),
    },
}


def read_env_file(path: Path | None = None) -> Dict[str, str]:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    env_path = path or (root / ".env")
    data: Dict[str, str] = {}
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def effective_env() -> Dict[str, str]:
    data = read_env_file()
    for k, v in os.environ.items():
        if k.startswith("MODEL_") or k in {"OLLAMA_HOST", "OPENAI_API_KEY", "OPENAI_BASE_URL", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_NIM_API_KEY", "NVIDIA_NIM_BASE_URL"}:
            data[k] = v
    return data


def get_role_config(env: Dict[str, str] | None = None) -> Dict[str, Tuple[str, str]]:
    env = env or effective_env()
    profile = (env.get("MODEL_PROFILE") or "offline").strip().lower()
    base = dict(DEFAULT_PROFILE_MODELS.get(profile, DEFAULT_PROFILE_MODELS["offline"]))
    for role in ROLES:
        p = env.get(f"MODEL_{role.upper()}_PROVIDER", "").strip().lower()
        m = env.get(f"MODEL_{role.upper()}_NAME", "").strip()
        bp, bm = base.get(role, ("ollama", ""))
        base[role] = (p or bp, m or bm)
    return base


def list_ollama_models(host: str = "http://localhost:11434", timeout: float = 2.5) -> Tuple[bool, List[str], str]:
    host = (host or "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        names = []
        for item in data.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
        return True, sorted(names), ""
    except Exception as exc:
        return False, [], f"Ollama not reachable at {host}: {exc}"


def model_matches(wanted: str, installed: List[str]) -> bool:
    wanted = (wanted or "").strip()
    if not wanted:
        return True
    if wanted in installed:
        return True
    wanted_base = wanted.split(":", 1)[0]
    return any(x.split(":", 1)[0] == wanted_base for x in installed)


def ollama_pull_commands(role_config: Dict[str, Tuple[str, str]] | None = None, installed: List[str] | None = None) -> List[str]:
    role_config = role_config or get_role_config()
    installed = installed or []
    commands: List[str] = []
    seen = set()
    for _role, (provider, model) in role_config.items():
        if provider != "ollama" or not model:
            continue
        if model_matches(model, installed):
            continue
        if model in seen:
            continue
        seen.add(model)
        commands.append(f"ollama pull {model}")
    return commands


def diagnose_models() -> Dict[str, object]:
    env = effective_env()
    profile = (env.get("MODEL_PROFILE") or "offline").strip().lower()
    host = env.get("OLLAMA_HOST") or "http://localhost:11434"
    role_config = get_role_config(env)
    ok, installed, ollama_error = list_ollama_models(host)
    roles = []
    for role, (provider, model) in role_config.items():
        status = "unknown"
        detail = ""
        if provider == "ollama":
            if not ok:
                status = "unavailable"
                detail = ollama_error
            elif model_matches(model, installed):
                status = "ok"
                detail = "installed"
            else:
                status = "missing_model"
                detail = f"Run: ollama pull {model}"
        elif provider in {"nvidia", "nvidia_nim", "nim"}:
            status = "configured" if env.get("NVIDIA_NIM_API_KEY") else "missing_key"
            detail = "NVIDIA_NIM_API_KEY present" if status == "configured" else "Set NVIDIA_NIM_API_KEY"
        elif provider == "gemini":
            status = "configured" if env.get("GEMINI_API_KEY") else "missing_key"
            detail = "GEMINI_API_KEY present" if status == "configured" else "Set GEMINI_API_KEY"
        elif provider == "openai":
            status = "configured" if env.get("OPENAI_API_KEY") else "missing_key"
            detail = "OPENAI_API_KEY present" if status == "configured" else "Set OPENAI_API_KEY"
        elif provider == "anthropic":
            status = "configured" if env.get("ANTHROPIC_API_KEY") else "missing_key"
            detail = "ANTHROPIC_API_KEY present" if status == "configured" else "Set ANTHROPIC_API_KEY"
        elif provider == "llamacpp":
            status = "configured"
            detail = "llama.cpp server URL configured"
        elif provider == "null":
            status = "disabled"
            detail = "role disabled"
        else:
            status = "unknown_provider"
            detail = f"Unknown provider: {provider}"
        roles.append({"role": role, "provider": provider, "model": model, "status": status, "detail": detail})
    return {
        "profile": profile,
        "ollama_host": host,
        "ollama_reachable": ok,
        "ollama_error": ollama_error,
        "ollama_models": installed,
        "roles": roles,
        "pull_commands": ollama_pull_commands(role_config, installed),
    }


def format_model_report() -> str:
    d = diagnose_models()
    lines = ["JAV Model Setup Report", "=" * 24]
    lines.append(f"Profile: {d['profile']}")
    lines.append(f"Ollama: {'OK' if d['ollama_reachable'] else 'WARN'} — {d['ollama_host']}")
    if d.get("ollama_error"):
        lines.append(f"  {d['ollama_error']}")
    if d.get("ollama_models"):
        lines.append("Installed Ollama models:")
        for m in d["ollama_models"]:
            lines.append(f"  - {m}")
    lines.append("")
    lines.append("Roles:")
    for r in d["roles"]:
        lines.append(f"  - {r['role']:<9} {r['provider']}/{r['model']}  [{r['status']}] {r['detail']}")
    pulls = d.get("pull_commands") or []
    if pulls:
        lines.append("")
        lines.append("Missing Ollama models — run:")
        for cmd in pulls:
            lines.append(f"  {cmd}")
    return "\n".join(lines)


def main() -> int:
    print(format_model_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
