import json

from typer.testing import CliRunner

from storycodex.cli import app


def test_init_creates_expected_files(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--root", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "seeds").is_dir()
    assert (tmp_path / "artifacts" / "defaults").is_dir()
    assert (tmp_path / "artifacts" / "inputs").is_dir()
    assert (tmp_path / "out").is_dir()

    spec_path = tmp_path / "artifacts" / "defaults" / "story_spec.json"
    registry_path = tmp_path / "artifacts" / "registry.json"

    spec = json.loads(spec_path.read_text())
    registry = json.loads(registry_path.read_text())

    for key in [
        "title",
        "logline",
        "genre",
        "tone",
        "target_length",
        "pov",
        "tense",
        "constraints",
    ]:
        assert key in spec

    assert registry == {"version": 1, "artifacts": []}
