"""CLI contract conformance (contracts/validate-cli.md): exit codes, output
shapes, document-order determinism, library parity, zero execution."""

import json
from pathlib import Path

from typer.testing import CliRunner

from pipyer.cli import app
from pipyer.validation import validate_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VALID = FIXTURES / "valid" / "minimal.yaml"
INVALID = FIXTURES / "invalid" / "dangling_step_ref.yaml"

runner = CliRunner()


def test_valid_workflow_exits_zero_with_name_version_hash():
    result = runner.invoke(app, ["validate", str(VALID)])
    assert result.exit_code == 0, result.output
    assert "OK minimal" in result.output
    assert "schema v1" in result.output
    assert "sha256:" in result.output


def test_invalid_workflow_exits_one_naming_the_location():
    result = runner.invoke(app, ["validate", str(INVALID)])
    assert result.exit_code == 1
    assert "INVALID" in result.output
    assert "steps[1].inputs.test_output" in result.output
    assert "run_test" in result.output


def test_json_output_is_machine_readable():
    result = runner.invoke(app, ["validate", str(INVALID), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["valid"] is False
    assert payload["errors"], payload
    first = payload["errors"][0]
    assert {"loc", "code", "message"} <= set(first)


def test_errors_are_deterministic_and_document_ordered(tmp_path: Path):
    two_errors = tmp_path / "two_errors.yaml"
    two_errors.write_text(
        "schema_version: '1'\n"
        "name: two_errors\n"
        "steps:\n"
        "  - name: first\n"
        "    component: python\n"
        "    config: {script: s.py}\n"
        "    inputs: {bad: steps.nowhere.out}\n"
        "  - name: second\n"
        "    component: python\n"
        "    config: {script: t.py}\n"
        "    inputs: {worse: steps.elsewhere.out}\n"
    )
    a = runner.invoke(app, ["validate", str(two_errors), "--json"])
    b = runner.invoke(app, ["validate", str(two_errors), "--json"])
    assert a.output == b.output
    locs = [e["loc"] for e in json.loads(a.output)["errors"]]
    assert locs == sorted(locs, key=lambda loc: loc.startswith("steps[1]"))
    assert locs[0].startswith("steps[0]")


def test_missing_file_exits_two():
    result = runner.invoke(app, ["validate", str(FIXTURES / "nope.yaml")])
    assert result.exit_code == 2


def test_unreadable_yaml_exits_two(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{::: this is not yaml :::")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 2


def test_unsafe_yaml_constructs_exit_two(tmp_path: Path):
    evil = tmp_path / "evil.yaml"
    evil.write_text("!!python/object/apply:os.system ['echo pwned']\n")
    result = runner.invoke(app, ["validate", str(evil)])
    assert result.exit_code == 2


def test_library_parity_cli_reports_exactly_the_validation_api_errors():
    cli = runner.invoke(app, ["validate", str(INVALID), "--json"])
    cli_errors = [(e["loc"], e["code"]) for e in json.loads(cli.output)["errors"]]
    _, issues = validate_file(INVALID)
    lib_errors = [(i.loc, i.code) for i in issues]
    assert cli_errors == lib_errors


def test_validation_has_zero_side_effects(tmp_path: Path):
    before = sorted(p.name for p in VALID.parent.iterdir())
    runner.invoke(app, ["validate", str(VALID)])
    runner.invoke(app, ["validate", str(INVALID)])
    after = sorted(p.name for p in VALID.parent.iterdir())
    assert before == after
    assert list(tmp_path.iterdir()) == []
