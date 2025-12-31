import json

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.plan_scenes import load_schema
from storycodex.paths import scene_plan_path, scenes_index_path


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


def write_spine(root):
    spine = {
        "acts": [
            {
                "act_no": 1,
                "summary": "Setup",
                "chapters": [
                    {"chapter_no": 1, "goal": "", "turning_points": [], "scenes": [1, 2]},
                    {"chapter_no": 2, "goal": "", "turning_points": [], "scenes": [3]},
                ],
            }
        ]
    }
    path = root / "artifacts" / "plot" / "spine.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spine))


def build_wrapper():
    index = {
        "version": 1,
        "scenes": [
            {
                "scene_id": 1,
                "chapter_no": 1,
                "title": "Arrival",
                "plan_path": "artifacts/scenes/scene_001.plan.json",
                "beats_path": "artifacts/scenes/scene_001.beats.json",
            },
            {
                "scene_id": 2,
                "chapter_no": 1,
                "title": "Signal",
                "plan_path": "artifacts/scenes/scene_002.plan.json",
                "beats_path": "artifacts/scenes/scene_002.beats.json",
            },
            {
                "scene_id": 3,
                "chapter_no": 2,
                "title": "Contact",
                "plan_path": "artifacts/scenes/scene_003.plan.json",
                "beats_path": "artifacts/scenes/scene_003.beats.json",
            },
        ],
    }
    plans = [
        {
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
        },
        {
            "scene_id": 2,
            "chapter_no": 1,
            "title": "Signal",
            "setting": {
                "location_id": "comm_array",
                "time": "late",
                "mood_tags": ["uneasy"],
            },
            "cast": ["Elias"],
            "goal": "Discover anomaly",
            "stakes": "Safety risk",
            "beats_ref": "artifacts/scenes/scene_002.beats.json",
        },
        {
            "scene_id": 3,
            "chapter_no": 2,
            "title": "Contact",
            "setting": {
                "location_id": "core_lab",
                "time": "night",
                "mood_tags": ["tense"],
            },
            "cast": ["Elias", "Lyra"],
            "goal": "Make contact",
            "stakes": "Trust",
            "beats_ref": "artifacts/scenes/scene_003.beats.json",
        },
    ]
    return {"index": index, "plans": plans}


def test_plan_scenes_writes_outputs(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_spine(tmp_path)

    wrapper = build_wrapper()

    def fake_chat(messages, model, temperature=0.4, max_tokens=None):
        return json.dumps(wrapper)

    monkeypatch.setattr("storycodex.plan_scenes.llm.chat", fake_chat)
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")

    runner = CliRunner()
    result = runner.invoke(app, ["plan", "scenes", "--root", str(tmp_path)])

    assert result.exit_code == 0

    index_path = scenes_index_path(tmp_path)
    assert index_path.exists()

    index = json.loads(index_path.read_text())
    schema_index = load_schema("scenes-index.schema.json")
    jsonschema.Draft202012Validator(schema_index).validate(index)

    schema_plan = load_schema("scene-plan.schema.json")
    for scene_id in [1, 2, 3]:
        plan_path = scene_plan_path(tmp_path, scene_id)
        assert plan_path.exists()
        plan = json.loads(plan_path.read_text())
        jsonschema.Draft202012Validator(schema_plan).validate(plan)


def test_plan_scenes_cache_skip(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_spine(tmp_path)

    index_path = scenes_index_path(tmp_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{}")

    called = {"value": False}

    def fake_chat(messages, model, temperature=0.4, max_tokens=None):
        called["value"] = True
        return "{}"

    monkeypatch.setattr("storycodex.plan_scenes.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["plan", "scenes", "--root", str(tmp_path)])

    assert result.exit_code == 0
    assert called["value"] is False


def test_plan_scenes_chapter_only(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_spine(tmp_path)

    wrapper = build_wrapper()
    wrapper["plans"] = [wrapper["plans"][2]]

    def fake_chat(messages, model, temperature=0.4, max_tokens=None):
        return json.dumps(wrapper)

    monkeypatch.setattr("storycodex.plan_scenes.llm.chat", fake_chat)
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")

    existing_path = scene_plan_path(tmp_path, 1)
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text("{\"keep\": true}")

    runner = CliRunner()
    result = runner.invoke(
        app, ["plan", "scenes", "--root", str(tmp_path), "--chapter", "2"]
    )

    assert result.exit_code == 0
    assert json.loads(existing_path.read_text()) == {"keep": True}

    chapter_plan = scene_plan_path(tmp_path, 3)
    assert chapter_plan.exists()
