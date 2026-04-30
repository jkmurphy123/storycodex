# WorldCodex Alignment Plan

Date: 2026-04-30

## Goal

Adapt StoryCodex so it focuses on story structure, scene planning, drafting, and revision while relying on WorldCodex for all canonical world data.

StoryCodex should:

- Plan plot spines, chapters, scenes, and beats.
- Build scene context packets from story structure plus WorldCodex exports.
- Draft scenes using only the context packet.
- Check scene continuity against story structure and WorldCodex-derived locks/facts.
- Optionally propose WorldCodex patches when drafted story events should become canon.

StoryCodex should not:

- Invent or maintain canonical settings, characters, factions, relationships, or world history.
- Treat local `artifacts/world/*.json` or `artifacts/characters/*.json` as the source of truth.
- Merge world updates directly.
- Own character/world state except for story-local arc state needed for scene execution.

## Current Shape

StoryCodex is already mostly a story-structure tool:

- `plan_spine.py` creates act/chapter/scene structure.
- `plan_scenes.py` creates scene plans with setting, cast, goals, stakes.
- `plan_beats.py` creates beat-level scene structure.
- `build_context.py` compiles Ring A/B/C scene context.
- `write_scene.py` writes prose from a context packet.
- `check_continuity.py` checks beat coverage, locks, POV, and tense.
- `merge.py` and `seed_apply.py` handle local seed/config merges.

The main alignment issue is that `build_context.py` currently reads optional local world and character artifacts:

- `artifacts/world/tiny.json`
- `artifacts/world/medium.json`
- `artifacts/world/full.json`
- `artifacts/characters/tiny.json`
- `artifacts/characters/medium.json`
- `artifacts/characters/full.json`
- `artifacts/characters/state/chNN.json`
- `artifacts/continuity/locks.json`
- `artifacts/continuity/facts.json`

Those local world/character/fact artifacts should either become WorldCodex export caches or disappear from the active path.

## Target Architecture

WorldCodex remains the canonical world layer.

StoryCodex becomes a story-structure client:

```text
WorldCodex world
  -> world export <world> story-context --character ... --location ... --faction ...
  -> StoryCodex plans plot spine/scenes/beats
  -> StoryCodex builds scene context packets from story structure + WorldCodex context
  -> StoryCodex writes scenes
  -> StoryCodex checks story continuity
  -> optional: StoryCodex proposes worldcodex.patch.v1 updates for durable canon changes
```

WorldCodex context types that matter:

- `story-context` for scene/character-focused prose drafting.
- `character-context` for character arc and voice support.
- `location-context` for scene settings.
- `world-bible` for broad project initialization or reference.

Initial integration should use a small CLI-backed `WorldCodexClient`, matching the approach used in WorldWeaver. A later Python package integration can sit behind the same interface.

## Ownership Boundary

### StoryCodex Owns

- Story spec: title, logline, genre, tone, POV, tense, target length.
- Plot intent: central question, core arc, themes, act shape, ending constraints.
- Plot spine: acts, chapters, scene IDs.
- Scene plans: scene goals, story stakes, required cast IDs, required setting ID.
- Scene beats: narrative beat order and scene-level dramatic function.
- Drafts, continuity reports, and prose patch plans.
- Story-local character arc state, only when it is explicitly story-local and not canon.

### WorldCodex Owns

- Settings and locations.
- Characters and reusable character facts.
- Factions, organizations, cultures, technologies, artifacts, conflicts.
- Relationships between world atoms.
- Timeline and historical/canon events.
- Canon tiers, deprecation, conflict resolution, patch validation, preview, and application.

## Code Change Inventory

### Add

- `storycodex/worldcodex_client.py`
  - CLI-backed adapter with:
    - `export_context(context_type, *, location_id="", character_id="", faction_id="", tag="", canon_tier="")`
    - `validate_patch(patch_path)`
    - `preview_patch(patch_path)`
    - optional `apply_patch(patch_path)`
  - Fake runner support for tests.

- WorldCodex settings, likely environment variables:
  - `STORYCODEX_WORLDCODEX_WORLD`
  - `STORYCODEX_WORLDCODEX_CLI`
  - `STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS`

- Context normalization helpers:
  - Convert WorldCodex atoms into the current scene context packet shape.
  - Resolve scene `location_id` and `cast` entries to WorldCodex atom IDs.
  - Derive continuity locks/facts from WorldCodex context without local world ownership.

- Optional patch proposal service:
  - `storycodex/worldcodex_patch_proposal.py`
  - Emits `worldcodex.patch.v1` for durable story events introduced in drafted scenes.

### Adapt

- `storycodex/defaults.py`
  - Add optional WorldCodex binding fields to story defaults or plot intent:
    - world ID
    - protagonist atom ID
    - primary location/faction IDs
    - canon tier filters
  - Keep this as story selection metadata, not world canon.

- `storycodex/seed_apply.py`
  - Allow seed overrides to specify WorldCodex atom IDs.
  - Validate that StoryCodex seeds do not define canonical character/location bodies.

- `storycodex/plan_spine.py`
  - Mostly keep as-is.
  - Optionally include a compact WorldCodex `story-context` or `world-bible` export so plot structure respects available canon.
  - The spine should still be story structure, not world building.

- `storycodex/plan_scenes.py`
  - Replace placeholder location/cast generation with WorldCodex-aware selection.
  - Scene plan `setting.location_id` should be a WorldCodex place atom ID when known.
  - Scene plan `cast` should prefer WorldCodex character atom IDs.
  - Prompt should instruct the planner to choose from provided WorldCodex atoms instead of inventing locations/characters.

- `storycodex/plan_beats.py`
  - Include WorldCodex context only as constraints/reference.
  - Beats should remain story action structure.

- `storycodex/build_context.py`
  - Primary integration point.
  - Replace `select_resolution_artifact(root / "artifacts" / "world", resolution)` and local character artifacts with WorldCodex exports.
  - Fetch a targeted context using scene plan IDs:
    - `world export <world> story-context --location <location_id> --character <character_id>`
    - If multiple characters are needed, fetch the main POV/protagonist context first and supplement with `character-context` or a broader `story-context`.
  - Transform WorldCodex atoms into Ring B:
    - `setting.location.id/name/constraints`
    - `cast[].id/name/role/voice_tics/current_state/wants_now/taboos`
  - Transform WorldCodex facts into Ring C:
    - `open_threads`
    - `relevant_facts`
    - `glossary`
  - Add WorldCodex export metadata and hashes to `build.sources` and context meta.

- `storycodex/check_continuity.py`
  - Keep story-structure checks.
  - Add WorldCodex-derived locks/facts to checker input.
  - Do not attempt to fix world canon directly.
  - If a scene introduces durable canon changes, emit a separate WorldCodex patch proposal later.

- `storycodex/write_scene.py`
  - Mostly keep as-is.
  - Strengthen prompt language: no new world facts beyond context unless the scene plan explicitly marks them as speculative or story-local.

- `README.md`
  - Explain WorldCodex dependency and commands.
  - Replace “world/characters optional artifacts” language with WorldCodex export language.

### Deprecate or Reframe

- `artifacts/world/*.json`
  - Deprecate as authored source files.
  - If retained, treat them as generated caches of WorldCodex exports only.

- `artifacts/characters/*.json`
  - Deprecate as authored source files.
  - If retained, treat them as generated caches of WorldCodex exports only.

- `artifacts/continuity/facts.json` and `locks.json`
  - Keep only for story-local constraints.
  - World facts and canon locks should be derived from WorldCodex context.

## Milestone 1: Add the WorldCodex Boundary

Add the integration layer without changing planning behavior yet.

Code changes:

- Add `storycodex/worldcodex_client.py`.
- Add environment readers for:
  - `STORYCODEX_WORLDCODEX_WORLD`
  - `STORYCODEX_WORLDCODEX_CLI`
  - `STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS`
- Add tests with a fake command runner.
- Add a CLI smoke command if useful:
  - `storycodex world export --root . --context story-context --character character.foo`
  - This should write a cache under `artifacts/worldcodex/`.

Acceptance tests:

- Client builds expected WorldCodex commands.
- JSON exports parse successfully.
- Non-zero WorldCodex exits raise useful errors.
- Existing tests still pass.

## Milestone 2: WorldCodex-Aware Scene Planning

Make scene plans choose canonical WorldCodex atoms.

Code changes:

- Extend story/plot seed inputs with optional WorldCodex selection fields:
  - protagonist atom ID
  - required cast atom IDs
  - primary location/faction/conflict IDs
  - tag/canon tier filters
- Update `plan_scenes.py` prompt to receive a compact WorldCodex context.
- Update schema/prompt expectations so:
  - `setting.location_id` may be `place.*`
  - `cast` should contain WorldCodex character atom IDs where known.
- Add tests that fake a WorldCodex export and verify planned scene IDs reference canonical atom IDs.

Acceptance tests:

- Scene plans no longer require placeholder location slugs when WorldCodex context exists.
- Cast entries preserve WorldCodex character IDs.
- Planner is still allowed to leave unknowns only when no suitable atom is available.

## Milestone 3: Build Context from WorldCodex

Move Ring B/C world and character material to WorldCodex exports.

Code changes:

- Update `build_context.py` to call `WorldCodexClient.export_context`.
- Add normalizers for WorldCodex atoms:
  - `place` -> context setting.
  - `character` -> context cast.
  - `org/faction/conflict/event` -> relevant facts, open threads, glossary, constraints.
  - relationships -> Ring C relevant facts or Ring B cast relationship notes.
- Stop reading `artifacts/world/*.json` and `artifacts/characters/*.json` as authored sources.
- Update `scene-context-packet.schema.json` if needed to include:
  - source atom IDs
  - relationship notes
  - canon tier constraints
  - WorldCodex export metadata

Acceptance tests:

- `build-context` can produce a valid context packet from fake WorldCodex exports.
- Ring B setting contains the WorldCodex place ID and name.
- Ring B cast contains WorldCodex character IDs and summaries.
- Ring C includes relevant timeline/conflict/relationship facts.
- `build.sources` includes the WorldCodex export context and selected source atom IDs.

## Milestone 4: Story Continuity and Canon Proposal Split

Keep StoryCodex continuity focused on story execution, then add optional canon proposals.

Code changes:

- Keep `check_continuity.py` checking:
  - beat coverage
  - POV
  - tense
  - continuity locks
  - context violations
- Add a separate command:
  - `storycodex propose-world-patch --root . --scene 1`
- This command should read:
  - scene context
  - draft/final scene
  - continuity report
  - WorldCodex source atom IDs
- It should emit `worldcodex.patch.v1` for durable world changes only.
- Do not apply patches by default.

Acceptance tests:

- Continuity report remains story/prose-focused.
- WorldCodex patch proposal output validates local shape.
- Scene-only prose fixes are not mixed with canon patches.
- `--apply` is absent or explicit; default is save/preview only.

## Milestone 5: Remove Local World-Building Assumptions and Update Docs

Clean up the ownership boundary.

Code changes:

- Update `README.md` quickstart:
  - configure WorldCodex world
  - plan spine
  - plan scenes with WorldCodex context
  - build context
  - write scene
  - check continuity
  - optionally propose WorldCodex patch
- Update tests that write local `artifacts/world` and `artifacts/characters` so they use fake WorldCodex exports or generated cache fixtures.
- Mark local world/character artifact support as legacy cache compatibility if not removed outright.
- Document that WorldCodex owns world-building and StoryCodex owns story structure.

Acceptance tests:

- No active code path treats local world/character artifacts as canonical source.
- Docs do not instruct users to author world or character canon in StoryCodex.
- Full CLI flow works with fake WorldCodex:
  - `storycodex seed apply`
  - `storycodex plan spine`
  - `storycodex plan scenes`
  - `storycodex plan beats`
  - `storycodex build-context`
  - `storycodex write scene`
  - `storycodex check continuity`

## Suggested Final Workflow

```bash
export STORYCODEX_WORLDCODEX_WORLD=titan-osa
export STORYCODEX_WORLDCODEX_CLI=world

storycodex init --root .
storycodex seed apply --root .
storycodex plan spine --root .
storycodex plan scenes --root .
storycodex plan beats --root . --scene 1
storycodex build-context --root . --scene 1
storycodex write scene --root . --scene 1 --target-words 1200
storycodex check continuity --root . --scene 1
storycodex propose-world-patch --root . --scene 1
```

WorldCodex should be the only tool that applies world/canon changes.

## Risks and Design Notes

- Scene planning may need a richer selector than a single `story-context` export if a scene includes several characters and locations. Start simple, then add `character-context` and `location-context` supplement calls.
- WorldCodex atom schemas may not map perfectly to StoryCodex cast fields such as `voice_tics`, `wants_now`, and `taboos`. These can be story-local overlays in StoryCodex, but should not overwrite WorldCodex canon.
- Story-local character state is legitimate in StoryCodex when it describes where a character is in this story arc. Canonical character facts belong in WorldCodex.
- Context packet schema should stay strict. Add WorldCodex metadata explicitly instead of allowing arbitrary extra fields.
- Patch proposal should be optional. Many scenes should not update world canon.

