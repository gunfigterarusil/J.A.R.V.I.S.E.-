# V10 — Modular Model/API Router MVP

Status: ✅ MVP Done

V10 turns JAV from a single-model assistant into a role-based model platform. The brain still calls `kernel.llm_router.generate(...)`, but the router now maps each cognitive task to a model role.

## Model roles

- `fast` — quick chat, lightweight responses, summaries.
- `reason` — deeper reasoning, imagination, analysis.
- `code` — code repair, patch proposals, project debugging.
- `critic` — review/checker role for future verifier loops.
- `vision` — visual/screen reasoning model role.
- `embedding` — semantic memory / vector model role.
- `action` — action planning, GUI/task-chain planning.

## Profiles

Set in `.env`:

```env
MODEL_PROFILE=offline
```

Built-in profiles:

- `offline` — local-first Ollama/Qwen/Llama/LLaVA style setup.
- `balanced` — local fast/code plus Gemini for reasoning/vision/critic if configured.
- `power` — cloud-heavy OpenAI/Anthropic style setup.
- `code` — code-focused local profile.
- `voice_companion` — fast local profile for daily voice assistant use.
- `custom` — use explicit role overrides.

## Role overrides

Every role can be pointed to a separate provider/model:

```env
MODEL_PROFILE=custom
MODEL_FAST_PROVIDER=ollama
MODEL_FAST_NAME=qwen2.5:7b
MODEL_REASON_PROVIDER=ollama
MODEL_REASON_NAME=llama3.1:8b
MODEL_CODE_PROVIDER=ollama
MODEL_CODE_NAME=qwen2.5-coder:7b
MODEL_CRITIC_PROVIDER=gemini
MODEL_CRITIC_NAME=gemini-2.0-flash
MODEL_VISION_PROVIDER=ollama
MODEL_VISION_NAME=llava
MODEL_ACTION_PROVIDER=ollama
MODEL_ACTION_NAME=qwen2.5:7b
```

Supported provider names in V10 MVP:

```text
ollama
openai
gemini
anthropic
llamacpp
null
```

## Commands

In chat or desktop:

```text
/models
/model-status
/model-health
/model-profile
```

Natural language:

```text
покажи статус моделей
яка модель активна
model health
```

## Safety

V10 only changes which model thinks about each role. It does not bypass V7 safety. File writes, shell, GUI actions and repair application still use the existing permission/firewall/approval flow.

## Next improvements

- Add real embedding provider calls for vector memory instead of only local hashed vectors.
- Add vision model calls in V9.6 screen understanding when configured.
- Add critic model verification before applying patches/actions.
- Add live profile switching without restart.
- Add model benchmark/self-test panel in desktop UI.
