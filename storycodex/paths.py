from __future__ import annotations

from pathlib import Path


def root_path(root: str | None) -> Path:
    return Path(root or ".").resolve()


def ensure_dirs(root: Path) -> None:
    for rel in [
        "seeds",
        "artifacts",
        "artifacts/defaults",
        "artifacts/inputs",
        "out",
    ]:
        path = root / rel
        if path.exists() and not path.is_dir():
            raise ValueError(f"Expected directory at {path}, found a file")
        path.mkdir(parents=True, exist_ok=True)


def defaults_spec_path(root: Path) -> Path:
    return root / "artifacts" / "defaults" / "story_spec.json"


def registry_path(root: Path) -> Path:
    return root / "artifacts" / "registry.json"


def seed_override_path(root: Path) -> Path:
    return root / "seeds" / "story_overrides.json"


def inputs_spec_path(root: Path) -> Path:
    return root / "artifacts" / "inputs" / "story_spec.json"


def inputs_manifest_path(root: Path) -> Path:
    return root / "artifacts" / "inputs" / "manifest.json"


def seed_report_path(root: Path) -> Path:
    return root / "out" / "seed_report.json"


def plot_spine_path(root: Path) -> Path:
    return root / "artifacts" / "plot" / "spine.json"


def plot_spine_meta_path(root: Path) -> Path:
    return root / "artifacts" / "plot" / "spine.meta.json"


def scenes_dir(root: Path) -> Path:
    return root / "artifacts" / "scenes"


def scenes_index_path(root: Path) -> Path:
    return scenes_dir(root) / "scenes.json"


def scenes_meta_path(root: Path) -> Path:
    return scenes_dir(root) / "scenes.meta.json"


def scene_plan_path(root: Path, scene_id: int) -> Path:
    return scenes_dir(root) / f"scene_{scene_id:03d}.plan.json"


def scene_beats_path(root: Path, scene_id: int) -> Path:
    return scenes_dir(root) / f"scene_{scene_id:03d}.beats.json"
