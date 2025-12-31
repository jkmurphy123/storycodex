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
- STORYCODEX_MODEL
