import json

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.build_context import load_schema
from storycodex.paths import scene_context_path, scene_context_meta_path, scene_beats_path, scene_plan_path


jsonschema = pytest.importorskip("jsonschema")


def write_story_spec(root):
    spec = {
        "title": "Test Story",
        "logline": "A test logline.",
        "genre": ["fantasy"],
        "tone": ["hopeful"],
        "target_length": {"unit": "words", "value": 1200},
        "pov": "first",
        "tense": "past",
        "constraints": {"must": ["keep it tight"], "must_not": []},
    }
    path = root / "artifacts" / "inputs" / "story_spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec))


def write_scene_plan(root, scene_id=1, chapter_no=1):
    plan = {
        "scene_id": scene_id,
        "chapter_no": chapter_no,
        "title": "Arrival",
        "setting": {
            "location_id": "dock_bay",
            "time": "night",
            "mood_tags": ["quiet"],
        },
        "cast": ["Elias"],
        "goal": "Establish tone",
        "stakes": "Isolation deepens",
        "beats_ref": f"artifacts/scenes/scene_{scene_id:03d}.beats.json",
    }
    path = scene_plan_path(root, scene_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan))


def write_scene_beats(root, scene_id=1):
    beats = {
        "scene_id": scene_id,
        "beats": [
            {"type": "entry", "description": "Elias enters the dock."},
            {"type": "orientation", "description": "He checks the lights."},
            {"type": "pressure", "description": "A warning alarm chirps."},
            {"type": "interaction", "description": "He investigates the panel."},
            {"type": "turn", "description": "A hidden message appears."},
            {"type": "exit", "description": "He leaves with the data."},
        ],
    }
    path = scene_beats_path(root, scene_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(beats))
    return beats


def test_build_context_writes_outputs(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)
    beats = write_scene_beats(tmp_path)

    def fake_chat(messages, model, temperature=0.2, max_tokens=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("storycodex.build_context.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["build-context", "--root", str(tmp_path), "--scene", "1"])

    assert result.exit_code == 0

    context_path = scene_context_path(tmp_path, 1)
    meta_path = scene_context_meta_path(tmp_path, 1)
    assert context_path.exists()
    assert meta_path.exists()

    context = json.loads(context_path.read_text())
    schema = load_schema("scene-context-packet.schema.json")
    jsonschema.Draft202012Validator(schema).validate(context)

    assert context["ringB"]["beats"] == beats["beats"]


def test_build_context_without_style_profile(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)
    write_scene_beats(tmp_path)

    def fake_chat(messages, model, temperature=0.2, max_tokens=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("storycodex.build_context.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["build-context", "--root", str(tmp_path), "--scene", "1"])

    assert result.exit_code == 0
    context = json.loads(scene_context_path(tmp_path, 1).read_text())
    assert context["ringA"]["tone"] == ["hopeful"]
    assert all(
        not rule.startswith("Intent:") for rule in context["ringA"]["style_rules"]
    )


def test_build_context_cache_skip(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)
    write_scene_beats(tmp_path)

    context_path = scene_context_path(tmp_path, 1)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text("{}")

    called = {"value": False}

    def fake_chat(messages, model, temperature=0.2, max_tokens=None):
        called["value"] = True
        return "{}"

    monkeypatch.setattr("storycodex.build_context.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["build-context", "--root", str(tmp_path), "--scene", "1"])

    assert result.exit_code == 0
    assert called["value"] is False


def test_build_context_prior_scene_summary(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path, scene_id=2, chapter_no=1)
    write_scene_beats(tmp_path, scene_id=2)

    out_dir = tmp_path / "out" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scene_001.final.md").write_text("Some prior scene text.")

    def fake_chat(messages, model, temperature=0.2, max_tokens=None):
        return "Short summary."

    monkeypatch.setattr("storycodex.build_context.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["build-context", "--root", str(tmp_path), "--scene", "2"])

    assert result.exit_code == 0
    context = json.loads(scene_context_path(tmp_path, 2).read_text())
    assert context["ringC"]["prior_scene_summary"] == "Short summary."


def test_build_context_includes_plot_intent_constraints(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)
    write_scene_beats(tmp_path)

    plot_intent = {
        "plot_intent": {
            "core_arc": "Learns to trust",
            "themes": ["trust", "belonging"],
            "central_question": "Will they risk it?",
        }
    }
    plot_path = tmp_path / "artifacts" / "inputs" / "plot_intent.json"
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    plot_path.write_text(json.dumps(plot_intent))

    def fake_chat(messages, model, temperature=0.2, max_tokens=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("storycodex.build_context.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["build-context", "--root", str(tmp_path), "--scene", "1"])

    assert result.exit_code == 0
    context = json.loads(scene_context_path(tmp_path, 1).read_text())
    constraints = context["ringA"]["global_constraints"]
    assert "Core arc: Learns to trust" in constraints
    assert "Central question: Will they risk it?" in constraints
    assert "Theme: trust" in context["ringA"]["style_rules"]


def test_build_context_with_style_profile(tmp_path, monkeypatch):
    write_story_spec(tmp_path)
    write_scene_plan(tmp_path)
    write_scene_beats(tmp_path)

    profile = {
        "profile_id": "noir",
        "profile_name": "Noir",
        "intent": "Bleak, taut noir focus.",
        "tone": ["noir"],
        "syntax": {
            "sentence_rhythm": "Short punches.",
            "paragraphing": "One paragraph per beat.",
        },
        "sensory": {"priority_order": ["sound", "touch"], "motifs": ["rust"]},
        "dialogue": {"style": "Clipped.", "subtext_rule": "Say less."},
        "scene_rules": {"must_include": ["shadow"], "must_not": []},
        "horror_engine": {"taboos": ["gratuitous gore"]},
        "output_controls": {
            "metaphor_density": "low",
            "exposition_throttle": "tight",
            "violence": "medium",
            "gore": "low",
        },
    }
    profile_path = tmp_path / "seeds" / "style_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile))

    def fake_chat(messages, model, temperature=0.2, max_tokens=None):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("storycodex.build_context.llm.chat", fake_chat)

    runner = CliRunner()
    first = runner.invoke(app, ["build-context", "--root", str(tmp_path), "--scene", "1"])
    assert first.exit_code == 0
    context_first = json.loads(scene_context_path(tmp_path, 1).read_text())

    second = runner.invoke(
        app, ["build-context", "--root", str(tmp_path), "--scene", "1", "--force"]
    )
    assert second.exit_code == 0
    context_second = json.loads(scene_context_path(tmp_path, 1).read_text())

    assert context_first["ringA"]["style_rules"] == context_second["ringA"]["style_rules"]
    assert "noir" in context_first["ringA"]["tone"]
    assert "MUST: shadow" in context_first["ringA"]["global_constraints"]
    assert any(
        rule.startswith("Sentence rhythm:") for rule in context_first["ringA"]["style_rules"]
    )
    assert any(
        rule.startswith("Sensory priority:") for rule in context_first["ringA"]["style_rules"]
    )
    assert any(
        rule.startswith("Dialogue style:") for rule in context_first["ringA"]["style_rules"]
    )
    assert any(
        item["artifact_id"] == "seeds/style_profile.json"
        for item in context_first["build"]["sources"]
    )
