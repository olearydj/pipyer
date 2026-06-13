from __future__ import annotations

import json
import textwrap

from typer.testing import CliRunner

from pipyer.cli import app
from pipyer.runner import run_workflow


def _write_echo_workflow(tmp_path, *, matrix_values: list[str] | None = None, results_dir=None):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "echo.py").write_text(
        "import json, sys\n"
        "inputs = json.load(sys.stdin)\n"
        "print(json.dumps({'value': inputs['value']}))\n"
    )
    values = matrix_values or ["old", "new"]
    lines = [
        'schema_version: "2"',
        "name: matrix_echo",
        "matrix:",
        "  model:",
        *(f"    - {json.dumps(value)}" for value in values),
        "steps:",
        "  - name: emit",
        "    component: python",
        "    config:",
        "      script: scripts/echo.py",
        "    inputs:",
        "      value: matrix.model",
    ]
    if results_dir:
        lines += ["settings:", f"  results_dir: {json.dumps(str(results_dir))}"]
    lines += ["outputs:", "  summary_value: steps.emit.output"]
    (tmp_path / "workflow.yaml").write_text("\n".join(lines) + "\n")
    return tmp_path / "workflow.yaml"


def test_matrix_runs_all_cells_and_outputs_are_per_cell(tmp_path):
    wf = _write_echo_workflow(tmp_path)
    run = run_workflow(wf, results_dir=tmp_path / "runs")

    cell_events = [e for e in run.events if e.get("event") == "cell_started"]
    step_results = [e for e in run.events if e.get("event") == "step_result"]

    assert [e["matrix"] for e in cell_events] == [{"model": "old"}, {"model": "new"}]
    assert [e["cell_index"] for e in step_results] == [0, 1]
    assert [e["matrix"] for e in step_results] == [{"model": "old"}, {"model": "new"}]
    assert run.record.totals["outputs"]["summary_value"] == [
        {"cell_index": 0, "matrix": {"model": "old"}, "value": {"value": "old"}},
        {"cell_index": 1, "matrix": {"model": "new"}, "value": {"value": "new"}},
    ]
    assert "## Matrix Cells" in (run.run_dir / "summary.md").read_text(encoding="utf-8")


def test_matrix_resume_uses_cell_prefixed_unit_keys(tmp_path):
    wf = _write_echo_workflow(tmp_path)
    run_workflow(wf, results_dir=tmp_path / "runs")
    resumed = run_workflow(wf, results_dir=tmp_path / "runs", resume=True)
    assert resumed.recomputed_step_count == 0
    assert resumed.record.totals["resume_skipped"] == ["cell[0]/emit", "cell[1]/emit"]


def test_cell_budget_halt_continues_next_cell(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "maybe_fail.py").write_text(
        "import json, sys\n"
        "value = json.load(sys.stdin)['value']\n"
        "if value == 'bad':\n"
        "    raise SystemExit(1)\n"
        "print(json.dumps({'value': value}))\n"
    )
    wf = tmp_path / "workflow.yaml"
    wf.write_text(
        textwrap.dedent(
            """
            schema_version: "2"
            name: matrix_halt
            matrix:
              case: ["bad", "ok"]
            settings:
              max_failures: 0
            steps:
              - name: run_case
                component: python
                config:
                  script: scripts/maybe_fail.py
                inputs:
                  value: matrix.case
            """
        )
    )

    run = run_workflow(wf, results_dir=tmp_path / "runs")
    halted = [e for e in run.events if e.get("event") == "cell_halted"]
    successes = [
        e for e in run.events if e.get("event") == "step_result" and e.get("status") == "success"
    ]
    assert run.status == "completed"
    assert halted and halted[0]["cell_index"] == 0
    assert successes and successes[0]["cell_index"] == 1


def test_resource_digest_makes_script_edits_recompute_on_resume(tmp_path):
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts" / "emit.py"
    script.write_text("import json\nprint(json.dumps({'value': 1}))\n")
    wf = tmp_path / "workflow.yaml"
    wf.write_text(
        textwrap.dedent(
            """
            schema_version: "2"
            name: digest_case
            steps:
              - name: emit
                component: python
                config:
                  script: scripts/emit.py
            outputs:
              value: steps.emit.output
            """
        )
    )
    first = run_workflow(wf, results_dir=tmp_path / "runs")
    script.write_text("import json\nprint(json.dumps({'value': 2}))\n")
    resumed = run_workflow(wf, results_dir=tmp_path / "runs", resume=True)
    assert first.record.totals["outputs"]["value"] == {"value": 1}
    assert resumed.record.totals["outputs"]["value"] == {"value": 2}
    assert resumed.record.totals["recomputed"] == ["emit"]


def test_compare_cells_writes_artifacts_and_json_stdout(tmp_path):
    results_dir = tmp_path / "runs"
    wf = _write_echo_workflow(tmp_path, results_dir=results_dir)
    run = run_workflow(wf, results_dir=results_dir)

    result = CliRunner().invoke(
        app,
        [
            "compare",
            run.run_id,
            "--results-dir",
            str(results_dir),
            "--left-cell-index",
            "0",
            "--right-cell-index",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert record["left"]["cell_index"] == 0
    assert record["right"]["cell_index"] == 1
    assert record["units"]["different"] == 1
    comparison_dirs = list((results_dir / "comparisons").glob("*"))
    assert comparison_dirs
    assert (comparison_dirs[0] / "comparison.md").is_file()
    assert (comparison_dirs[0] / "comparison.json").is_file()


def test_compare_archive_run_dir_metadata_is_stable(tmp_path):
    results_dir = tmp_path / "runs"
    wf = _write_echo_workflow(tmp_path, results_dir=results_dir)
    run = run_workflow(wf, results_dir=results_dir)
    archive_run = tmp_path / "archive" / "artifacts" / "run"
    archive_run.parent.mkdir(parents=True)
    run.run_dir.rename(archive_run)

    result = CliRunner().invoke(
        app,
        [
            "compare",
            str(archive_run),
            "--results-dir",
            str(results_dir),
            "--left-cell-index",
            "0",
            "--right-cell-index",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert record["left"]["run_dir"] == "artifacts/run"
    assert record["right"]["run_dir"] == "artifacts/run"


def test_compare_param_selector_errors_on_duplicate_cells(tmp_path):
    results_dir = tmp_path / "runs"
    wf = _write_echo_workflow(tmp_path, matrix_values=["same", "same"], results_dir=results_dir)
    run = run_workflow(wf, results_dir=results_dir)

    result = CliRunner().invoke(
        app,
        [
            "compare",
            run.run_id,
            "--results-dir",
            str(results_dir),
            "--left-cell",
            "model=same",
            "--right-cell-index",
            "1",
        ],
    )

    assert result.exit_code == 2
    assert "matches multiple cells" in result.output
