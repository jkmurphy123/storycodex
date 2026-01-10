from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from . import llm
from .paths import (
    inputs_plot_intent_path,
    inputs_spec_path,
    plot_spine_path,
    scene_beats_path,
    scene_context_meta_path,
    scene_context_path,
    scene_plan_path,
    scenes_index_path,
    seed_style_profile_path,
)


@dataclass
class BuildContextResult:
    context: dict[str, Any]
    meta: dict[str, Any]


def build_context(
    root: Path,
    scene_id: int,
    budget: int,
    resolution: str,
    include: str,
    model: str | None,
    force: bool,
    run_id: str | None,
) -> BuildContextResult | None:
    context_path = scene_context_path(root, scene_id)
    if context_path.exists() and not force:
        return None

    story_spec_path = inputs_spec_path(root)
    if not story_spec_path.exists():
        raise FileNotFoundError(
            f"Missing story spec at {story_spec_path}; run seed apply first."
        )

    plan_path = scene_plan_path(root, scene_id)
    if not plan_path.exists():
        raise FileNotFoundError(
            f"Missing scene plan at {plan_path}; run plan scenes first."
        )

    beats_path = scene_beats_path(root, scene_id)
    if not beats_path.exists():
        raise FileNotFoundError(
            f"Missing scene beats at {beats_path}; run plan beats first."
        )

    story_spec_text = story_spec_path.read_text()
    plan_text = plan_path.read_text()
    beats_text = beats_path.read_text()

    story_spec = json.loads(story_spec_text)
    scene_plan = json.loads(plan_text)
    scene_beats = json.loads(beats_text)

    optional_artifacts: dict[str, dict[str, Any]] = {}
    input_hashes = {
        "story_spec": sha256_text(story_spec_text),
        "scene_plan": sha256_text(plan_text),
        "scene_beats": sha256_text(beats_text),
    }

    plot_intent = read_optional_json(
        inputs_plot_intent_path(root), input_hashes, "plot_intent"
    )
    style_profile = read_style_profile(root, input_hashes)
    spine = read_optional_json(plot_spine_path(root), input_hashes, "plot_spine")
    scenes_index = read_optional_json(
        scenes_index_path(root), input_hashes, "scenes_index"
    )
    locks = read_optional_json(
        root / "artifacts" / "continuity" / "locks.json",
        input_hashes,
        "continuity_locks",
    )
    facts = read_optional_json(
        root / "artifacts" / "continuity" / "facts.json",
        input_hashes,
        "continuity_facts",
    )

    world_data, world_resolution = select_resolution_artifact(
        root / "artifacts" / "world", resolution
    )
    if world_data is not None:
        optional_artifacts["world"] = {"data": world_data, "resolution": world_resolution}
        input_hashes["world"] = sha256_text(json.dumps(world_data, sort_keys=True))

    characters_data, characters_resolution = select_resolution_artifact(
        root / "artifacts" / "characters", resolution
    )
    if characters_data is not None:
        optional_artifacts["characters"] = {
            "data": characters_data,
            "resolution": characters_resolution,
        }
        input_hashes["characters"] = sha256_text(
            json.dumps(characters_data, sort_keys=True)
        )

    state_data = read_character_state(root, scene_plan)
    if state_data is not None:
        optional_artifacts["character_state"] = {
            "data": state_data,
            "resolution": characters_resolution or "tiny",
        }
        input_hashes["character_state"] = sha256_text(
            json.dumps(state_data, sort_keys=True)
        )

    prior_scene_summary = "N/A"
    prior_scene_path = prior_scene_text_path(root, scene_id)
    if prior_scene_path is not None:
        summary_text = summarize_prior_scene(prior_scene_path, model)
        prior_scene_summary = summary_text
        input_hashes["prior_scene"] = sha256_text(prior_scene_path.read_text())

    ringA = build_ringA(story_spec, plot_intent)
    if style_profile is not None:
        ringA = apply_style_profile(ringA, style_profile)
    ringB = build_ringB(scene_plan, scene_beats, optional_artifacts, locks)
    ringC = build_ringC(
        prior_scene_summary, scenes_index, facts, optional_artifacts, ringB
    )

    ringA, ringB, ringC = apply_include(include, ringA, ringB, ringC)

    required_sources: list[Any] = ["inputs/story_spec.json", plan_path, beats_path]
    if plot_intent is not None:
        required_sources.append("inputs/plot_intent.json")

    sources = build_sources(
        resolution,
        required=required_sources,
        optional=optional_artifacts,
    )
    if style_profile is not None:
        sources.append({"artifact_id": "seeds/style_profile.json", "resolution_used": "tiny"})

    context = {
        "scene_id": scene_id,
        "build": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "budget_tokens": budget,
            "resolution_strategy": resolution,
            "include": include,
            "sources": sources,
        },
        "ringA": ringA,
        "ringB": ringB,
        "ringC": ringC,
    }

    errors = validate_context(context)
    if errors:
        repair_prompt = build_repair_prompt(context, errors)
        repaired = llm.chat(
            repair_prompt, model or llm.get_default_model(), temperature=0.2, max_tokens=1200
        )
        repaired_context = parse_json_or_none(repaired)
        if repaired_context is None:
            raise ValueError("LLM response could not be repaired into valid JSON")
        errors = validate_context(repaired_context)
        if errors:
            raise ValueError("LLM response could not be repaired into valid JSON")
        context = repaired_context

    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n")

    backend_used, _ = llm.resolve_backend(llm.get_base_url(), llm.get_backend_setting())
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model or llm.get_default_model(),
        "backend": backend_used,
        "input_hashes": input_hashes,
        "run_id": run_id,
        "budget": budget,
        "resolution": resolution,
        "include": include,
    }
    meta_path = scene_context_meta_path(root, scene_id)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return BuildContextResult(context=context, meta=meta)


def build_ringA(
    story_spec: dict[str, Any],
    plot_intent: dict[str, Any] | None,
) -> dict[str, Any]:
    logline = story_spec.get("logline") or ""
    premise = logline if logline else story_spec.get("title", "")

    constraints = story_spec.get("constraints", {})
    must = constraints.get("must", []) if isinstance(constraints, dict) else []
    must_not = constraints.get("must_not", []) if isinstance(constraints, dict) else []
    global_constraints = [f"MUST {item}" for item in must] + [
        f"MUST NOT {item}" for item in must_not
    ]

    if plot_intent and isinstance(plot_intent, dict):
        intent = plot_intent.get("plot_intent", {})
        if isinstance(intent, dict):
            core_arc = intent.get("core_arc")
            if isinstance(core_arc, str) and core_arc.strip():
                global_constraints.append(f"Core arc: {core_arc.strip()}")
            central_question = intent.get("central_question")
            if isinstance(central_question, str) and central_question.strip():
                global_constraints.append(
                    f"Central question: {central_question.strip()}"
                )

    tone = story_spec.get("tone", []) or []
    pov = story_spec.get("pov", "first")
    tense = story_spec.get("tense", "past")

    style_rules = [
        f"Write in {tense} tense.",
        f"Use {pov} POV.",
        "Keep paragraphs concise.",
        "Favor concrete sensory details.",
        "Maintain tonal consistency.",
    ]
    if isinstance(tone, list) and tone:
        style_rules.append("Tone: " + ", ".join(tone))
    if plot_intent and isinstance(plot_intent, dict):
        intent = plot_intent.get("plot_intent", {})
        themes = intent.get("themes") if isinstance(intent, dict) else None
        if isinstance(themes, list):
            for theme in themes:
                if isinstance(theme, str) and theme.strip():
                    style_rules.append(f"Theme: {theme.strip()}")

    return {
        "premise": premise,
        "tone": tone if isinstance(tone, list) else [],
        "pov": pov,
        "tense": tense,
        "global_constraints": global_constraints,
        "style_rules": style_rules,
    }


def apply_style_profile(ringA: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    tone = ensure_list(profile.get("tone", []))
    ringA["tone"] = append_unique(ringA.get("tone", []), tone)

    scene_rules = profile.get("scene_rules", {}) if isinstance(profile, dict) else {}
    must_include = ensure_list(scene_rules.get("must_include", []))
    must_not = ensure_list(scene_rules.get("must_not", []))
    horror_engine = profile.get("horror_engine", {}) if isinstance(profile, dict) else {}
    taboos = ensure_list(horror_engine.get("taboos", []))

    constraints = ringA.get("global_constraints", [])
    constraints = append_unique(
        constraints,
        [f"MUST: {item}" for item in must_include if item],
    )
    constraints = append_unique(
        constraints,
        [f"MUST NOT: {item}" for item in must_not if item],
    )
    constraints = append_unique(
        constraints,
        [f"MUST NOT: {item}" for item in taboos if item],
    )
    ringA["global_constraints"] = constraints

    new_rules = build_style_rules_from_profile(profile)
    ringA["style_rules"] = cap_rules(
        append_unique(ringA.get("style_rules", []), new_rules), 20
    )
    return ringA


def build_style_rules_from_profile(profile: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    intent = profile.get("intent")
    if isinstance(intent, str) and intent.strip():
        rules.append(f"Intent: {intent.strip()}")

    syntax = profile.get("syntax", {}) if isinstance(profile, dict) else {}
    if isinstance(syntax, dict):
        sentence_rhythm = syntax.get("sentence_rhythm")
        if isinstance(sentence_rhythm, str) and sentence_rhythm.strip():
            rules.append(f"Sentence rhythm: {sentence_rhythm.strip()}")
        paragraphing = syntax.get("paragraphing")
        if isinstance(paragraphing, str) and paragraphing.strip():
            rules.append(f"Paragraphing: {paragraphing.strip()}")

    sensory = profile.get("sensory", {}) if isinstance(profile, dict) else {}
    if isinstance(sensory, dict):
        priority_order = ensure_list(sensory.get("priority_order", []))
        motifs = ensure_list(sensory.get("motifs", []))
        if priority_order:
            rules.append("Sensory priority: " + " > ".join(priority_order))
        if motifs:
            rules.append("Motifs: " + ", ".join(motifs))

    dialogue = profile.get("dialogue", {}) if isinstance(profile, dict) else {}
    if isinstance(dialogue, dict):
        subtext_rule = dialogue.get("subtext_rule")
        if isinstance(subtext_rule, str) and subtext_rule.strip():
            rules.append(f"Dialogue subtext: {subtext_rule.strip()}")
        style = dialogue.get("style")
        if isinstance(style, str) and style.strip():
            rules.append(f"Dialogue style: {style.strip()}")

    diction = profile.get("diction", {}) if isinstance(profile, dict) else {}
    if isinstance(diction, dict):
        register = diction.get("register")
        note = diction.get("note")
        if isinstance(register, str) and register.strip():
            rules.append(f"Diction register: {register.strip()}")
        if isinstance(note, str) and note.strip():
            rules.append(f"Diction note: {note.strip()}")

    output_controls = profile.get("output_controls", {}) if isinstance(profile, dict) else {}
    if isinstance(output_controls, dict) and output_controls:
        parts = []
        for key in ["metaphor_density", "exposition_throttle", "violence", "gore"]:
            value = output_controls.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{key}={value.strip()}")
        if parts:
            rules.append("Output controls: " + ", ".join(parts))

    horror_engine = profile.get("horror_engine", {}) if isinstance(profile, dict) else {}
    if isinstance(horror_engine, dict):
        principles = ensure_list(horror_engine.get("principles", []))[:5]
        rules.extend([f"Horror principle: {item}" for item in principles if item])

    voice = profile.get("character_voice", {}) if isinstance(profile, dict) else {}
    if isinstance(voice, dict):
        habits = ensure_list(voice.get("habits", []))[:5]
        rules.extend([f"Voice habit: {item}" for item in habits if item])
        unreliability = ensure_list(voice.get("unreliability", []))[:5]
        rules.extend([f"Unreliability: {item}" for item in unreliability if item])

    return rules


def cap_rules(rules: list[str], limit: int) -> list[str]:
    return rules[:limit]


def build_ringB(
    scene_plan: dict[str, Any],
    scene_beats: dict[str, Any],
    optional_artifacts: dict[str, dict[str, Any]],
    locks: dict[str, Any] | None,
) -> dict[str, Any]:
    setting = scene_plan.get("setting", {}) if isinstance(scene_plan, dict) else {}
    location_id = ""
    time = ""
    mood_tags: list[str] = []
    if isinstance(setting, dict):
        location_id = setting.get("location_id", "")
        time = setting.get("time", "")
        mood_tags = ensure_list(setting.get("mood_tags", []))

    cast_names = scene_plan.get("cast", []) if isinstance(scene_plan.get("cast", []), list) else []
    characters = build_cast(cast_names, optional_artifacts)

    beats = scene_beats.get("beats", []) if isinstance(scene_beats, dict) else []
    beats = [beat for beat in beats if isinstance(beat, dict)]

    continuity_locks = []
    if locks:
        continuity_locks = select_relevant_locks(locks, cast_names, location_id)

    return {
        "scene_goal": scene_plan.get("goal", ""),
        "setting": {
            "location": {
                "id": location_id,
                "name": location_id,
                "constraints": [],
            },
            "time": time,
            "mood_tags": mood_tags,
        },
        "cast": characters,
        "beats": beats,
        "continuity_locks": continuity_locks,
    }


def build_ringC(
    prior_scene_summary: str,
    scenes_index: dict[str, Any] | None,
    facts: dict[str, Any] | None,
    optional_artifacts: dict[str, dict[str, Any]],
    ringB: dict[str, Any],
) -> dict[str, Any]:
    open_threads: list[str] = []
    if scenes_index and isinstance(scenes_index, dict):
        open_threads = []

    relevant_facts: list[str] = []
    if facts:
        relevant_facts = select_relevant_facts(facts, ringB)

    glossary = []
    world = optional_artifacts.get("world")
    if world:
        glossary = select_glossary_terms(world["data"], ringB)

    return {
        "prior_scene_summary": prior_scene_summary,
        "open_threads": open_threads,
        "relevant_facts": relevant_facts,
        "glossary": glossary,
    }


def apply_include(
    include: str,
    ringA: dict[str, Any],
    ringB: dict[str, Any],
    ringC: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if include == "all":
        return ringA, ringB, ringC
    if include == "ringA":
        return ringA, empty_ringB(), empty_ringC()
    if include == "ringB":
        return empty_ringA(), ringB, empty_ringC()
    if include == "ringC":
        return empty_ringA(), empty_ringB(), ringC
    return ringA, ringB, ringC


def empty_ringA() -> dict[str, Any]:
    return {
        "premise": "",
        "tone": [],
        "pov": "first",
        "tense": "past",
        "global_constraints": [],
        "style_rules": [],
    }


def empty_ringB() -> dict[str, Any]:
    return {
        "scene_goal": "",
        "setting": {
            "location": {"id": "", "name": "", "constraints": []},
            "time": "",
            "mood_tags": [],
        },
        "cast": [],
        "beats": [],
        "continuity_locks": [],
    }


def empty_ringC() -> dict[str, Any]:
    return {
        "prior_scene_summary": "N/A",
        "open_threads": [],
        "relevant_facts": [],
        "glossary": [],
    }


def build_sources(
    resolution: str,
    required: list[Any],
    optional: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    resolution_used = resolution if resolution in {"tiny", "medium", "full"} else "tiny"
    for item in required:
        if isinstance(item, Path):
            artifact_id = str(item)
        else:
            artifact_id = str(item)
        sources.append({"artifact_id": artifact_id, "resolution_used": resolution_used})

    for key, info in optional.items():
        sources.append(
            {"artifact_id": key, "resolution_used": info.get("resolution", "tiny")}
        )
    return sources


def select_resolution_artifact(base: Path, resolution: str) -> tuple[dict[str, Any] | None, str | None]:
    order = resolution_order(resolution)
    for res in order:
        path = base / f"{res}.json"
        if path.exists():
            return json.loads(path.read_text()), res
    return None, None


def resolution_order(resolution: str) -> list[str]:
    if resolution == "tiny":
        return ["tiny", "medium", "full"]
    if resolution == "medium":
        return ["medium", "tiny", "full"]
    if resolution == "full":
        return ["full", "medium", "tiny"]
    return ["tiny", "medium", "full"]


def read_optional_json(path: Path, input_hashes: dict[str, str], key: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text()
    input_hashes[key] = sha256_text(text)
    return json.loads(text)


def read_style_profile(root: Path, input_hashes: dict[str, str]) -> dict[str, Any] | None:
    path = seed_style_profile_path(root)
    if not path.exists():
        return None
    text = path.read_text()
    validate_style_profile(text)
    input_hashes["style_profile"] = sha256_text(text)
    return json.loads(text)


def validate_style_profile(text: str) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    schema = load_schema("style-profile.schema.json")
    data = json.loads(text)
    validator = jsonschema.Draft202012Validator(schema)
    errors = [error.message for error in validator.iter_errors(data)]
    if errors:
        raise ValueError("Style profile validation failed: " + "; ".join(errors))


def read_character_state(root: Path, scene_plan: dict[str, Any]) -> dict[str, Any] | None:
    chapter_no = scene_plan.get("chapter_no")
    if not isinstance(chapter_no, int):
        return None
    state_path = root / "artifacts" / "characters" / "state" / f"ch{chapter_no:02d}.json"
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text())


def build_cast(cast_names: list[Any], optional_artifacts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    characters_data = optional_artifacts.get("characters", {}).get("data")
    state_data = optional_artifacts.get("character_state", {}).get("data")
    characters = []
    for name in cast_names:
        if not isinstance(name, str):
            continue
        entry = find_character(characters_data, name)
        if entry:
            current_state = entry.get("current_state", "")
            if state_data:
                state_override = find_character_state(state_data, entry)
                if state_override:
                    current_state = state_override
            characters.append(
                {
                    "id": entry.get("id", name),
                    "name": entry.get("name", name),
                    "role": entry.get("role", ""),
                    "voice_tics": ensure_list(entry.get("voice_tics", [])),
                    "current_state": current_state,
                    "wants_now": ensure_list(entry.get("wants_now", [])),
                    "taboos": ensure_list(entry.get("taboos", [])),
                }
            )
        else:
            characters.append(
                {
                    "id": name,
                    "name": name,
                    "role": "",
                    "voice_tics": [],
                    "current_state": "",
                    "wants_now": [],
                    "taboos": [],
                }
            )
    return characters


def find_character(data: Any, name: str) -> dict[str, Any] | None:
    if isinstance(data, list):
        for entry in data:
            if match_character(entry, name):
                return entry
    if isinstance(data, dict):
        for key in ["characters", "items"]:
            if isinstance(data.get(key), list):
                for entry in data[key]:
                    if match_character(entry, name):
                        return entry
    return None


def match_character(entry: Any, name: str) -> bool:
    if not isinstance(entry, dict):
        return False
    entry_id = str(entry.get("id", "")).lower()
    entry_name = str(entry.get("name", "")).lower()
    target = name.lower()
    return target in {entry_id, entry_name}


def find_character_state(state_data: Any, entry: dict[str, Any]) -> str | None:
    if isinstance(state_data, dict):
        state_map = state_data.get("characters")
        if isinstance(state_map, dict):
            entry_id = entry.get("id")
            if entry_id in state_map and isinstance(state_map[entry_id], dict):
                return state_map[entry_id].get("current_state")
    return None


def select_relevant_locks(locks: dict[str, Any], cast: list[Any], location_id: str) -> list[dict[str, Any]]:
    lock_items = []
    if isinstance(locks, list):
        lock_items = locks
    elif isinstance(locks, dict):
        if isinstance(locks.get("locks"), list):
            lock_items = locks.get("locks", [])
        elif isinstance(locks.get("items"), list):
            lock_items = locks.get("items", [])

    keywords = {str(item).lower() for item in cast}
    if location_id:
        keywords.add(location_id.lower())

    selected = []
    for lock in lock_items:
        normalized = normalize_lock(lock)
        if not keywords:
            selected.append(normalized)
            continue
        statement = normalized.get("statement", "").lower()
        if any(keyword in statement for keyword in keywords):
            selected.append(normalized)
    return selected


def normalize_lock(lock: Any) -> dict[str, Any]:
    if not isinstance(lock, dict):
        return {
            "id": "unknown",
            "statement": str(lock),
            "severity": "should",
            "tags": [],
        }
    severity = lock.get("severity", "should")
    if severity not in {"must", "should"}:
        severity = "should"
    return {
        "id": str(lock.get("id", lock.get("lock_id", "unknown"))),
        "statement": str(lock.get("statement", lock.get("text", ""))),
        "severity": severity,
        "tags": ensure_list(lock.get("tags", [])),
    }


def select_relevant_facts(facts: dict[str, Any], ringB: dict[str, Any]) -> list[str]:
    candidates = []
    if isinstance(facts, list):
        candidates = facts
    elif isinstance(facts, dict):
        if isinstance(facts.get("facts"), list):
            candidates = facts.get("facts", [])
        elif isinstance(facts.get("items"), list):
            candidates = facts.get("items", [])

    keywords = set()
    for entry in ringB.get("cast", []):
        if isinstance(entry, dict):
            keywords.add(entry.get("name", "").lower())
    location = ringB.get("setting", {}).get("location", {}).get("id", "")
    if location:
        keywords.add(location.lower())

    results = []
    for item in candidates:
        if isinstance(item, str):
            if any(keyword in item.lower() for keyword in keywords):
                results.append(item)
        elif isinstance(item, dict):
            statement = str(item.get("statement", item.get("text", "")))
            if any(keyword in statement.lower() for keyword in keywords):
                results.append(statement)
    return results


def select_glossary_terms(world_data: dict[str, Any], ringB: dict[str, Any]) -> list[dict[str, Any]]:
    glossary = world_data.get("glossary") if isinstance(world_data, dict) else None
    if not isinstance(glossary, list):
        return []

    text_blob = json.dumps(ringB, sort_keys=True).lower()
    selected = []
    for entry in glossary:
        if not isinstance(entry, dict):
            continue
        term = entry.get("term")
        definition = entry.get("definition")
        if not term or not definition:
            continue
        if term.lower() in text_blob:
            selected.append({"term": term, "definition": definition})
    return selected


def prior_scene_text_path(root: Path, scene_id: int) -> Path | None:
    if scene_id <= 1:
        return None
    out_dir = root / "out" / "scenes"
    final_path = out_dir / f"scene_{scene_id - 1:03d}.final.md"
    if final_path.exists():
        return final_path
    draft_path = out_dir / f"scene_{scene_id - 1:03d}.draft.md"
    if draft_path.exists():
        return draft_path
    return None


def summarize_prior_scene(path: Path, model: str | None) -> str:
    content = path.read_text()
    prompt = [
        {"role": "system", "content": "Summarize the scene in 3-5 sentences."},
        {"role": "user", "content": content},
    ]
    return llm.chat(prompt, model or llm.get_default_model(), temperature=0.2, max_tokens=200)


def validate_context(context: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    schema = load_schema("scene-context-packet.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    return [error.message for error in validator.iter_errors(context)]


def build_repair_prompt(context: dict[str, Any], errors: list[str]) -> list[dict[str, str]]:
    error_text = "\n".join(f"- {error}" for error in errors)
    instruction = (
        "The JSON context packet is invalid. Return ONLY corrected JSON that matches "
        "scene-context-packet.schema.json.\nErrors:\n"
        f"{error_text}\n\nInvalid JSON:\n"
        f"{json.dumps(context, indent=2, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": "You must output valid JSON only."},
        {"role": "user", "content": instruction},
    ]


def parse_json_or_none(content: str) -> dict[str, Any] | None:
    try:
        return json.loads(strip_json_fences(content))
    except json.JSONDecodeError:
        return None


def load_schema(name: str) -> dict[str, Any]:
    schema_path = resources.files("storycodex.schemas").joinpath(name)
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def append_unique(base: list[Any], extra: list[Any]) -> list[Any]:
    result: list[Any] = []
    for item in base + extra:
        if not any(item == existing for existing in result):
            result.append(item)
    return result


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
