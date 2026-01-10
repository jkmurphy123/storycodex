import json

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.plan_beats import load_schema
from storycodex.paths import scene_beats_path, scene_beats_meta_path, scene_plan_path


jsonschema = pytest.importorskip("jsonschema")


def write_story_spec(root):
    spec = {
        "title": "Test Story",
        "logline": "Test logline",
        "genre": ["fantasy"],
        "tone": ["hopeful"],
        "target_length": {"unit": "words", "value": 1200},
        "pov": "first",
        "tense": "past",
        "constraints": {"must": [], "must_not": []},
    }
    path = root / "artifacts" / "inputs" / "story_spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec))


def write_scene_plan(root):
    plan = {
        "scene_id": 1,
        "chapter_no": 1,
        "title": "Arrival",
        "setting": {
            "location_id": "dock_bay",
            "time": "night",
            "mood_tags": ["quiet"],
        },
        "cast": ["Elias"],
        "goal": "Establish tone",
        "stakes": "Isolation deepens",
        "beats_ref": "artifacts/scenes/scene_001.beats.json",
    }
    path = scene_plan_path(root, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan))


def beats_payload():
    return {
        "scene_id": 1,
        "beats": [
            {"type": "entry", "description": "Elias enters the dock."},
            {"type": "orientation", "description": "He checks the lights."},
            {"type": "pressure", "description": "A warning alarm chirps."},
            {"type": "interaction", "description": "He investigates the panel."},
            {"type": "turn", "description": "A hidden message appears."},
            {"type": "exit", "description": "He leaves with the data."},
        ],
    }


def test_plan_beats_writes_output(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)

    def fake_chat(messages, model, temperature=0.4, max_tokens=None):
        return json.dumps(beats_payload())

    monkeypatch.setattr("storycodex.plan_beats.llm.chat", fake_chat)
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")

    runner = CliRunner()
    result = runner.invoke(
        app, ["plan", "beats", "--root", str(tmp_path), "--scene", "1"]
    )

    assert result.exit_code == 0

    beats_path = scene_beats_path(tmp_path, 1)
    meta_path = scene_beats_meta_path(tmp_path, 1)
    assert beats_path.exists()
    assert meta_path.exists()

    beats = json.loads(beats_path.read_text())
    schema = load_schema("scene-beats.schema.json")
    jsonschema.Draft202012Validator(schema).validate(beats)


def test_plan_beats_cache_skip(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)

    beats_path = scene_beats_path(tmp_path, 1)
    beats_path.parent.mkdir(parents=True, exist_ok=True)
    beats_path.write_text("{}")

    called = {"value": False}

    def fake_chat(messages, model, temperature=0.4, max_tokens=None):
        called["value"] = True
        return "{}"

    monkeypatch.setattr("storycodex.plan_beats.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(
        app, ["plan", "beats", "--root", str(tmp_path), "--scene", "1"]
    )

    assert result.exit_code == 0
    assert called["value"] is False


def test_plan_beats_repair(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)

    calls = {"count": 0}

    def fake_chat(messages, model, temperature=0.4, max_tokens=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return "not json"
        return json.dumps(beats_payload())

    monkeypatch.setattr("storycodex.plan_beats.llm.chat", fake_chat)
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")

    runner = CliRunner()
    result = runner.invoke(
        app, ["plan", "beats", "--root", str(tmp_path), "--scene", "1"]
    )

    assert result.exit_code == 0
    beats_path = scene_beats_path(tmp_path, 1)
    assert beats_path.exists()
