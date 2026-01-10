import json

from typer.testing import CliRunner

from storycodex.cli import app


def write_context(root, scene_id=1, beats_count=2):
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
            "cast": [
                {
                    "id": "Elias",
                    "name": "Elias",
                    "role": "protagonist",
                    "voice_tics": [],
                    "current_state": "tired",
                    "wants_now": [],
                    "taboos": [],
                }
            ],
            "beats": [
                {"type": "entry", "description": "Enters."},
                {"type": "turn", "description": "Finds clue."},
            ][:beats_count],
            "continuity_locks": [],
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


def test_write_scene_writes_output(tmp_path, monkeypatch):
    write_context(tmp_path)

    prose = "Paragraph one.\n\nParagraph two.\n"

    def fake_chat(messages, model, temperature=0.7, max_tokens=None):
        return prose

    monkeypatch.setattr("storycodex.write_scene.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(
        app, ["write", "scene", "--root", str(tmp_path), "--scene", "1", "--target-words", "4"]
    )

    assert result.exit_code == 0
    draft_path = tmp_path / "out" / "scenes" / "scene_001.draft.md"
    meta_path = tmp_path / "out" / "scenes" / "scene_001.draft.meta.json"
    assert draft_path.exists()
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text())
    assert meta["target_words"] == 4


def test_write_scene_cache_skip(tmp_path, monkeypatch):
    write_context(tmp_path)

    draft_path = tmp_path / "out" / "scenes" / "scene_001.draft.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text("Existing")

    called = {"value": False}

    def fake_chat(messages, model, temperature=0.7, max_tokens=None):
        called["value"] = True
        return "Text"

    monkeypatch.setattr("storycodex.write_scene.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(app, ["write", "scene", "--root", str(tmp_path), "--scene", "1"])

    assert result.exit_code == 0
    assert called["value"] is False


def test_write_scene_missing_context(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["write", "scene", "--root", str(tmp_path), "--scene", "1"])
    assert result.exit_code == 1


def test_write_scene_validation_retry(tmp_path, monkeypatch):
    write_context(tmp_path)

    calls = {"count": 0}

    def fake_chat(messages, model, temperature=0.7, max_tokens=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return "short"
        if calls["count"] == 2:
            return "One two.\n\nThree four."
        return "One two three four five six.\n\nSeven eight nine ten eleven twelve."

    monkeypatch.setattr("storycodex.write_scene.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "write",
            "scene",
            "--root",
            str(tmp_path),
            "--scene",
            "1",
            "--target-words",
            "4",
        ],
    )

    assert result.exit_code == 0
    draft_path = tmp_path / "out" / "scenes" / "scene_001.draft.md"
    assert draft_path.exists()
