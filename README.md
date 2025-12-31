# storycodex

StoryCodex provides a small CLI for initializing a workspace and applying seed overrides.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

```bash
storycodex init --root .
storycodex seed apply --root .
storycodex plan spine --root .
```

Environment variables:
- OPENAI_API_KEY
- STORYCODEX_BASE_URL
- STORYCODEX_BACKEND
- STORYCODEX_MODEL
- STORYCODEX_TIMEOUT_SECONDS

Ollama example:
```bash
export STORYCODEX_BASE_URL="http://localhost:11434"
export STORYCODEX_MODEL="gemma3:4b"
export STORYCODEX_BACKEND="ollama"
```

OpenAI-compatible example:
```bash
export STORYCODEX_BASE_URL="http://localhost:8000/v1"
export STORYCODEX_MODEL="your-model"
export STORYCODEX_BACKEND="openai"
```

Default backend is `auto`, which probes `{base_url}/v1/models` and falls back to Ollama.
