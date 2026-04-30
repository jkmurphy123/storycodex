from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.build_context import build_context
from storycodex.paths import scene_beats_path, scene_context_path, scene_plan_path
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


def test_build_context_uses_worldcodex_atoms_for_ring_b_and_c(tmp_path, monkeypatch) -> None:
    story_spec_path = tmp_path / "artifacts" / "inputs" / "story_spec.json"
    story_spec_path.parent.mkdir(parents=True, exist_ok=True)
    story_spec_path.write_text(
        __import__("json").dumps(
            {
                "title": "Test",
                "logline": "A test.",
                "genre": ["fiction"],
                "tone": ["tense"],
                "target_length": {"unit": "words", "value": 1000},
                "pov": "close_third",
                "tense": "past",
                "constraints": {"must": [], "must_not": []},
            }
        )
    )
    scene_plan_path(tmp_path, 1).parent.mkdir(parents=True, exist_ok=True)
    scene_plan_path(tmp_path, 1).write_text(
        __import__("json").dumps(
            {
                "scene_id": 1,
                "chapter_no": 1,
                "title": "Harbor",
                "setting": {"location_id": "place.glass_harbor", "time": "night", "mood_tags": ["tense"]},
                "cast": ["character.elara"],
                "goal": "Find the witness",
                "stakes": "The trail goes cold",
                "beats_ref": "artifacts/scenes/scene_001.beats.json",
            }
        )
    )
    scene_beats_path(tmp_path, 1).write_text(
        __import__("json").dumps(
            {"scene_id": 1, "beats": [{"type": "entry", "description": "Elara enters Glass Harbor."}]}
        )
    )

    class FakeWorldCodexClient:
        def export_context(self, context_type, **kwargs):
            return {
                "metadata": {"world_id": "titan-osa", "source_atom_ids": ["place.glass_harbor", "character.elara"]},
                "places": [
                    {
                        "id": "place.glass_harbor",
                        "type": "place",
                        "name": "Glass Harbor",
                        "summary": "A corporate port district under curfew.",
                        "data": {"constraints": ["Security drones patrol the gantries."]},
                    }
                ],
                "characters": [
                    {
                        "id": "character.elara",
                        "type": "character",
                        "name": "Elara Myung",
                        "summary": "An investigator under pressure.",
                        "data": {
                            "role": "investigator",
                            "voice_tics": ["precise"],
                            "current_state": "exhausted but focused",
                            "wants_now": ["find the witness"],
                            "taboos": ["trusting officials"],
                        },
                    }
                ],
                "relationships": [
                    {"subject": "character.elara", "predicate": "investigates", "object": "place.glass_harbor"}
                ],
                "timeline": [
                    {
                        "id": "event.lockdown",
                        "type": "event",
                        "name": "Harbor lockdown",
                        "summary": "Glass Harbor was sealed after the vote.",
                        "data": {"locations": ["place.glass_harbor"], "participants": ["character.elara"]},
                    }
                ],
                "conflicts": [
                    {
                        "id": "conflict.harbor_access",
                        "type": "conflict",
                        "name": "Harbor access dispute",
                        "summary": "Control of the port remains unresolved.",
                    }
                ],
            }

    monkeypatch.setattr("storycodex.build_context.build_worldcodex_client", lambda world=None: FakeWorldCodexClient())
    monkeypatch.setattr("storycodex.build_context.validate_context", lambda context: [])
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")

    result = build_context(
        tmp_path,
        1,
        6500,
        "auto",
        "all",
        None,
        False,
        None,
        world="titan-osa",
    )

    assert result is not None
    context = __import__("json").loads(scene_context_path(tmp_path, 1).read_text())
    assert context["ringB"]["setting"]["location"]["id"] == "place.glass_harbor"
    assert context["ringB"]["setting"]["location"]["name"] == "Glass Harbor"
    assert "Security drones patrol the gantries." in context["ringB"]["setting"]["location"]["constraints"]
    assert context["ringB"]["cast"][0]["id"] == "character.elara"
    assert context["ringB"]["cast"][0]["role"] == "investigator"
    assert any("Harbor lockdown" in fact for fact in context["ringC"]["relevant_facts"])
    assert any("Harbor access dispute" in thread for thread in context["ringC"]["open_threads"])
    assert any(source["artifact_id"] == "worldcodex" for source in context["build"]["sources"])
