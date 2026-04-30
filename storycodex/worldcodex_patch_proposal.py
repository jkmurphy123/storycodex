from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import llm
from .check_continuity import parse_json_or_none
from .paths import scene_context_path
from .worldcodex_client import WorldCodexClientError, build_worldcodex_client

PATCH_SCHEMA_VERSION = "worldcodex.patch.v1"
SUPPORTED_OPS = {
    "add_atom",
    "update_atom",
    "deprecate_atom",
    "add_relationship",
    "update_relationship",
    "add_timeline_event",
    "resolve_conflict",
}
ATOM_ID_PATTERN = re.compile(
    r"\b(?:character|place|faction|org|organization|event|conflict|artifact|concept)\.[A-Za-z0-9_.:-]+\b"
)


@dataclass
class WorldPatchProposalResult:
    patch: dict[str, Any]
    meta: dict[str, Any]
    patch_path: Path
    preview: str | None = None


def propose_world_patch(
    root: Path,
    scene_id: int,
    input_kind: str,
    model: str | None,
    force: bool,
    run_id: str | None,
    *,
    preview: bool = False,
    world: str | None = None,
) -> WorldPatchProposalResult | None:
    patch_path = world_patch_path(root, scene_id)
    meta_path = world_patch_meta_path(root, scene_id)
    preview_path = world_patch_preview_path(root, scene_id)

    if patch_path.exists() and not force:
        return None

    context_path = scene_context_path(root, scene_id)
    if not context_path.exists():
        raise FileNotFoundError(f"Missing context at {context_path}; run build-context first.")

    prose_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.{input_kind}.md"
    if not prose_path.exists():
        raise FileNotFoundError(f"Missing {input_kind} scene at {prose_path}; run write scene first.")

    report_path = root / "out" / "scenes" / f"scene_{scene_id:03d}.continuity_report.json"
    continuity_report = load_json_if_exists(report_path)

    context_text = context_path.read_text()
    prose_text = prose_path.read_text()
    context = json.loads(context_text)
    source_atom_ids = collect_worldcodex_atom_ids(context)

    proposal_input = {
        "scene_id": scene_id,
        "input": input_kind,
        "source_atom_ids": source_atom_ids,
        "context": compact_context_for_patch(context),
        "continuity_report": continuity_report,
        "prose": prose_text,
    }
    chosen_model = model or llm.get_default_model()
    patch = generate_world_patch(proposal_input, chosen_model)
    validate_worldcodex_patch(patch)

    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(json.dumps(patch, indent=2, sort_keys=True) + "\n")

    preview_text = None
    if preview:
        try:
            client = build_worldcodex_client(world=world)
            client.validate_patch(patch_path)
            preview_text = client.preview_patch(patch_path).stdout
        except WorldCodexClientError as exc:
            raise RuntimeError(str(exc)) from exc
        preview_path.write_text(preview_text)

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
        "source_atom_ids": source_atom_ids,
        "worldcodex_previewed": preview,
    }
    if report_path.exists():
        meta["input_hashes"]["continuity_report"] = sha256_text(report_path.read_text())
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return WorldPatchProposalResult(patch=patch, meta=meta, patch_path=patch_path, preview=preview_text)


def generate_world_patch(proposal_input: dict[str, Any], model: str) -> dict[str, Any]:
    prompt = [
        {
            "role": "system",
            "content": "You propose durable WorldCodex canon patches. Output JSON only.",
        },
        {
            "role": "user",
            "content": build_world_patch_prompt(proposal_input),
        },
    ]
    content = llm.chat(prompt, model, temperature=0.1, max_tokens=2200)
    parsed = parse_json_or_none(content)
    if parsed is None:
        raise ValueError("WorldCodex patch proposal is not valid JSON")
    return parsed


def build_world_patch_prompt(proposal_input: dict[str, Any]) -> str:
    payload = json.dumps(proposal_input, indent=2, sort_keys=True)
    return (
        "Create a worldcodex.patch.v1 JSON object for durable world changes introduced by this scene. "
        "Only include changes that should become world canon, such as public events, durable relationship "
        "changes, new canonical facts, status changes, or conflict updates. Do not include prose fixes, "
        "beat coverage fixes, style notes, pacing notes, or scene-local internal thoughts. If there are no "
        "durable world changes, return schema_version with an empty operations array.\n\n"
        "Required top-level shape:\n"
        "{\n"
        '  "schema_version": "worldcodex.patch.v1",\n'
        '  "description": "short purpose",\n'
        '  "operations": []\n'
        "}\n\n"
        "Supported operation names: add_atom, update_atom, deprecate_atom, add_relationship, "
        "update_relationship, add_timeline_event, resolve_conflict. Prefer source_atom_ids when updating "
        "existing atoms. Return JSON only.\n\n"
        "Proposal input JSON:\n"
        f"{payload}"
    )


def validate_worldcodex_patch(patch: dict[str, Any]) -> None:
    if not isinstance(patch, dict):
        raise ValueError("WorldCodex patch must be a JSON object")
    if patch.get("schema_version") != PATCH_SCHEMA_VERSION:
        raise ValueError(f"WorldCodex patch schema_version must be {PATCH_SCHEMA_VERSION}")

    operations = patch.get("operations")
    if not isinstance(operations, list):
        raise ValueError("WorldCodex patch operations must be a list")

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"WorldCodex patch operation {index} must be an object")
        op_name = operation.get("op")
        if op_name not in SUPPORTED_OPS:
            raise ValueError(f"Unsupported WorldCodex patch operation {index}: {op_name}")
        validate_worldcodex_operation(index, operation)


def validate_worldcodex_operation(index: int, operation: dict[str, Any]) -> None:
    op_name = operation["op"]
    if op_name in {"add_atom", "add_timeline_event"}:
        atom = operation.get("atom")
        if not isinstance(atom, dict):
            raise ValueError(f"WorldCodex patch operation {index} requires atom object")
        if not atom.get("id") or not atom.get("type"):
            raise ValueError(f"WorldCodex patch operation {index} atom requires id and type")
        if op_name == "add_timeline_event" and atom.get("type") != "event":
            raise ValueError(f"WorldCodex patch operation {index} timeline atom type must be event")
    elif op_name in {"update_atom", "deprecate_atom", "resolve_conflict"}:
        if not operation.get("atom_id"):
            raise ValueError(f"WorldCodex patch operation {index} requires atom_id")
    elif op_name == "add_relationship":
        relationship = operation.get("relationship")
        if not isinstance(relationship, dict):
            raise ValueError(f"WorldCodex patch operation {index} requires relationship object")
        if not relationship.get("subject") or not relationship.get("predicate") or not relationship.get("object"):
            raise ValueError(f"WorldCodex patch operation {index} relationship requires subject, predicate, and object")
    elif op_name == "update_relationship":
        if not operation.get("subject") or not operation.get("predicate") or not operation.get("object"):
            raise ValueError(f"WorldCodex patch operation {index} requires subject, predicate, and object")


def compact_context_for_patch(context: dict[str, Any]) -> dict[str, Any]:
    ring_b = context.get("ringB", {}) if isinstance(context.get("ringB"), dict) else {}
    ring_c = context.get("ringC", {}) if isinstance(context.get("ringC"), dict) else {}
    build = context.get("build", {}) if isinstance(context.get("build"), dict) else {}
    return {
        "scene_id": context.get("scene_id"),
        "build_sources": build.get("sources", []),
        "scene_goal": ring_b.get("scene_goal"),
        "setting": ring_b.get("setting", {}),
        "cast": ring_b.get("cast", []),
        "beats": ring_b.get("beats", []),
        "continuity_locks": ring_b.get("continuity_locks", []),
        "open_threads": ring_c.get("open_threads", []),
        "relevant_facts": ring_c.get("relevant_facts", []),
        "glossary": ring_c.get("glossary", []),
    }


def collect_worldcodex_atom_ids(payload: Any) -> list[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            for match in ATOM_ID_PATTERN.findall(value):
                found.add(match)
            return
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
            return
        if isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return sorted(found)


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def world_patch_path(root: Path, scene_id: int) -> Path:
    return root / "out" / "scenes" / f"scene_{scene_id:03d}.worldcodex_patch.json"


def world_patch_meta_path(root: Path, scene_id: int) -> Path:
    return root / "out" / "scenes" / f"scene_{scene_id:03d}.worldcodex_patch.meta.json"


def world_patch_preview_path(root: Path, scene_id: int) -> Path:
    return root / "out" / "scenes" / f"scene_{scene_id:03d}.worldcodex_patch.preview.txt"


def sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
