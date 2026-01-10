from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_PLOT_INTENT
from .merge import merge
from .paths import (
    defaults_plot_intent_path,
    defaults_spec_path,
    inputs_manifest_path,
    inputs_plot_intent_path,
    inputs_spec_path,
    seed_plot_override_path,
    seed_override_path,
    seed_report_path,
)


@dataclass
class SeedResult:
    merged_spec: dict[str, Any]
    merged_plot_intent: dict[str, Any]
    seeds_used: list[dict[str, str]]
    changed_keys: list[str]
    plot_changed_keys: list[str]


def apply_seeds(root: Path) -> SeedResult:
    base_path = defaults_spec_path(root)
    if not base_path.exists():
        raise FileNotFoundError(f"Missing base spec at {base_path}")

    base_spec = json.loads(base_path.read_text())
    base_plot_path = defaults_plot_intent_path(root)
    if base_plot_path.exists():
        base_plot_intent = json.loads(base_plot_path.read_text())
    else:
        base_plot_intent = DEFAULT_PLOT_INTENT

    override_path = seed_override_path(root)
    plot_override_path = seed_plot_override_path(root)
    seeds_used: list[dict[str, str]] = []

    if override_path.exists():
        override_data = json.loads(override_path.read_text())
        seeds_used.append(
            {
                "path": str(override_path.relative_to(root)),
                "hash": file_hash(override_path),
            }
        )
    else:
        override_data = {}

    if plot_override_path.exists():
        plot_override_data = json.loads(plot_override_path.read_text())
        seeds_used.append(
            {
                "path": str(plot_override_path.relative_to(root)),
                "hash": file_hash(plot_override_path),
            }
        )
    else:
        plot_override_data = {}

    merged = merge(base_spec, override_data)
    changed_keys = sorted(list(diff_keys(base_spec, merged)))

    merged_plot_intent = merge(base_plot_intent, plot_override_data)
    plot_changed_keys = sorted(list(diff_keys(base_plot_intent, merged_plot_intent)))
    validate_plot_intent(merged_plot_intent)

    return SeedResult(
        merged_spec=merged,
        merged_plot_intent=merged_plot_intent,
        seeds_used=seeds_used,
        changed_keys=changed_keys,
        plot_changed_keys=plot_changed_keys,
    )


def write_outputs(root: Path, result: SeedResult) -> None:
    spec_path = inputs_spec_path(root)
    plot_intent_path = inputs_plot_intent_path(root)
    manifest_path = inputs_manifest_path(root)
    report_path = seed_report_path(root)

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    spec_path.write_text(json.dumps(result.merged_spec, indent=2, sort_keys=True) + "\n")
    plot_intent_path.write_text(
        json.dumps(result.merged_plot_intent, indent=2, sort_keys=True) + "\n"
    )
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seeds_used": result.seeds_used,
        "resolved_inputs": {
            "story_spec": str(spec_path.relative_to(root)),
            "plot_intent": str(plot_intent_path.relative_to(root)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    report = {
        "version": 1,
        "changed_keys": result.changed_keys,
        "plot_overrides": {"changed_keys": result.plot_changed_keys},
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def diff_keys(base: Any, merged: Any, prefix: str = "") -> set[str]:
    if base == merged:
        return set()
    if isinstance(base, dict) and isinstance(merged, dict):
        changes: set[str] = set()
        all_keys = base.keys() | merged.keys()
        for key in all_keys:
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            changes |= diff_keys(base.get(key), merged.get(key), next_prefix)
        return changes
    return {prefix}


def validate_plot_intent(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validation") from exc

    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = [error.message for error in validator.iter_errors(payload)]
    if errors:
        error_text = "; ".join(errors)
        raise ValueError(f"Plot intent validation failed: {error_text}")


def load_schema() -> dict[str, Any]:
    schema_path = resources.files("storycodex.schemas").joinpath(
        "plot-intent.schema.json"
    )
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
