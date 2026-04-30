# storycodex

StoryCodex plans, drafts, and checks story structure. WorldCodex owns canonical
world-building data such as settings, characters, factions, relationships, and
history.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

```bash
storycodex init --root .
storycodex seed apply --root .
export STORYCODEX_WORLDCODEX_WORLD=titan-osa
export STORYCODEX_WORLDCODEX_CLI=world
storycodex plan spine --root .
storycodex plan scenes --root .
storycodex plan beats --root . --scene 1
storycodex build-context --root . --scene 1
storycodex write scene --root . --scene 1
storycodex check continuity --root . --scene 1
storycodex propose-world-patch --root . --scene 1
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
- STORYCODEX_WORLDCODEX_WORLD
- STORYCODEX_WORLDCODEX_CLI
- STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS

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
- `storycodex plan scenes --root . --world "$STORYCODEX_WORLDCODEX_WORLD" --character character.example --location place.example`
- When WorldCodex context is available, scene `setting.location_id` and `cast` should use WorldCodex atom IDs.

Beats planning:
- `storycodex plan beats --root . --scene 1`
- Requires `seed apply` and `plan scenes`
- Scene plan beats_ref points to the beats file produced here.

Context building:
- `storycodex build-context --root . --scene 1`
- Compiles Ring A/B/C context for drafting from plans and beats.
- `storycodex build-context --root . --scene 1 --world "$STORYCODEX_WORLDCODEX_WORLD"`
- When WorldCodex is configured, Ring B setting/cast and Ring C relevant facts/open threads are derived from WorldCodex exports.
- Optional local artifacts remain only for story-local continuity locks/facts and chapter state under `artifacts/story_state/`; they are not canonical world building.

WorldCodex boundary:
- `storycodex world export --root . --context story-context` caches a WorldCodex export under `artifacts/worldcodex/`.
- `STORYCODEX_WORLDCODEX_WORLD` should point to the WorldCodex world id or path.
- StoryCodex does not author canonical places, characters, factions, relationships, conflicts, or history.
- WorldCodex is the only tool that applies world/canon changes.

Writing:
- `storycodex write scene --root . --scene 1`
- Uses ONLY the context packet for the scene.
- Produces a draft; continuity checks and polishing come later.

Continuity check:
- `storycodex check continuity --root . --scene 1`
- Produces `continuity_report.json` and `patch.json` without modifying prose.
- The patch file is a prose repair plan only; it is not a WorldCodex canon patch.

WorldCodex patch proposal:
- `storycodex propose-world-patch --root . --scene 1`
- Reads the scene context, draft/final prose, and continuity report, then saves `out/scenes/scene_001.worldcodex_patch.json`.
- Emits `worldcodex.patch.v1` for durable canon changes only. StoryCodex does not apply these patches.
- Add `--preview --world <world-id-or-path>` to validate and preview the proposal through the WorldCodex CLI.
