"""`pipyer run` CLI contract (contracts/run-cli.md): dry-run parity with
validate, exit codes, pre-run input checking, no secret values in output."""

from pathlib import Path

from typer.testing import CliRunner

from pipyer.cli import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRADEBOT = FIXTURES / "gradebot" / "workflow.yaml"
INVALID = FIXTURES / "invalid" / "dangling_step_ref.yaml"

runner = CliRunner()


def test_dry_run_is_exactly_validate():
    dry = runner.invoke(app, ["run", str(GRADEBOT), "--dry-run"])
    val = runner.invoke(app, ["validate", str(GRADEBOT)])
    assert dry.exit_code == val.exit_code == 0
    assert dry.output == val.output


def test_dry_run_invalid_matches_validate_exit_and_output(tmp_path):
    dry = runner.invoke(app, ["run", str(INVALID), "--dry-run"])
    val = runner.invoke(app, ["validate", str(INVALID)])
    assert dry.exit_code == val.exit_code == 1
    assert dry.output == val.output
    assert list(tmp_path.iterdir()) == []  # nothing executed, nothing written


def test_invalid_workflow_exits_two_before_any_run_directory(tmp_path):
    result = runner.invoke(app, ["run", str(INVALID), "--results-dir", str(tmp_path / "runs")])
    assert result.exit_code == 2
    assert not (tmp_path / "runs").exists()


def test_unknown_input_key_exits_two_pre_run(tmp_path):
    result = runner.invoke(
        app,
        ["run", str(GRADEBOT), "--input", "nonsense=1", "--results-dir", str(tmp_path / "runs")],
    )
    assert result.exit_code == 2
    assert "nonsense" in result.output
    assert not (tmp_path / "runs").exists()


def test_retry_failed_without_resume_exits_two():
    result = runner.invoke(app, ["run", str(GRADEBOT), "--retry-failed"])
    assert result.exit_code == 2
    assert "--resume" in result.output


def test_resume_with_no_prior_run_exits_two_never_a_fresh_run(tmp_path):
    result = runner.invoke(
        app, ["run", str(GRADEBOT), "--resume", "last", "--results-dir", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert list(tmp_path.iterdir()) == []


def test_completed_with_failures_exits_one_and_prints_accounting(tmp_path):
    # The gradebot fixture has one deliberately failing submission (bob).
    result = runner.invoke(app, ["run", str(GRADEBOT), "--results-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "failed" in result.output
    assert "summary" in result.output


def test_json_output_is_the_run_record(tmp_path):
    import json

    result = runner.invoke(app, ["run", str(GRADEBOT), "--results-dir", str(tmp_path), "--json"])
    record = json.loads(result.output)
    assert record["workflow_name"] == "gradebot_hw"
    assert record["status"] == "completed"
    assert "config_snapshot" in record


def test_no_secret_values_in_any_output(tmp_path, monkeypatch):
    canary = "sk-canary-never-print-me"
    monkeypatch.setenv("ANTHROPIC_API_KEY", canary)
    result = runner.invoke(app, ["run", str(GRADEBOT), "--results-dir", str(tmp_path), "--json"])
    assert canary not in result.output
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert canary not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_input_values_parse_as_yaml_scalars(tmp_path):
    result = runner.invoke(
        app,
        [
            "run",
            str(GRADEBOT),
            "--input",
            "submissions_dir=empty/",
            "--results-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "0 failed" in result.output
