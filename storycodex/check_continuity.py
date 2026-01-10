from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from . import llm
from .paths import scene_context_path


@dataclass
class ContinuityResult:
    report: dict[str, Any]
    patch: dict[str, Any]
    meta: dict[str, Any]


def check_continuity(
    root: Path,
    scene_id: int,
    input_kind: str,
    model: str | None,
    force: bool,
    run_id: str | None,
) -> ContinuityResult | None:
    report_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.continuity_report.json"
    patch_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.patch.json"
    meta_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.continuity.meta.json"

    if report_path.exists() and patch_path.exists() and not force:
        return None

    context_path = scene_context_path(root, scene_id)
    if not context_path.exists():
        raise FileNotFoundError(
            f"Missing context at {context_path}; run build-context first."
        )

    prose_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.{input_kind}.md"
    if not prose_path.exists():
        raise FileNotFoundError(
            f"Missing {input_kind} scene at {prose_path}; run write scene first."
        )

    context_text = context_path.read_text()
    prose_text = prose_path.read_text()
    context = json.loads(context_text)

    checker_input = build_checker_input(scene_id, input_kind, context, prose_text)
    chosen_model = model or llm.get_default_model()

    report = generate_report(checker_input, chosen_model)
    errors = validate_json(report, "continuity-report.schema.json")
    if errors:
        report = repair_json(report, errors, "continuity-report.schema.json", chosen_model)
        errors = validate_json(report, "continuity-report.schema.json")
        if errors:
            raise ValueError("Continuity report failed validation")

    patch = generate_patch(report, checker_input, chosen_model)
    errors = validate_json(patch, "scene-patch.schema.json")
    if errors:
        patch = repair_json(patch, errors, "scene-patch.schema.json", chosen_model)
        errors = validate_json(patch, "scene-patch.schema.json")
        if errors:
            raise ValueError("Patch plan failed validation")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    patch_path.write_text(json.dumps(patch, indent=2, sort_keys=True) + "\n")

    backend_used, _ = llm.resolve_backend(llm.get_base_url(), llm.get_backend_setting())
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": chosen_model,
        "backend": backend_used,
        "input": input_kind,
        "input_hashes": {
            "context": sha256_text(context_text),
            "prose": sha256_text(prose_text),
        },
        "run_id": run_id,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return ContinuityResult(report=report, patch=patch, meta=meta)


def build_checker_input(
    scene_id: int, input_kind: str, context: dict[str, Any], prose_text: str
) -> dict[str, Any]:
    ringA = context.get("ringA", {})
    ringB = context.get("ringB", {})
    return {
        "scene_id": scene_id,
        "input": input_kind,
        "pov": ringA.get("pov"),
        "tense": ringA.get("tense"),
        "global_constraints": ringA.get("global_constraints", []),
        "beats": [
            {
                "type": beat.get("type"),
                "description": beat.get("description"),
                "must_include": beat.get("must_include", []),
                "must_avoid": beat.get("must_avoid", []),
            }
            for beat in ringB.get("beats", [])
            if isinstance(beat, dict)
        ],
        "locks": [
            {
                "id": lock.get("id"),
                "statement": lock.get("statement"),
                "severity": lock.get("severity"),
                "tags": lock.get("tags", []),
            }
            for lock in ringB.get("continuity_locks", [])
            if isinstance(lock, dict)
        ],
        "prose": prose_text,
    }


def generate_report(checker_input: dict[str, Any], model: str) -> dict[str, Any]:
    prompt = [
        {
            "role": "system",
            "content": "You are a mechanical continuity checker. Output JSON only.",
        },
        {
            "role": "user",
            "content": build_report_prompt(checker_input),
        },
    ]
    content = llm.chat(prompt, model, temperature=0.1, max_tokens=2000)
    parsed = parse_json_or_none(content)
    if parsed is None:
        raise ValueError("Continuity report is not valid JSON")
    return parsed


def generate_patch(
    report: dict[str, Any], checker_input: dict[str, Any], model: str
) -> dict[str, Any]:
    prompt = [
        {
            "role": "system",
            "content": "You are a mechanical patch planner. Output JSON only.",
        },
        {
            "role": "user",
            "content": build_patch_prompt(report, checker_input),
        },
    ]
    content = llm.chat(prompt, model, temperature=0.1, max_tokens=1500)
    parsed = parse_json_or_none(content)
    if parsed is None:
        raise ValueError("Patch plan is not valid JSON")
    return parsed


def build_report_prompt(checker_input: dict[str, Any]) -> str:
    payload = json.dumps(checker_input, indent=2, sort_keys=True)
    return (
        "Analyze the prose for beat coverage, continuity locks, POV, and tense. "
        "Return JSON only matching continuity-report.schema.json. "
        "For each beat, include coverage, evidence, and notes. "
        "For each lock, include pass/fail/unclear with evidence. "
        "Also note any POV/tense issues.\n\n"
        "Checker input JSON:\n"
        f"{payload}"
    )


def build_patch_prompt(report: dict[str, Any], checker_input: dict[str, Any]) -> str:
    report_json = json.dumps(report, indent=2, sort_keys=True)
    payload = json.dumps(checker_input, indent=2, sort_keys=True)
    return (
        "Generate a patch plan JSON matching scene-patch.schema.json. "
        "For each must-fix or uncovered beat, propose a minimal operation. "
        "Use target anchors as short exact substrings or PARAGRAPH:<n>. "
        "Include must_preserve with beat order and lock constraints.\n\n"
        "Continuity report JSON:\n"
        f"{report_json}\n\n"
        "Checker input JSON:\n"
        f"{payload}"
    )


def validate_json(payload: dict[str, Any], schema_name: str) -> list[str]:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    schema = load_schema(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    return [error.message for error in validator.iter_errors(payload)]


def repair_json(payload: dict[str, Any], errors: list[str], schema_name: str, model: str) -> dict[str, Any]:
    error_text = "\n".join(f"- {error}" for error in errors)
    prompt = [
        {"role": "system", "content": "You must output valid JSON only."},
        {
            "role": "user",
            "content": (
                "Fix the JSON to match the schema. Return JSON only.\n"
                f"Schema: {schema_name}\n"
                f"Errors:\n{error_text}\n\n"
                f"Invalid JSON:\n{json.dumps(payload, indent=2, sort_keys=True)}"
            ),
        },
    ]
    content = llm.chat(prompt, model, temperature=0.1, max_tokens=1200)
    parsed = parse_json_or_none(content)
    if parsed is None:
        raise ValueError("Repair output is not valid JSON")
    return parsed


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


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
