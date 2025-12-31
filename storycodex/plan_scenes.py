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
    inputs_spec_path,
    plot_spine_path,
    scene_beats_path,
    scene_plan_path,
    scenes_index_path,
    scenes_meta_path,
)


@dataclass
class PlanScenesResult:
    index: dict[str, Any]
    plans: list[dict[str, Any]]
    meta: dict[str, Any]


def plan_scenes(
    root: Path,
    chapter: int | None,
    model: str | None,
    force: bool,
    run_id: str | None,
) -> PlanScenesResult | None:
    index_path = scenes_index_path(root)
    if chapter is None and index_path.exists() and not force:
        return None

    story_spec_path = inputs_spec_path(root)
    if not story_spec_path.exists():
        raise FileNotFoundError(
            f"Missing story spec at {story_spec_path}; run seed apply first."
        )

    spine_path = plot_spine_path(root)
    if not spine_path.exists():
        raise FileNotFoundError(
            f"Missing plot spine at {spine_path}; run plan spine first."
        )

    story_spec_text = story_spec_path.read_text()
    spine_text = spine_path.read_text()
    story_spec = json.loads(story_spec_text)
    spine = json.loads(spine_text)

    scene_ids_by_chapter, scene_id_to_chapter = extract_scene_ids(spine)
    if chapter is not None:
        if chapter not in scene_ids_by_chapter:
            raise ValueError(f"Chapter {chapter} not found in spine")
        target_scene_ids = scene_ids_by_chapter[chapter]
        if index_path.exists() and not force:
            if all(
                scene_plan_path(root, scene_id).exists()
                for scene_id in target_scene_ids
            ):
                return None
    else:
        target_scene_ids = [
            scene_id
            for scene_ids in scene_ids_by_chapter.values()
            for scene_id in scene_ids
        ]

    chosen_model = model or llm.get_default_model()
    backend_used, _ = llm.resolve_backend(llm.get_base_url(), llm.get_backend_setting())

    prompt = build_prompt(story_spec, spine, chapter)
    content = llm.chat(prompt, chosen_model, temperature=0.4, max_tokens=2000)

    index, plans, errors = parse_and_validate(
        content,
        scene_ids_by_chapter,
        scene_id_to_chapter,
        target_scene_ids,
    )
    if errors:
        repair_prompt = build_repair_prompt(content, errors)
        repaired = llm.chat(
            repair_prompt, chosen_model, temperature=0.4, max_tokens=2000
        )
        index, plans, errors = parse_and_validate(
            repaired,
            scene_ids_by_chapter,
            scene_id_to_chapter,
            target_scene_ids,
        )
        if errors:
            raise ValueError("LLM response could not be repaired into valid JSON")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")

    for plan in plans:
        plan_path = scene_plan_path(root, plan["scene_id"])
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": chosen_model,
        "backend": backend_used,
        "input_hashes": {
            "story_spec": sha256_text(story_spec_text),
            "spine": sha256_text(spine_text),
        },
        "run_id": run_id,
        "chapter": chapter,
    }
    meta_path = scenes_meta_path(root)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return PlanScenesResult(index=index, plans=plans, meta=meta)


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def extract_scene_ids(spine: dict[str, Any]) -> tuple[dict[int, list[int]], dict[int, int]]:
    scene_ids_by_chapter: dict[int, list[int]] = {}
    scene_id_to_chapter: dict[int, int] = {}

    for act in spine.get("acts", []):
        for chapter in act.get("chapters", []):
            chapter_no = chapter.get("chapter_no")
            scenes = chapter.get("scenes", [])
            if not isinstance(chapter_no, int):
                continue
            scene_ids_by_chapter.setdefault(chapter_no, [])
            for scene_id in scenes:
                if isinstance(scene_id, int):
                    scene_ids_by_chapter[chapter_no].append(scene_id)
                    scene_id_to_chapter[scene_id] = chapter_no

    return scene_ids_by_chapter, scene_id_to_chapter


def build_prompt(
    story_spec: dict[str, Any],
    spine: dict[str, Any],
    chapter: int | None,
) -> list[dict[str, str]]:
    story_json = json.dumps(story_spec, indent=2, sort_keys=True)
    spine_json = json.dumps(spine, indent=2, sort_keys=True)
    chapter_line = (
        f"Only include plans for chapter {chapter}."
        if chapter is not None
        else "Include plans for all chapters."
    )
    instruction = (
        "Generate a JSON object with two keys: index and plans. BOTH keys are required. "
        "Return JSON only, no extra text, no markdown fences. "
        "Do NOT wrap the JSON in {role, content}. "
        "Use the spine scene IDs exactly; scenes are global sequential integers. "
        "index must be an object: {version: 1, scenes: [ ... ]}. "
        "Each index.scenes item must be: "
        "{scene_id, chapter_no, title, plan_path, beats_path}. "
        "plan_path must be artifacts/scenes/scene_###.plan.json and "
        "beats_path must be artifacts/scenes/scene_###.beats.json (zero-padded to 3 digits). "
        "plans must be a list of scene-plan objects with required fields, and there must be one plan per scene_id. "
        "Do not omit the plans list: it is required even if brief. "
        "{scene_id, chapter_no, title, setting, cast, goal, stakes, beats_ref}. "
        "setting must be an object: {location_id, time, mood_tags} and "
        "location_id must be a short slug (e.g. argonaut_station_corridor). "
        "beats_ref must equal the matching beats_path. "
        "Keep cast to 0-4 entries. Keep content concise. "
        f"{chapter_line}\n\n"
        "Output format:\n"
        "{\"index\": <scenes-index>, \"plans\": [<scene-plan>, ...]}\n\n"
        "Example (shape only, not actual content):\n"
        "{\n"
        "  \"index\": {\n"
        "    \"version\": 1,\n"
        "    \"scenes\": [\n"
        "      {\n"
        "        \"scene_id\": 1,\n"
        "        \"chapter_no\": 1,\n"
        "        \"title\": \"Scene Title\",\n"
        "        \"plan_path\": \"artifacts/scenes/scene_001.plan.json\",\n"
        "        \"beats_path\": \"artifacts/scenes/scene_001.beats.json\"\n"
        "      }\n"
        "    ]\n"
        "  },\n"
        "  \"plans\": [\n"
        "    {\n"
        "      \"scene_id\": 1,\n"
        "      \"chapter_no\": 1,\n"
        "      \"title\": \"Scene Title\",\n"
        "      \"setting\": {\n"
        "        \"location_id\": \"ship_corridor\",\n"
        "        \"time\": \"night\",\n"
        "        \"mood_tags\": [\"tense\"]\n"
        "      },\n"
        "      \"cast\": [\"Protagonist\"],\n"
        "      \"goal\": \"Short goal\",\n"
        "      \"stakes\": \"Short stakes\",\n"
        "      \"beats_ref\": \"artifacts/scenes/scene_001.beats.json\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Story spec JSON:\n"
        f"{story_json}\n\n"
        "Spine JSON:\n"
        f"{spine_json}"
    )
    return [
        {"role": "system", "content": "You are a careful story planner."},
        {"role": "user", "content": instruction},
    ]


def build_repair_prompt(invalid_text: str, errors: list[str]) -> list[dict[str, str]]:
    error_text = "\n".join(f"- {error}" for error in errors)
    instruction = (
        "The previous response was invalid. Return ONLY valid JSON (no markdown fences) in the format "
        "{\"index\": <scenes-index>, \"plans\": [<scene-plan>, ...]}.\n"
        "Errors:\n"
        f"{error_text}\n\n"
        "Invalid response:\n"
        f"{invalid_text}"
    )
    return [
        {"role": "system", "content": "You must output valid JSON only."},
        {"role": "user", "content": instruction},
    ]


def parse_and_validate(
    content: str,
    scene_ids_by_chapter: dict[int, list[int]],
    scene_id_to_chapter: dict[int, int],
    target_scene_ids: list[int],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, list[str]]:
    try:
        payload = json.loads(strip_json_fences(content))
    except json.JSONDecodeError:
        return None, None, ["Response is not valid JSON"]

    if not isinstance(payload, dict):
        return None, None, ["Response must be a JSON object"]

    index = payload.get("index")
    plans = payload.get("plans")
    errors: list[str] = []

    schema_index = load_schema("scenes-index.schema.json")
    schema_plan = load_schema("scene-plan.schema.json")

    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    validator_index = jsonschema.Draft202012Validator(schema_index)
    validator_plan = jsonschema.Draft202012Validator(schema_plan)

    if index is None:
        errors.append("Missing index in response")
    else:
        for error in validator_index.iter_errors(index):
            errors.append(f"index: {error.message}")

    if plans is None:
        errors.append("Missing plans in response")
    elif not isinstance(plans, list):
        errors.append("plans must be a list")

    expected_scene_ids = [
        scene_id
        for scene_ids in scene_ids_by_chapter.values()
        for scene_id in scene_ids
    ]
    expected_scene_ids_set = set(expected_scene_ids)

    if isinstance(index, dict):
        entries = index.get("scenes", []) if isinstance(index.get("scenes"), list) else []
        seen_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            scene_id = entry.get("scene_id")
            seen_ids.add(scene_id)
            chapter_no = entry.get("chapter_no")
            if scene_id not in expected_scene_ids_set:
                errors.append(f"index includes unknown scene_id {scene_id}")
                continue
            if chapter_no != scene_id_to_chapter.get(scene_id):
                errors.append(f"scene_id {scene_id} has wrong chapter_no")
            expected_plan = plan_path_for_scene(scene_id)
            expected_beats = beats_path_for_scene(scene_id)
            if entry.get("plan_path") != expected_plan:
                errors.append(f"scene_id {scene_id} has invalid plan_path")
            if entry.get("beats_path") != expected_beats:
                errors.append(f"scene_id {scene_id} has invalid beats_path")
        missing = expected_scene_ids_set - seen_ids
        if missing:
            errors.append("index missing scenes: " + ", ".join(str(s) for s in sorted(missing)))

    if isinstance(plans, list):
        plan_ids = set()
        for plan in plans:
            if not isinstance(plan, dict):
                errors.append("plan entries must be objects")
                continue
            for error in validator_plan.iter_errors(plan):
                errors.append(f"plan {plan.get('scene_id')}: {error.message}")
            scene_id = plan.get("scene_id")
            chapter_no = plan.get("chapter_no")
            if scene_id not in expected_scene_ids_set:
                errors.append(f"plan has unknown scene_id {scene_id}")
                continue
            if chapter_no != scene_id_to_chapter.get(scene_id):
                errors.append(f"plan scene_id {scene_id} has wrong chapter_no")
            if plan.get("beats_ref") != beats_path_for_scene(scene_id):
                errors.append(f"plan scene_id {scene_id} has invalid beats_ref")
            plan_ids.add(scene_id)

        missing_plans = set(target_scene_ids) - plan_ids
        if missing_plans:
            errors.append("missing plans for scenes: " + ", ".join(str(s) for s in sorted(missing_plans)))
        extra_plans = plan_ids - set(target_scene_ids)
        if extra_plans:
            errors.append(
                "plans provided for unexpected scenes: "
                + ", ".join(str(s) for s in sorted(extra_plans))
            )

    if errors:
        return None, None, errors

    return index, plans, []


def plan_path_for_scene(scene_id: int) -> str:
    return f"artifacts/scenes/scene_{scene_id:03d}.plan.json"


def beats_path_for_scene(scene_id: int) -> str:
    return f"artifacts/scenes/scene_{scene_id:03d}.beats.json"


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
