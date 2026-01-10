import json

import pytest
from typer.testing import CliRunner

from storycodex.cli import app
from storycodex.seed_apply import load_schema


def test_seed_apply_writes_outputs(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    (tmp_path / "artifacts" / "defaults").mkdir(parents=True)
    (tmp_path / "seeds").mkdir(parents=True)

    base_spec = {
        "title": "Base",
        "logline": "Base logline",
        "genre": ["fantasy"],
        "tone": ["moody"],
        "target_length": {"unit": "words", "value": 500},
        "pov": "first",
        "tense": "past",
        "constraints": {"must": [], "must_not": []},
    }
    override_spec = {
        "title": "Override",
        "genre": ["fantasy", "epic"],
        "constraints": {"must": ["dragons"]},
    }
    base_plot_intent = {
        "plot_intent": {"core_arc": "", "themes": [], "central_question": ""},
        "protagonist_arc": {
            "starting_state": "",
            "midpoint_state": "",
            "end_state": "",
        },
        "plot_constraints": {"must_include": [], "must_not": []},
        "act_shape": {
            "act_1": {"purpose": "", "beats": []},
            "act_2": {"purpose": "", "beats": []},
            "act_3": {"purpose": "", "beats": []},
        },
        "ending_constraints": {
            "resolution_style": "",
            "final_image": "",
            "emotional_aftertaste": "",
        },
    }

    (tmp_path / "artifacts" / "defaults" / "story_spec.json").write_text(
        json.dumps(base_spec)
    )
    (tmp_path / "artifacts" / "defaults" / "plot_intent.json").write_text(
        json.dumps(base_plot_intent)
    )
    (tmp_path / "seeds" / "story_overrides.json").write_text(
        json.dumps(override_spec)
    )

    runner = CliRunner()
    result = runner.invoke(app, ["seed", "apply", "--root", str(tmp_path)])

    assert result.exit_code == 0

    merged = json.loads(
        (tmp_path / "artifacts" / "inputs" / "story_spec.json").read_text()
    )
    plot_intent = json.loads(
        (tmp_path / "artifacts" / "inputs" / "plot_intent.json").read_text()
    )
    manifest = json.loads(
        (tmp_path / "artifacts" / "inputs" / "manifest.json").read_text()
    )
    report = json.loads((tmp_path / "out" / "seed_report.json").read_text())

    assert merged["title"] == "Override"
    assert merged["genre"] == ["fantasy", "epic"]
    assert "dragons" in merged["constraints"]["must"]

    schema = load_schema()
    jsonschema.Draft202012Validator(schema).validate(plot_intent)

    assert manifest["version"] == 1
    assert manifest["seeds_used"]
    assert manifest["resolved_inputs"]["story_spec"] == "artifacts/inputs/story_spec.json"
    assert (
        manifest["resolved_inputs"]["plot_intent"] == "artifacts/inputs/plot_intent.json"
    )

    assert "changed_keys" in report
    assert "title" in report["changed_keys"]
    assert "plot_overrides" in report


def test_seed_apply_plot_overrides_merge(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    (tmp_path / "artifacts" / "defaults").mkdir(parents=True)
    (tmp_path / "seeds").mkdir(parents=True)

    base_plot_intent = {
        "plot_intent": {
            "core_arc": "Base arc",
            "themes": ["resilience"],
            "central_question": "",
        },
        "plot_constraints": {"must_include": ["signal"], "must_not": []},
    }
    overrides = {
        "plot_intent": {
            "themes": ["resilience", "sacrifice"],
            "central_question": "Will she return?",
        },
        "plot_constraints": {"must_include": ["signal", "beacon"]},
    }

    (tmp_path / "artifacts" / "defaults" / "story_spec.json").write_text("{}")
    (tmp_path / "artifacts" / "defaults" / "plot_intent.json").write_text(
        json.dumps(base_plot_intent)
    )
    (tmp_path / "seeds" / "plot_overrides.json").write_text(json.dumps(overrides))

    runner = CliRunner()
    result = runner.invoke(app, ["seed", "apply", "--root", str(tmp_path)])

    assert result.exit_code == 0

    plot_intent = json.loads(
        (tmp_path / "artifacts" / "inputs" / "plot_intent.json").read_text()
    )
    manifest = json.loads(
        (tmp_path / "artifacts" / "inputs" / "manifest.json").read_text()
    )
    report = json.loads((tmp_path / "out" / "seed_report.json").read_text())

    assert plot_intent["plot_intent"]["core_arc"] == "Base arc"
    assert plot_intent["plot_intent"]["central_question"] == "Will she return?"
    assert plot_intent["plot_intent"]["themes"] == ["resilience", "sacrifice"]
    assert plot_intent["plot_constraints"]["must_include"] == ["signal", "beacon"]

    schema = load_schema()
    jsonschema.Draft202012Validator(schema).validate(plot_intent)

    assert any(
        entry["path"] == "seeds/plot_overrides.json" for entry in manifest["seeds_used"]
    )
    assert "plot_overrides" in report
    assert report["plot_overrides"]["changed_keys"]
