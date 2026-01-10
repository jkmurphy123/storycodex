from __future__ import annotations

import json
from pathlib import Path

import typer

from .defaults import (
    DEFAULT_PLOT_INTENT,
    DEFAULT_STORY_SPEC,
    DEFAULT_STYLE_PROFILE_EXAMPLE,
)
from .paths import (
    defaults_plot_intent_path,
    defaults_spec_path,
    ensure_dirs,
    inputs_manifest_path,
    inputs_plot_intent_path,
    inputs_spec_path,
    plot_spine_path,
    registry_path,
    root_path,
    seed_report_path,
    seed_style_profile_example_path,
)
from .seed_apply import apply_seeds, write_outputs
from .plan_spine import plan_spine as run_plan_spine
from .plan_scenes import plan_scenes as run_plan_scenes
from .plan_beats import plan_beats as run_plan_beats
from .build_context import build_context as run_build_context
from .write_scene import write_scene as run_write_scene
from .check_continuity import check_continuity as run_check_continuity

app = typer.Typer(help="StoryCodex CLI")
seed_app = typer.Typer(help="Seed operations")
plan_app = typer.Typer(help="Planning operations")
write_app = typer.Typer(help="Writing operations")
check_app = typer.Typer(help="Check operations")
app.add_typer(seed_app, name="seed")
app.add_typer(plan_app, name="plan")
app.add_typer(write_app, name="write")
app.add_typer(check_app, name="check")


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
        write_json(defaults_plot_intent_path(root_dir), DEFAULT_PLOT_INTENT, force)
        example_path = seed_style_profile_example_path(root_dir)
        if force or not example_path.exists():
            write_json(example_path, DEFAULT_STYLE_PROFILE_EXAMPLE, force=True)
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
        inputs_plot_intent_path(root_dir),
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


@plan_app.command("spine")
def plan_spine(
    root: str = typer.Option(".", "--root", help="Root directory"),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run identifier"),
    json_output: bool = typer.Option(False, "--json", help="Print plot spine JSON"),
) -> None:
    """Plan a plot spine using LLM guidance."""
    root_dir = root_path(root)
    output_path = plot_spine_path(root_dir)
    if output_path.exists() and not force:
        return

    try:
        result = run_plan_spine(root_dir, model, force, run_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result and json_output:
        typer.echo(json.dumps(result.spine, indent=2, sort_keys=True))
    elif result:
        typer.secho("Plot spine generated.", fg=typer.colors.GREEN)


@plan_app.command("scenes")
def plan_scenes(
    root: str = typer.Option(".", "--root", help="Root directory"),
    chapter: int | None = typer.Option(None, "--chapter", help="Chapter number"),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run identifier"),
    json_output: bool = typer.Option(False, "--json", help="Print scenes index JSON"),
) -> None:
    """Plan scenes and scene index using LLM guidance."""
    root_dir = root_path(root)
    try:
        result = run_plan_scenes(root_dir, chapter, model, force, run_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result is None:
        return

    if json_output:
        typer.echo(json.dumps(result.index, indent=2, sort_keys=True))
    else:
        typer.secho("Scenes planned.", fg=typer.colors.GREEN)


@plan_app.command("beats")
def plan_beats(
    root: str = typer.Option(".", "--root", help="Root directory"),
    scene: int = typer.Option(..., "--scene", help="Scene id"),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run identifier"),
    json_output: bool = typer.Option(False, "--json", help="Print scene beats JSON"),
) -> None:
    """Plan beats for a specific scene."""
    if scene < 1:
        typer.secho("--scene must be >= 1", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    root_dir = root_path(root)
    try:
        result = run_plan_beats(root_dir, scene, model, force, run_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result is None:
        return

    if json_output:
        typer.echo(json.dumps(result.beats, indent=2, sort_keys=True))
    else:
        typer.secho("Scene beats planned.", fg=typer.colors.GREEN)


@app.command("build-context")
def build_context(
    root: str = typer.Option(".", "--root", help="Root directory"),
    scene: int = typer.Option(..., "--scene", help="Scene id"),
    budget: int = typer.Option(6500, "--budget", help="Token budget"),
    resolution: str = typer.Option(
        "auto", "--resolution", help="Resolution: auto|tiny|medium|full"
    ),
    include: str = typer.Option(
        "all", "--include", help="Include: ringA|ringB|ringC|all"
    ),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run identifier"),
    json_output: bool = typer.Option(False, "--json", help="Print context JSON"),
) -> None:
    """Build a scene context packet for prose drafting."""
    if scene < 1:
        typer.secho("--scene must be >= 1", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if budget < 1000:
        typer.secho("--budget must be >= 1000", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if resolution not in {"auto", "tiny", "medium", "full"}:
        typer.secho("--resolution must be auto|tiny|medium|full", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if include not in {"ringA", "ringB", "ringC", "all"}:
        typer.secho("--include must be ringA|ringB|ringC|all", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    root_dir = root_path(root)
    try:
        result = run_build_context(
            root_dir, scene, budget, resolution, include, model, force, run_id
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result is None:
        return

    if json_output:
        typer.echo(json.dumps(result.context, indent=2, sort_keys=True))
    else:
        typer.secho("Context packet built.", fg=typer.colors.GREEN)


@write_app.command("scene")
def write_scene(
    root: str = typer.Option(".", "--root", help="Root directory"),
    scene: int = typer.Option(..., "--scene", help="Scene id"),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    length: str = typer.Option("medium", "--length", help="Length: short|medium|long"),
    target_words: int | None = typer.Option(None, "--target-words", help="Target word count"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run identifier"),
    json_output: bool = typer.Option(False, "--json", help="Print draft text"),
) -> None:
    """Write a scene draft using the context packet."""
    if scene < 1:
        typer.secho("--scene must be >= 1", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if length not in {"short", "medium", "long"}:
        typer.secho("--length must be short|medium|long", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if target_words is not None and target_words < 1:
        typer.secho("--target-words must be >= 1", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    root_dir = root_path(root)
    try:
        result = run_write_scene(
            root_dir,
            scene,
            model,
            length,
            target_words,
            force,
            run_id,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result is None:
        return

    if json_output:
        typer.echo(result)
    else:
        typer.secho("Scene draft written.", fg=typer.colors.GREEN)


@check_app.command("continuity")
def check_continuity(
    root: str = typer.Option(".", "--root", help="Root directory"),
    scene: int = typer.Option(..., "--scene", help="Scene id"),
    input_kind: str = typer.Option("draft", "--input", help="draft|final"),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing outputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run identifier"),
    json_output: bool = typer.Option(False, "--json", help="Print report JSON"),
) -> None:
    """Check continuity against beats and locks."""
    if scene < 1:
        typer.secho("--scene must be >= 1", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if input_kind not in {"draft", "final"}:
        typer.secho("--input must be draft|final", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    root_dir = root_path(root)
    try:
        result = run_check_continuity(
            root_dir, scene, input_kind, model, force, run_id
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result is None:
        return

    if json_output:
        typer.echo(json.dumps(result.report, indent=2, sort_keys=True))
    else:
        typer.secho("Continuity check complete.", fg=typer.colors.GREEN)


def main():
    app()

if __name__ == "__main__":
    main()
