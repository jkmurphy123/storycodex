from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .merge import merge
from .paths import (
    defaults_spec_path,
    inputs_manifest_path,
    inputs_spec_path,
    seed_override_path,
    seed_report_path,
)


@dataclass
class SeedResult:
    merged_spec: dict[str, Any]
    seeds_used: list[dict[str, str]]
    changed_keys: list[str]


def apply_seeds(root: Path) -> SeedResult:
    base_path = defaults_spec_path(root)
    if not base_path.exists():
        raise FileNotFoundError(f"Missing base spec at {base_path}")

    base_spec = json.loads(base_path.read_text())
    override_path = seed_override_path(root)
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

    merged = merge(base_spec, override_data)
    changed_keys = sorted(list(diff_keys(base_spec, merged)))
    return SeedResult(merged_spec=merged, seeds_used=seeds_used, changed_keys=changed_keys)


def write_outputs(root: Path, result: SeedResult) -> None:
    spec_path = inputs_spec_path(root)
    manifest_path = inputs_manifest_path(root)
    report_path = seed_report_path(root)

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    spec_path.write_text(json.dumps(result.merged_spec, indent=2, sort_keys=True) + "\n")
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seeds_used": result.seeds_used,
        "resolved_inputs": {"story_spec": str(spec_path.relative_to(root))},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    report = {
        "version": 1,
        "changed_keys": result.changed_keys,
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
