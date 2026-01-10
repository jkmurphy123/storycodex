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
    scene_beats_meta_path,
    scene_beats_path,
    scene_plan_path,
    scenes_index_path,
)


@dataclass
class PlanBeatsResult:
    beats: dict[str, Any]
    meta: dict[str, Any]


def plan_beats(
    root: Path,
    scene_id: int,
    model: str | None,
    force: bool,
    run_id: str | None,
) -> PlanBeatsResult | None:
    beats_path = scene_beats_path(root, scene_id)
    if beats_path.exists() and not force:
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

    story_spec_text = story_spec_path.read_text()
    plan_text = plan_path.read_text()
    story_spec = json.loads(story_spec_text)
    scene_plan = json.loads(plan_text)

    plot_intent_text = None
    plot_intent_path = inputs_plot_intent_path(root)
    if plot_intent_path.exists():
        plot_intent_text = plot_intent_path.read_text()
        plot_intent = json.loads(plot_intent_text)
    else:
        plot_intent = None

    spine = read_optional_json(plot_spine_path(root))
    scenes_index = read_optional_json(scenes_index_path(root))

    chosen_model = model or llm.get_default_model()
    backend_used, _ = llm.resolve_backend(llm.get_base_url(), llm.get_backend_setting())

    prompt = build_prompt(story_spec, scene_plan, spine, scenes_index, plot_intent)
    content = llm.chat(prompt, chosen_model, temperature=0.4, max_tokens=1200)

    beats, errors = parse_and_validate(content)
    if errors:
        repair_prompt = build_repair_prompt(content, errors)
        repaired = llm.chat(repair_prompt, chosen_model, temperature=0.4, max_tokens=1200)
        beats, errors = parse_and_validate(repaired)
        if errors:
            raise ValueError("LLM response could not be repaired into valid JSON")

    beats_path.parent.mkdir(parents=True, exist_ok=True)
    beats_path.write_text(json.dumps(beats, indent=2, sort_keys=True) + "\n")

    input_hashes = {
        "story_spec": sha256_text(story_spec_text),
        "scene_plan": sha256_text(plan_text),
    }
    if plot_intent_text:
        input_hashes["plot_intent"] = sha256_text(plot_intent_text)

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": chosen_model,
        "backend": backend_used,
        "input_hashes": input_hashes,
        "run_id": run_id,
    }
    meta_path = scene_beats_meta_path(root, scene_id)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return PlanBeatsResult(beats=beats, meta=meta)


def build_prompt(
    story_spec: dict[str, Any],
    scene_plan: dict[str, Any],
    spine: dict[str, Any] | None,
    scenes_index: dict[str, Any] | None,
    plot_intent: dict[str, Any] | None,
) -> list[dict[str, str]]:
    spec_summary = {
        "pov": story_spec.get("pov"),
        "tense": story_spec.get("tense"),
        "tone": story_spec.get("tone"),
        "constraints": story_spec.get("constraints"),
        "serialization": story_spec.get("serialization"),
    }
    spec_json = json.dumps(spec_summary, indent=2, sort_keys=True)
    plan_json = json.dumps(scene_plan, indent=2, sort_keys=True)

    context_parts = []
    if spine is not None:
        context_parts.append("Spine JSON:\n" + json.dumps(spine, indent=2, sort_keys=True))
    if scenes_index is not None:
        context_parts.append(
            "Scenes index JSON:\n" + json.dumps(scenes_index, indent=2, sort_keys=True)
        )
    if plot_intent is not None:
        context_parts.append(
            "Plot intent JSON:\n" + json.dumps(plot_intent, indent=2, sort_keys=True)
        )

    context_block = "\n\n".join(context_parts)
    hook_rule = (
        "If story_spec.serialization.enabled is true OR the scene has high stakes, "
        "include a final hook beat to tee up the next scene."
    )

    instruction = (
        "Generate scene beats JSON that matches the schema. Return JSON only, no extra text, no markdown fences. "
        "Beats should form a coherent mini-arc: entry -> orientation -> pressure -> interaction -> turn -> exit. "
        "Always include at least one turn beat. "
        f"{hook_rule} "
        "Keep descriptions concrete with visible actions, dialogue intent, or reveals. "
        "must_include and must_avoid should be short bullet-like strings and ONLY appear inside beat objects (not at the root). "
        "Align beats with any relevant plot constraints or act-shape purpose for this scene.\n\n"
        "Output shape example (structure only):\n"
        "{\n"
        "  \"scene_id\": 1,\n"
        "  \"beats\": [\n"
        "    {\"type\": \"entry\", \"description\": \"...\"},\n"
        "    {\"type\": \"orientation\", \"description\": \"...\"},\n"
        "    {\"type\": \"pressure\", \"description\": \"...\"},\n"
        "    {\"type\": \"interaction\", \"description\": \"...\"},\n"
        "    {\"type\": \"turn\", \"description\": \"...\"},\n"
        "    {\"type\": \"exit\", \"description\": \"...\"},\n"
        "    {\"type\": \"hook\", \"description\": \"...\", \"must_include\": [\"...\"], \"must_avoid\": [\"...\"]}\n"
        "  ]\n"
        "}\n\n"
        "Story spec summary:\n"
        f"{spec_json}\n\n"
        "Scene plan JSON:\n"
        f"{plan_json}"
    )

    if context_block:
        instruction = instruction + "\n\n" + context_block

    return [
        {"role": "system", "content": "You are a careful story planner."},
        {"role": "user", "content": instruction},
    ]


def build_repair_prompt(invalid_text: str, errors: list[str]) -> list[dict[str, str]]:
    error_text = "\n".join(f"- {error}" for error in errors)
    instruction = (
        "The previous response was invalid. Return ONLY valid JSON (no markdown fences) "
        "that matches scene-beats.schema.json.\n"
        "Errors:\n"
        f"{error_text}\n\n"
        "Invalid response:\n"
        f"{invalid_text}"
    )
    return [
        {"role": "system", "content": "You must output valid JSON only."},
        {"role": "user", "content": instruction},
    ]


def parse_and_validate(content: str) -> tuple[dict[str, Any] | None, list[str]]:
    content = extract_llm_content(content)
    try:
        payload = json.loads(strip_json_fences(content))
    except json.JSONDecodeError:
        return None, ["Response is not valid JSON"]

    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    schema = load_schema("scene-beats.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    errors = [error.message for error in validator.iter_errors(payload)]
    if errors:
        return None, errors

    return payload, []


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


def extract_llm_content(text: str) -> str:
    raw = text.strip()
    if raw.startswith("response="):
        raw = raw[len("response=") :].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    if isinstance(parsed, dict):
        if "choices" in parsed:
            try:
                return parsed["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                return raw
        if "message" in parsed and isinstance(parsed["message"], dict):
            content = parsed["message"].get("content")
            if isinstance(content, str):
                return content
        if "content" in parsed and isinstance(parsed["content"], str):
            return parsed["content"]
        if parsed.get("role") == "assistant" and isinstance(parsed.get("content"), str):
            return parsed["content"]
    return raw


def read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
