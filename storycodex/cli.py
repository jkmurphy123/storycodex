from __future__ import annotations

import json
from pathlib import Path

import typer

from .paths import (
    defaults_spec_path,
    ensure_dirs,
    inputs_manifest_path,
    inputs_spec_path,
    registry_path,
    root_path,
    seed_report_path,
)
from .seed_apply import apply_seeds, write_outputs

app = typer.Typer(help="StoryCodex CLI")
seed_app = typer.Typer(help="Seed operations")
app.add_typer(seed_app, name="seed")


DEFAULT_STORY_SPEC = {
    "title": "Untitled Story",
    "logline": "A short logline.",
    "genre": ["fiction"],
    "tone": ["neutral"],
    "target_length": {"unit": "words", "value": 1000},
    "pov": "first",
    "tense": "past",
    "constraints": {"must": [], "must_not": []},
}


def write_json(path: Path, payload: dict, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {path} without --force")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def ensure_writable(paths: list[Path], force: bool) -> None:
    for path in paths:
        if path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite {path} without --force")


@app.command("init")
def init(
    root: str = typer.Option(".", "--root", help="Root directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Initialize a StoryCodex workspace."""
    root_dir = root_path(root)
    ensure_dirs(root_dir)

    try:
        write_json(defaults_spec_path(root_dir), DEFAULT_STORY_SPEC, force)
        write_json(registry_path(root_dir), {"version": 1, "artifacts": []}, force)
    except FileExistsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(f"Initialized StoryCodex at {root_dir}", fg=typer.colors.GREEN)


@seed_app.command("apply")
def seed_apply(
    root: str = typer.Option(".", "--root", help="Root directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    json_output: bool = typer.Option(False, "--json", help="Print merged story spec JSON"),
) -> None:
    """Apply seed overrides and write resolved inputs."""
    root_dir = root_path(root)

    output_paths = [
        inputs_spec_path(root_dir),
        inputs_manifest_path(root_dir),
        seed_report_path(root_dir),
    ]
    try:
        ensure_writable(output_paths, force)
        result = apply_seeds(root_dir)
        write_outputs(root_dir, result)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(result.merged_spec, indent=2, sort_keys=True))
    else:
        typer.secho("Seeds applied.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
