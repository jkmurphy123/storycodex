import json

from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.worldcodex_patch_proposal import (
    collect_worldcodex_atom_ids,
    validate_worldcodex_patch,
)


def write_context(root, scene_id=1):
    context = {
        "scene_id": scene_id,
        "build": {
            "sources": [
                {
                    "artifact_id": "worldcodex",
                    "resolution_used": "story-context",
                }
            ]
        },
        "ringA": {
            "pov": "third",
            "tense": "past",
        },
        "ringB": {
            "scene_goal": "Expose the harbor vote.",
            "setting": {
                "location": {
                    "id": "place.glass_harbor",
                    "name": "Glass Harbor",
                }
            },
            "cast": [
                {
                    "id": "character.elara",
                    "name": "Elara",
                    "role": "protagonist",
                }
            ],
            "beats": [
                {
                    "type": "turn",
                    "description": "Elara makes the vote public.",
                }
            ],
            "continuity_locks": [],
        },
        "ringC": {
            "open_threads": ["conflict.harbor_vote remains unresolved"],
            "relevant_facts": ["faction.tide_council controls the registry"],
            "glossary": [],
        },
    }
    path = root / "artifacts" / "scenes" / f"scene_{scene_id:03d}.context.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context))
    return context


def write_draft(root, scene_id=1):
    out_dir = root / "out" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"scene_{scene_id:03d}.draft.md").write_text(
        "Elara stood in Glass Harbor and announced the registry vote."
    )


def write_continuity_report(root, scene_id=1):
    out_dir = root / "out" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"scene_{scene_id:03d}.continuity_report.json").write_text(
        json.dumps(
            {
                "scene_id": scene_id,
                "input": "draft",
                "summary": "Story checks passed.",
                "beat_coverage": [],
                "lock_checks": [],
                "other_issues": [],
                "verdict": {
                    "must_fixes": 0,
                    "should_fixes": 0,
                    "ready_for_polish": True,
                },
            }
        )
    )


def valid_world_patch():
    return {
        "schema_version": "worldcodex.patch.v1",
        "description": "Record the public harbor vote.",
        "operations": [
            {
                "op": "add_timeline_event",
                "atom": {
                    "id": "event.scene_001_harbor_vote",
                    "type": "event",
                    "name": "Harbor registry vote revealed",
                    "summary": "Elara publicly reveals the registry vote in Glass Harbor.",
                    "data": {
                        "participants": ["character.elara"],
                        "locations": ["place.glass_harbor"],
                    },
                },
            }
        ],
    }


def test_collect_worldcodex_atom_ids_recurses_context():
    payload = {
        "location": {"id": "place.glass_harbor"},
        "cast": [{"id": "character.elara"}],
        "notes": ["conflict.harbor_vote", "not-an-atom"],
    }

    assert collect_worldcodex_atom_ids(payload) == [
        "character.elara",
        "conflict.harbor_vote",
        "place.glass_harbor",
    ]


def test_validate_worldcodex_patch_rejects_scene_patch_shape():
    scene_patch = {
        "scene_id": 1,
        "input": "draft",
        "operations": [],
    }

    try:
        validate_worldcodex_patch(scene_patch)
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("Expected scene patch shape to fail WorldCodex validation")


def test_propose_world_patch_cli_writes_worldcodex_patch(tmp_path, monkeypatch):
    write_context(tmp_path)
    write_draft(tmp_path)
    write_continuity_report(tmp_path)
    captured = {}

    def fake_chat(messages, model, temperature=0.1, max_tokens=None):
        captured["prompt"] = messages[-1]["content"]
        return json.dumps(valid_world_patch())

    monkeypatch.setattr("storycodex.worldcodex_patch_proposal.llm.chat", fake_chat)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "propose-world-patch",
            "--root",
            str(tmp_path),
            "--scene",
            "1",
        ],
    )

    assert result.exit_code == 0
    patch_path = tmp_path / "out" / "scenes" / "scene_001.worldcodex_patch.json"
    meta_path = tmp_path / "out" / "scenes" / "scene_001.worldcodex_patch.meta.json"

    patch = json.loads(patch_path.read_text())
    meta = json.loads(meta_path.read_text())

    assert patch["schema_version"] == "worldcodex.patch.v1"
    assert patch["operations"][0]["op"] == "add_timeline_event"
    assert "scene-patch.schema.json" not in captured["prompt"]
    assert "prose fixes" in captured["prompt"]
    assert meta["source_atom_ids"] == [
        "character.elara",
        "conflict.harbor_vote",
        "faction.tide_council",
        "place.glass_harbor",
    ]
