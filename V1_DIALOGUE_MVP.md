# V1 Dialogue MVP

Implemented: real LLM dialogue loop with memory retrieval.

## What changed

- `modules/tier3_reasoning/llm/llm_module.py` is now the dialogue coordinator.
- `memory_module.py` now returns `dialogue_context` for LLM turns.
- User messages and assistant responses are stored into memory.
- Recent dialogue history is persisted as `dialogue_history`.
- Added terminal test mode: `python main.py --chat`.

## Runtime flow

```text
user_utterance
  -> memory_request: dialogue_context
  -> memory_retrieved
  -> LLM prompt assembly
  -> LLMRouter.generate
  -> response_generated
  -> dialogue_turn_completed
  -> memory persistence
```

## Recommended local model

For Ollama:

```bash
ollama serve
ollama pull llama3.1:8b
# or for coding-heavy work:
ollama pull qwen2.5-coder:7b
```

`.env` example:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

## Test

```bash
python main.py --chat
```

Ask two related questions. The second answer should use recent dialogue and retrieved memory.
