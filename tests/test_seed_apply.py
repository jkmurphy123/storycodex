import json

from typer.testing import CliRunner

from storycodex.cli import app


def test_seed_apply_writes_outputs(tmp_path):
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

    (tmp_path / "artifacts" / "defaults" / "story_spec.json").write_text(
        json.dumps(base_spec)
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
    manifest = json.loads(
        (tmp_path / "artifacts" / "inputs" / "manifest.json").read_text()
    )
    report = json.loads((tmp_path / "out" / "seed_report.json").read_text())

    assert merged["title"] == "Override"
    assert merged["genre"] == ["fantasy", "epic"]
    assert "dragons" in merged["constraints"]["must"]

    assert manifest["version"] == 1
    assert manifest["seeds_used"]
    assert manifest["resolved_inputs"]["story_spec"] == "artifacts/inputs/story_spec.json"

    assert "changed_keys" in report
    assert "title" in report["changed_keys"]
