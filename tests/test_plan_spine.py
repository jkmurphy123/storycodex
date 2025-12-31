import json

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.plan_spine import load_schema


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


def test_plan_spine_writes_output(tmp_path, monkeypatch):
    jsonschema = pytest.importorskip("jsonschema")
    write_story_spec(tmp_path)

    spine_json = json.dumps(
        {
            "acts": [
                {
                    "act_no": 1,
                    "summary": "Setup",
                    "chapters": [
                        {
                            "chapter_no": 1,
                            "goal": "Goal",
                            "turning_points": ["Inciting"],
                            "scenes": [1],
                            "end_hook": "Hook",
                        },
                        {
                            "chapter_no": 2,
                            "goal": "Goal 2",
                            "turning_points": ["Turn"],
                            "scenes": [2],
                        },
                    ],
                }
            ]
        }
    )

    def fake_chat_completion(messages, model):
        return spine_json

    monkeypatch.setattr("storycodex.plan_spine.llm.chat_completion", fake_chat_completion)

    runner = CliRunner()
    result = runner.invoke(app, ["plan", "spine", "--root", str(tmp_path)])

    assert result.exit_code == 0

    spine_path = tmp_path / "artifacts" / "plot" / "spine.json"
    meta_path = tmp_path / "artifacts" / "plot" / "spine.meta.json"
    assert spine_path.exists()
    assert meta_path.exists()

    spine = json.loads(spine_path.read_text())
    schema = load_schema()
    jsonschema.Draft202012Validator(schema).validate(spine)


def test_plan_spine_cache_skip(tmp_path, monkeypatch):
    write_story_spec(tmp_path)

    spine_path = tmp_path / "artifacts" / "plot" / "spine.json"
    spine_path.parent.mkdir(parents=True, exist_ok=True)
    spine_path.write_text("{}")

    called = {"value": False}

    def fake_chat_completion(messages, model):
        called["value"] = True
        return "{}"

    monkeypatch.setattr("storycodex.plan_spine.llm.chat_completion", fake_chat_completion)

    runner = CliRunner()
    result = runner.invoke(app, ["plan", "spine", "--root", str(tmp_path)])

    assert result.exit_code == 0
    assert called["value"] is False
