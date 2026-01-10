import json

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.check_continuity import load_schema


jsonschema = pytest.importorskip("jsonschema")


def write_context(root, scene_id=1):
    context = {
        "scene_id": scene_id,
        "build": {
            "created_at": "2025-01-01T00:00:00Z",
            "budget_tokens": 6500,
            "resolution_strategy": "auto",
            "include": "all",
            "sources": [
                {"artifact_id": "inputs/story_spec.json", "resolution_used": "tiny"}
            ],
        },
        "ringA": {
            "premise": "Test premise",
            "tone": ["quiet"],
            "pov": "first",
            "tense": "past",
            "global_constraints": [],
            "style_rules": ["Keep it tight."],
        },
        "ringB": {
            "scene_goal": "Goal",
            "setting": {
                "location": {"id": "dock", "name": "dock", "constraints": []},
                "time": "night",
                "mood_tags": ["quiet"],
            },
            "cast": [],
            "beats": [
                {"type": "entry", "description": "Enters."},
                {"type": "turn", "description": "Finds clue."},
            ],
            "continuity_locks": [
                {
                    "id": "lock-1",
                    "statement": "Must keep the box intact",
                    "severity": "must",
                    "tags": ["box"],
                }
            ],
        },
        "ringC": {
            "prior_scene_summary": "N/A",
            "open_threads": [],
            "relevant_facts": [],
            "glossary": [],
        },
    }
    path = root / "artifacts" / "scenes" / f"scene_{scene_id:03d}.context.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context))


def write_draft(root, scene_id=1):
    out_dir = root / "out" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"scene_{scene_id:03d}.draft.md").write_text("Draft text.")


def test_check_continuity_writes_outputs(tmp_path, monkeypatch):
    write_context(tmp_path)
    write_draft(tmp_path)

    report = {
        "scene_id": 1,
        "input": "draft",
        "summary": "OK",
        "beat_coverage": [
            {
                "beat_index": 0,
                "beat_type": "entry",
                "beat_description": "Enters.",
                "covered": True,
                "evidence": "Draft text",
                "notes": "",
            }
        ],
        "lock_checks": [
            {
                "lock_id": "lock-1",
                "severity": "must",
                "statement": "Must keep the box intact",
                "status": "pass",
                "evidence": "Draft text",
                "notes": "",
            }
        ],
        "other_issues": [],
        "verdict": {"must_fixes": 0, "should_fixes": 0, "ready_for_polish": True},
    }

    patch = {
        "scene_id": 1,
        "input": "draft",
        "operations": [],
    }

    calls = {"count": 0}

    def fake_chat(messages, model, temperature=0.1, max_tokens=None):
        calls["count"] += 1
        return json.dumps(report) if calls["count"] == 1 else json.dumps(patch)

    monkeypatch.setattr("storycodex.check_continuity.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(
        app, ["check", "continuity", "--root", str(tmp_path), "--scene", "1"]
    )

    assert result.exit_code == 0

    report_path = tmp_path / "out" / "scenes" / "scene_001.continuity_report.json"
    patch_path = tmp_path / "out" / "scenes" / "scene_001.patch.json"
    meta_path = tmp_path / "out" / "scenes" / "scene_001.continuity.meta.json"

    assert report_path.exists()
    assert patch_path.exists()
    assert meta_path.exists()

    report_data = json.loads(report_path.read_text())
    patch_data = json.loads(patch_path.read_text())

    schema_report = load_schema("continuity-report.schema.json")
    schema_patch = load_schema("scene-patch.schema.json")
    jsonschema.Draft202012Validator(schema_report).validate(report_data)
    jsonschema.Draft202012Validator(schema_patch).validate(patch_data)


def test_check_continuity_cache_skip(tmp_path, monkeypatch):
    write_context(tmp_path)
    write_draft(tmp_path)

    out_dir = tmp_path / "out" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scene_001.continuity_report.json").write_text("{}")
    (out_dir / "scene_001.patch.json").write_text("{}")

    called = {"value": False}

    def fake_chat(messages, model, temperature=0.1, max_tokens=None):
        called["value"] = True
        return "{}"

    monkeypatch.setattr("storycodex.check_continuity.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(
        app, ["check", "continuity", "--root", str(tmp_path), "--scene", "1"]
    )

    assert result.exit_code == 0
    assert called["value"] is False


def test_check_continuity_missing_inputs(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app, ["check", "continuity", "--root", str(tmp_path), "--scene", "1"]
    )
    assert result.exit_code == 1
