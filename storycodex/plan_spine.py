from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from . import llm
from .paths import inputs_spec_path, plot_spine_meta_path, plot_spine_path


@dataclass
class PlanResult:
    spine: dict[str, Any]
    meta: dict[str, Any]


def plan_spine(
    root: Path,
    model: str | None,
    force: bool,
    run_id: str | None,
) -> PlanResult | None:
    spine_path = plot_spine_path(root)
    if spine_path.exists() and not force:
        return None

    story_spec_path = inputs_spec_path(root)
    if not story_spec_path.exists():
        raise FileNotFoundError(f"Missing story spec at {story_spec_path}")

    story_spec_text = story_spec_path.read_text()
    story_spec = json.loads(story_spec_text)

    chosen_model = model or llm.get_default_model()
    prompt = build_prompt(story_spec)
    content = llm.chat(prompt, chosen_model, temperature=0.4, max_tokens=1500)

    spine = parse_and_validate(content)
    if spine is None:
        repair_prompt = build_repair_prompt(content)
        repaired = llm.chat(repair_prompt, chosen_model, temperature=0.4, max_tokens=1500)
        spine = parse_and_validate(repaired)
        if spine is None:
            raise ValueError("LLM response could not be repaired into valid JSON")

    spine_path.parent.mkdir(parents=True, exist_ok=True)
    spine_path.write_text(json.dumps(spine, indent=2, sort_keys=True) + "\n")

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": chosen_model,
        "input_hash": sha256_text(story_spec_text),
        "run_id": run_id,
    }
    meta_path = plot_spine_meta_path(root)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return PlanResult(spine=spine, meta=meta)


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def build_prompt(story_spec: dict[str, Any]) -> list[dict[str, str]]:
    spec_json = json.dumps(story_spec, indent=2, sort_keys=True)
    instruction = (
        "Generate a plot spine JSON object that matches the schema below. "
        "Return JSON only, no extra text, no markdown fences. Keep "
        "acts/chapters/scenes counts reasonable for the target_length. "
        "Scenes must be sequential integers starting at 1 across the whole "
        "story, and scenes arrays must contain integers only.\n\n"
        "Schema: {acts: [{act_no, summary, chapters: [{chapter_no, goal, "
        "turning_points, scenes, end_hook?}]}]}\n\n"
        "Story spec JSON:\n"
        f"{spec_json}"
    )
    return [
        {"role": "system", "content": "You are a careful story planner."},
        {"role": "user", "content": instruction},
    ]


def build_repair_prompt(invalid_text: str) -> list[dict[str, str]]:
    instruction = (
        "The previous response was invalid. Return ONLY valid JSON (no markdown "
        "fences) that conforms to the plot spine schema: {acts: [{act_no, "
        "summary, chapters: [{chapter_no, goal, turning_points, scenes, "
        "end_hook?}]}]}. Scenes arrays must contain integers only."
        "\nInvalid response:\n"
        f"{invalid_text}"
    )
    return [
        {"role": "system", "content": "You must output valid JSON only."},
        {"role": "user", "content": instruction},
    ]


def parse_and_validate(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        return None
    return data


def load_schema() -> dict[str, Any]:
    schema_path = resources.files("storycodex.schemas").joinpath(
        "plot-spine.schema.json"
    )
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
