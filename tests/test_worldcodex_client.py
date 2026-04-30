from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.plan_scenes import build_prompt, compact_worldcodex_context
from storycodex.worldcodex_client import (
    CommandResult,
    WorldCodexClient,
    WorldCodexClientError,
    get_worldcodex_timeout_seconds,
)


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = results
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def __call__(self, args: Sequence[str], timeout_seconds: int) -> CommandResult:
        self.calls.append((tuple(args), timeout_seconds))
        if not self.results:
            raise AssertionError(f"Unexpected command: {args}")
        return self.results.pop(0)


def test_export_context_builds_worldcodex_command_and_parses_json() -> None:
    runner = FakeRunner(
        [
            CommandResult(
                args=(),
                returncode=0,
                stdout='{"metadata":{"world_id":"titan-osa"},"characters":[]}',
                stderr="",
            )
        ]
    )
    client = WorldCodexClient(world="titan-osa", cli="world", timeout_seconds=12, runner=runner)

    payload = client.export_context(
        "story-context",
        location_id="place.harbor",
        character_id="character.elara",
        faction_id="org.council",
        tag="main-plot",
        canon_tier="established",
    )

    assert payload["metadata"]["world_id"] == "titan-osa"
    assert runner.calls == [
        (
            (
                "world",
                "export",
                "titan-osa",
                "story-context",
                "--location",
                "place.harbor",
                "--character",
                "character.elara",
                "--faction",
                "org.council",
                "--tag",
                "main-plot",
                "--canon-tier",
                "established",
            ),
            12,
        )
    ]


def test_export_context_rejects_invalid_json() -> None:
    runner = FakeRunner([CommandResult(args=(), returncode=0, stdout="not json", stderr="")])
    client = WorldCodexClient(world="titan-osa", runner=runner)

    with pytest.raises(WorldCodexClientError, match="invalid JSON"):
        client.export_context("story-context")


def test_export_context_requires_json_object() -> None:
    runner = FakeRunner([CommandResult(args=(), returncode=0, stdout='["bad"]', stderr="")])
    client = WorldCodexClient(world="titan-osa", runner=runner)

    with pytest.raises(WorldCodexClientError, match="must return a JSON object"):
        client.export_context("story-context")


def test_patch_commands_build_expected_arguments() -> None:
    runner = FakeRunner(
        [
            CommandResult(args=(), returncode=0, stdout="valid", stderr=""),
            CommandResult(args=(), returncode=0, stdout="preview", stderr=""),
            CommandResult(args=(), returncode=0, stdout="applied", stderr=""),
        ]
    )
    client = WorldCodexClient(world="titan-osa", cli="/opt/world", timeout_seconds=30, runner=runner)
    patch_path = Path("/tmp/patch.json")

    assert client.validate_patch(patch_path).stdout == "valid"
    assert client.preview_patch(patch_path).stdout == "preview"
    assert client.apply_patch(patch_path).stdout == "applied"
    assert runner.calls == [
        (("/opt/world", "patch", "validate", "titan-osa", "/tmp/patch.json"), 30),
        (("/opt/world", "patch", "preview", "titan-osa", "/tmp/patch.json"), 30),
        (("/opt/world", "patch", "apply", "titan-osa", "/tmp/patch.json"), 30),
    ]


def test_nonzero_command_raises_useful_error() -> None:
    runner = FakeRunner([CommandResult(args=(), returncode=2, stdout="", stderr="schema mismatch")])
    client = WorldCodexClient(world="titan-osa", runner=runner)

    with pytest.raises(WorldCodexClientError, match="schema mismatch"):
        client.validate_patch(Path("/tmp/patch.json"))


def test_timeout_is_reported_as_client_error() -> None:
    def runner(args: Sequence[str], timeout_seconds: int) -> CommandResult:
        raise subprocess.TimeoutExpired(args, timeout_seconds)

    client = WorldCodexClient(world="titan-osa", timeout_seconds=1, runner=runner)

    with pytest.raises(WorldCodexClientError, match="timed out"):
        client.export_context("story-context")


def test_timeout_env_validation(monkeypatch) -> None:
    monkeypatch.setenv("STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS", "9")
    assert get_worldcodex_timeout_seconds() == 9

    monkeypatch.setenv("STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match=">= 1"):
        get_worldcodex_timeout_seconds()


def test_world_export_cli_writes_cache(tmp_path, monkeypatch) -> None:
    class FakeClient:
        def export_context(self, context, **kwargs):
            return {
                "metadata": {"world_id": "titan-osa", "export_type": context},
                "kwargs": kwargs,
            }

    monkeypatch.setattr("storycodex.cli.build_worldcodex_client", lambda world=None: FakeClient())
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "world",
            "export",
            "--root",
            str(tmp_path),
            "--context",
            "story-context",
            "--world",
            "titan-osa",
            "--character",
            "character.elara",
        ],
    )

    assert result.exit_code == 0
    output_path = tmp_path / "artifacts" / "worldcodex" / "story-context.json"
    assert output_path.exists()
    payload = __import__("json").loads(output_path.read_text())
    assert payload["metadata"]["world_id"] == "titan-osa"
    assert payload["kwargs"]["character_id"] == "character.elara"


def test_plan_scenes_prompt_includes_compact_worldcodex_context() -> None:
    context = {
        "metadata": {"world_id": "titan-osa", "source_atom_ids": ["place.glass_harbor"]},
        "places": [{"id": "place.glass_harbor", "type": "place", "name": "Glass Harbor", "summary": "A port."}],
        "characters": [{"id": "character.elara", "type": "character", "name": "Elara Myung"}],
        "relationships": [{"subject": "character.elara", "predicate": "works_in", "object": "place.glass_harbor"}],
    }

    compact = compact_worldcodex_context(context)
    prompt = build_prompt(
        {
            "title": "Test",
            "logline": "A test.",
            "genre": ["fiction"],
            "tone": ["tense"],
            "target_length": {"unit": "words", "value": 1000},
            "pov": "close_third",
            "tense": "past",
            "constraints": {"must": [], "must_not": []},
        },
        {"acts": [{"act_no": 1, "summary": "Setup", "chapters": [{"chapter_no": 1, "goal": "", "turning_points": [], "scenes": [1]}]}]},
        None,
        None,
        context,
    )

    user_prompt = prompt[-1]["content"]
    assert compact["places"][0]["id"] == "place.glass_harbor"
    assert "WorldCodex context JSON" in user_prompt
    assert "place.glass_harbor" in user_prompt
    assert "character.elara" in user_prompt
    assert "setting.location_id must be that place atom ID" in user_prompt
