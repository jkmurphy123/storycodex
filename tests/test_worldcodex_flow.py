import json

from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.paths import scene_context_path, scene_plan_path


class FakeWorldCodexClient:
    def export_context(self, context_type, **kwargs):
        return {
            "metadata": {
                "schema_version": "worldcodex.context.v1",
                "export_type": context_type,
                "world_id": "titan-osa",
                "source_atom_ids": ["place.glass_harbor", "character.elara"],
            },
            "places": [
                {
                    "id": "place.glass_harbor",
                    "type": "place",
                    "name": "Glass Harbor",
                    "summary": "A corporate port where civic records are traded.",
                }
            ],
            "characters": [
                {
                    "id": "character.elara",
                    "type": "character",
                    "name": "Elara Myung",
                    "summary": "An investigator under pressure.",
                    "data": {
                        "role": "protagonist",
                        "goals": ["Expose the registry vote"],
                    },
                }
            ],
            "factions": [
                {
                    "id": "faction.tide_council",
                    "type": "faction",
                    "name": "Tide Council",
                    "summary": "The harbor's private governing bloc.",
                }
            ],
            "conflicts": [
                {
                    "id": "conflict.registry_vote",
                    "type": "conflict",
                    "name": "Registry Vote",
                    "summary": "Control of the harbor registry is contested.",
                }
            ],
            "relationships": [
                {
                    "subject": "character.elara",
                    "predicate": "opposes",
                    "object": "faction.tide_council",
                }
            ],
            "timeline": [],
        }


def fake_llm_chat(messages, model, temperature=0.4, max_tokens=None):
    system = messages[0]["content"]
    user = messages[-1]["content"]

    if "Generate a plot spine" in user:
        return json.dumps(
            {
                "acts": [
                    {
                        "act_no": 1,
                        "summary": "Elara tests the harbor registry.",
                        "chapters": [
                            {
                                "chapter_no": 1,
                                "goal": "Reveal the pressure around the vote.",
                                "turning_points": ["Elara makes the vote public."],
                                "scenes": [1],
                            }
                        ],
                    }
                ]
            }
        )

    if "two keys: index and plans" in user:
        return json.dumps(
            {
                "index": {
                    "version": 1,
                    "scenes": [
                        {
                            "scene_id": 1,
                            "chapter_no": 1,
                            "title": "Harbor Vote",
                            "plan_path": "artifacts/scenes/scene_001.plan.json",
                            "beats_path": "artifacts/scenes/scene_001.beats.json",
                        }
                    ],
                },
                "plans": [
                    {
                        "scene_id": 1,
                        "chapter_no": 1,
                        "title": "Harbor Vote",
                        "setting": {
                            "location_id": "place.glass_harbor",
                            "time": "morning",
                            "mood_tags": ["tense"],
                        },
                        "cast": ["character.elara"],
                        "goal": "Elara reveals the registry vote.",
                        "stakes": "The Tide Council can bury the evidence.",
                        "beats_ref": "artifacts/scenes/scene_001.beats.json",
                    }
                ],
            }
        )

    if "Generate scene beats" in user or "Scene plan JSON" in user:
        return json.dumps(
            {
                "scene_id": 1,
                "beats": [
                    {"type": "entry", "description": "Elara enters Glass Harbor."},
                    {"type": "orientation", "description": "She spots the council clerks."},
                    {"type": "pressure", "description": "The registry shutters begin closing."},
                    {"type": "interaction", "description": "Elara confronts the clerk."},
                    {"type": "turn", "description": "She reveals the vote record."},
                    {"type": "exit", "description": "The crowd turns toward the council."},
                ],
            }
        )

    if "professional fiction writer" in system:
        return (
            "Elara entered Glass Harbor as the shutters rattled down around the registry.\n\n"
            "She found the clerk hiding the vote record and made him read it aloud.\n\n"
            "When the crowd heard the count, the Tide Council lost the room."
        )

    if "mechanical continuity checker" in system:
        return json.dumps(
            {
                "scene_id": 1,
                "input": "draft",
                "summary": "Scene follows the planned beats.",
                "beat_coverage": [
                    {
                        "beat_index": 0,
                        "beat_type": "entry",
                        "beat_description": "Elara enters Glass Harbor.",
                        "covered": True,
                        "evidence": "Elara entered Glass Harbor",
                        "notes": "",
                    }
                ],
                "lock_checks": [],
                "other_issues": [],
                "verdict": {
                    "must_fixes": 0,
                    "should_fixes": 0,
                    "ready_for_polish": True,
                },
            }
        )

    if "mechanical patch planner" in system:
        return json.dumps({"scene_id": 1, "input": "draft", "operations": []})

    if "WorldCodex canon patches" in system:
        return json.dumps(
            {
                "schema_version": "worldcodex.patch.v1",
                "description": "Record the registry vote reveal.",
                "operations": [
                    {
                        "op": "add_timeline_event",
                        "atom": {
                            "id": "event.scene_001_registry_vote_revealed",
                            "type": "event",
                            "name": "Registry vote revealed",
                            "summary": "Elara reveals the harbor registry vote in public.",
                        },
                    }
                ],
            }
        )

    raise AssertionError(f"Unexpected prompt: {system}\n{user[:300]}")


def test_full_cli_flow_uses_worldcodex_for_world_data(tmp_path, monkeypatch):
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")
    monkeypatch.setenv("STORYCODEX_WORLDCODEX_WORLD", "titan-osa")
    monkeypatch.setattr("storycodex.llm.chat", fake_llm_chat)
    monkeypatch.setattr("storycodex.seed_apply.validate_plot_intent", lambda payload: None)
    monkeypatch.setattr(
        "storycodex.plan_spine.parse_and_validate",
        lambda content: json.loads(content),
    )
    monkeypatch.setattr(
        "storycodex.plan_scenes.parse_and_validate",
        lambda content, scene_ids_by_chapter, scene_id_to_chapter, target_scene_ids: (
            json.loads(content)["index"],
            json.loads(content)["plans"],
            [],
        ),
    )
    monkeypatch.setattr(
        "storycodex.plan_beats.parse_and_validate",
        lambda content: (json.loads(content), []),
    )
    monkeypatch.setattr("storycodex.build_context.validate_context", lambda context: [])
    monkeypatch.setattr("storycodex.check_continuity.validate_json", lambda payload, schema_name: [])
    monkeypatch.setattr(
        "storycodex.plan_scenes.build_worldcodex_client",
        lambda world=None: FakeWorldCodexClient(),
    )
    monkeypatch.setattr(
        "storycodex.build_context.build_worldcodex_client",
        lambda world=None: FakeWorldCodexClient(),
    )

    runner = CliRunner()
    commands = [
        ["init", "--root", str(tmp_path)],
        ["seed", "apply", "--root", str(tmp_path)],
        ["plan", "spine", "--root", str(tmp_path)],
        ["plan", "scenes", "--root", str(tmp_path)],
        ["plan", "beats", "--root", str(tmp_path), "--scene", "1"],
        ["build-context", "--root", str(tmp_path), "--scene", "1"],
        ["write", "scene", "--root", str(tmp_path), "--scene", "1", "--target-words", "40"],
        ["check", "continuity", "--root", str(tmp_path), "--scene", "1"],
        ["propose-world-patch", "--root", str(tmp_path), "--scene", "1"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output

    plan = json.loads(scene_plan_path(tmp_path, 1).read_text())
    context = json.loads(scene_context_path(tmp_path, 1).read_text())
    world_patch = json.loads(
        (tmp_path / "out" / "scenes" / "scene_001.worldcodex_patch.json").read_text()
    )

    assert plan["setting"]["location_id"] == "place.glass_harbor"
    assert plan["cast"] == ["character.elara"]
    assert context["ringB"]["setting"]["location"]["id"] == "place.glass_harbor"
    assert context["ringB"]["cast"][0]["id"] == "character.elara"
    assert any(source["artifact_id"] == "worldcodex" for source in context["build"]["sources"])
    assert world_patch["schema_version"] == "worldcodex.patch.v1"
    assert not (tmp_path / "artifacts" / "world").exists()
    assert not (tmp_path / "artifacts" / "characters").exists()
