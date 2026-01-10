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
storycodex plan scenes --root .
storycodex plan beats --root . --scene 1
storycodex build-context --root . --scene 1
storycodex write scene --root . --scene 1
storycodex check continuity --root . --scene 1
```

Seed overrides:
- `seeds/story_overrides.json` merges into `artifacts/defaults/story_spec.json` -> `artifacts/inputs/story_spec.json`.
- Optional `seeds/plot_overrides.json` merges into `artifacts/defaults/plot_intent.json` -> `artifacts/inputs/plot_intent.json`.
- Plot intent influences plan spine/scenes/beats and build-context when present.
- Optional `seeds/style_profile.json` is read by build-context to extend Ring A tone/style_rules/constraints.

Style profile example:
```json
{
  "profile_id": "noir",
  "profile_name": "Noir",
  "intent": "Bleak, taut noir focus.",
  "tone": ["noir"],
  "syntax": {"sentence_rhythm": "Short punches.", "paragraphing": "One paragraph per beat."},
  "scene_rules": {"must_include": ["shadow"], "must_not": []},
  "output_controls": {"metaphor_density": "low", "exposition_throttle": "tight", "violence": "medium", "gore": "low"}
}
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

Scenes planning:
- `storycodex plan scenes --root .`
- `storycodex plan scenes --root . --chapter 2`
- Cast and location_id may be placeholders until character/world steps exist.

Beats planning:
- `storycodex plan beats --root . --scene 1`
- Requires `seed apply` and `plan scenes`
- Scene plan beats_ref points to the beats file produced here.

Context building:
- `storycodex build-context --root . --scene 1`
- Compiles Ring A/B/C context for drafting from plans and beats.
- Optional artifacts: continuity locks/facts, world/characters at tiny/medium/full, character state.

Writing:
- `storycodex write scene --root . --scene 1`
- Uses ONLY the context packet for the scene.
- Produces a draft; continuity checks and polishing come later.

Continuity check:
- `storycodex check continuity --root . --scene 1`
- Produces `continuity_report.json` and `patch.json` without modifying prose.
