"""Regression tests for the second external review's findings.

1. Unhandled component exceptions become failure records; the run always
   reaches a terminal state with run.json and a summary (audit trail survives).
2. Prompt rendering shares validation's placeholder definition - literal JSON
   braces in prompts pass through without escaping.
3. Relative file_write paths cannot escape the run's outputs directory.
4. The provider chain's decision overrides a stale pre-set env var.
5. run_resumed carries hash-skip eligibility at the boundary.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from pipyer.prompts import extract_placeholders, render_prompt
from pipyer.runner import ValidationFailure, run_workflow
from pipyer.runner.resume import ResumePlan
from pipyer.validation import validate_file


def _minimal(tmp_path, step_yaml: str, extra: str = ""):
    (tmp_path / "workflow.yaml").write_text(
        textwrap.dedent(
            f"""
            schema_version: "2"
            name: review_case
            {extra}
            steps:
            {step_yaml}
            """
        )
    )
    return tmp_path / "workflow.yaml"


def _terminal_state(run):
    events = [json.loads(line) for line in (run.run_dir / "events.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "run_finished"
    assert (run.run_dir / "run.json").is_file()
    assert (run.run_dir / "summary.md").is_file()
    return events


def test_unhandled_component_exception_is_recorded_not_raised(tmp_path):
    (tmp_path / "bad.json").write_text("{not json")
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: load
                component: file_read
                config:
                  path: bad.json
                  format: json
                inputs: {}
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs")
    events = _terminal_state(run)
    failures = [e for e in events if e.get("event") == "step_result" and e["status"] == "failure"]
    assert failures and failures[0]["error"]["category"] == "unclassified"
    assert "JSONDecodeError" in failures[0]["error"]["message"]


def test_missing_shell_executable_is_recorded_not_raised(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: run_it
                component: shell
                config:
                  command: ["definitely-not-a-real-binary-xyz"]
                inputs: {}
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs")
    events = _terminal_state(run)
    failures = [e for e in events if e.get("event") == "step_result" and e["status"] == "failure"]
    assert failures and failures[0]["error"]["category"] == "unclassified"


def test_prompt_json_braces_pass_through():
    prompt = 'Return JSON like {"answer": "ok", "n": 3}. Grade: {payload} (id {n}).'
    assert extract_placeholders(prompt) == {"payload", "n"}
    rendered = render_prompt(prompt, {"payload": "x=1", "n": 7})
    assert '{"answer": "ok", "n": 3}' in rendered
    assert "Grade: x=1 (id 7)" in rendered


def test_relative_write_escape_is_blocked(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: escape
                component: file_write
                config:
                  path: ../../../outside-results.txt
                  format: text
                inputs:
                  content: "should never land"
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs")
    events = _terminal_state(run)
    failures = [e for e in events if e.get("event") == "step_result" and e["status"] == "failure"]
    assert failures and "escapes the run outputs directory" in failures[0]["error"]["message"]
    assert not (tmp_path / "outside-results.txt").exists()


def test_op_chain_builds_model_without_mutating_process_env(monkeypatch):
    from pipyer.runner.components import llm

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stale-env")
    monkeypatch.setattr(llm, "resolve_secret", lambda key, **kw: ("sk-from-op", "1password"))
    captured = {}

    def fake_build(model, *, key, secret):
        captured.update({"model": model, "key": key, "secret": secret})
        return "built-model"

    monkeypatch.setattr(llm, "_build_hosted_model", fake_build)

    from pipyer.schema.workflow import ModelAlias

    built = llm._build_model(
        ModelAlias(model="anthropic:claude-haiku-4-5"),
        model_overrides={},
        alias_name="grader",
        force_invalid=False,
    )
    assert built == "built-model"
    assert captured == {
        "model": "anthropic:claude-haiku-4-5",
        "key": "ANTHROPIC_API_KEY",
        "secret": "sk-from-op",
    }
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-stale-env"


def test_boundary_event_carries_skip_eligibility(tmp_path):
    events = [
        {"event": "run_started", "run_id": "r1"},
        {
            "event": "step_result",
            "step": "a",
            "status": "success",
            "input_hash": "sha256:aa",
            "attempt": 1,
            "output": {},
        },
        {
            "event": "step_result",
            "step": "b",
            "status": "failure",
            "input_hash": "sha256:bb",
            "attempt": 1,
        },
        {"event": "run_finished", "run_id": "r1", "status": "interrupted"},
    ]
    plan = ResumePlan(tmp_path, events, retry_failed=False)
    from datetime import UTC, datetime

    boundary = plan.boundary_event(schema_version="1", lock_reclaimed=False, at=datetime.now(UTC))
    assert boundary.skipped == ["a"]
    assert boundary.failed_not_retried == ["b"]


def test_runtime_input_resolution_error_is_recorded_not_raised(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: check
                component: assertions
                inputs:
                  x: inputs.payload.missing
                config:
                  checks:
                    - input: x
                      op: exists
            """
        ).replace("\n", "\n            "),
        extra=textwrap.dedent(
            """\
            inputs:
              payload:
                type: json
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs", inputs={"payload": {}})
    events = _terminal_state(run)
    failures = [e for e in events if e.get("event") == "step_result" and e["status"] == "failure"]
    assert failures and failures[0]["error"]["category"] == "unclassified"
    assert failures[0]["error"]["detail"]["phase"] == "input resolution"
    assert "ResolutionError" in failures[0]["error"]["message"]


def test_non_list_each_target_is_recorded_not_raised(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: check_each
                component: assertions
                each: inputs.items
                inputs:
                  x: item
                config:
                  checks:
                    - input: x
                      op: exists
            """
        ).replace("\n", "\n            "),
        extra=textwrap.dedent(
            """\
            inputs:
              items:
                type: json
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs", inputs={"items": 1})
    events = _terminal_state(run)
    failures = [e for e in events if e.get("event") == "step_result" and e["status"] == "failure"]
    assert failures and failures[0]["error"]["category"] == "unclassified"
    assert failures[0]["error"]["detail"]["phase"] == "each expansion"
    assert "expected list" in failures[0]["error"]["message"]


def test_cli_unknown_estimated_cost_prints_na(tmp_path):
    from pipyer.cli import app

    gradebot = Path(__file__).resolve().parents[1] / "fixtures" / "gradebot" / "workflow.yaml"
    result = CliRunner().invoke(app, ["run", str(gradebot), "--results-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "cost: n/a (" in result.output
    assert "cost: $0" not in result.output


def test_run_rejects_matrix_execution_until_feature_003(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: check
                component: assertions
                inputs:
                  x: "ok"
                config:
                  checks:
                    - input: x
                      op: equals
                      expected: "ok"
            """
        ).replace("\n", "\n            "),
        extra=textwrap.dedent(
            """\
            matrix:
              grader_model: ["test"]
            """
        ).replace("\n", "\n            "),
    )
    assert validate_file(wf)[1] == []
    try:
        run_workflow(wf, results_dir=tmp_path / "runs")
    except ValidationFailure as error:
        assert error.issues[0].code == "unsupported_runtime_feature"
        assert error.issues[0].loc == "matrix"
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("matrix workflow ran instead of failing loudly")


def test_run_rejects_alias_ref_execution_until_feature_003(tmp_path):
    (tmp_path / "prompt.md").write_text("{x}")
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: grade
                component: llm
                inputs:
                  x: "hi"
                config:
                  model: grader
                  prompt: prompt.md
                  output_schema:
                    type: object
                    properties:
                      answer: {type: string}
                    required: [answer]
            """
        ).replace("\n", "\n            "),
        extra=textwrap.dedent(
            """\
            inputs:
              model_name:
                type: string
                required: false
                default: "test"
            models:
              grader:
                model: inputs.model_name
                output_mode: tool
            """
        ).replace("\n", "\n            "),
    )
    assert validate_file(wf)[1] == []
    try:
        run_workflow(wf, results_dir=tmp_path / "runs")
    except ValidationFailure as error:
        assert error.issues[0].loc == "models.grader.model"
        assert error.issues[0].code == "unsupported_runtime_feature"
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("alias-ref workflow ran instead of failing loudly")


def test_python_subprocess_does_not_inherit_llm_api_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-canary")
    (tmp_path / "script.py").write_text(
        "import json, os, sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'secret': os.environ.get('ANTHROPIC_API_KEY')}))\n"
    )
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: check_env
                component: python
                config:
                  script: script.py
                inputs: {}
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs")
    result = next(e for e in run.events if e.get("event") == "step_result")
    assert result["output"]["output"]["secret"] is None
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-canary"


def test_input_type_mismatch_rejected_before_run_dir(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: check
                component: assertions
                inputs:
                  x: inputs.threshold
                config:
                  checks:
                    - input: x
                      op: exists
            """
        ).replace("\n", "\n            "),
        extra=textwrap.dedent(
            """\
            inputs:
              threshold:
                type: number
            """
        ).replace("\n", "\n            "),
    )
    try:
        run_workflow(wf, results_dir=tmp_path / "runs", inputs={"threshold": "abc"})
    except ValidationFailure as error:
        assert error.issues[0].code == "input_type_mismatch"
        assert error.issues[0].loc == "inputs.threshold"
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("type mismatch was accepted")
    assert not (tmp_path / "runs").exists()


def test_shell_parse_stdout_json_failure_is_loud(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            f"""\
              - name: bad_json
                component: shell
                config:
                  command: [{json.dumps(sys.executable)}, "-c", "print('not json')"]
                  parse_stdout: json
                inputs: {{}}
            """
        ).replace("\n", "\n            "),
    )
    run = run_workflow(wf, results_dir=tmp_path / "runs")
    failure = next(e for e in run.events if e.get("event") == "step_result")
    assert failure["status"] == "failure"
    assert failure["error"]["category"] == "output_validation_error"
    assert "not valid JSON" in failure["error"]["message"]


def test_invalid_assertion_regex_is_dry_run_error(tmp_path):
    wf = _minimal(
        tmp_path,
        textwrap.dedent(
            """\
              - name: check
                component: assertions
                inputs:
                  x: abc
                config:
                  checks:
                    - input: x
                      op: matches
                      expected: "["
            """
        ).replace("\n", "\n            "),
    )
    _workflow, issues = validate_file(wf)
    assert [(issue.loc, issue.code) for issue in issues] == [
        ("steps[0].config.checks[0].expected", "invalid_regex")
    ]


def test_run_halted_event_carries_accounting_payload(tmp_path):
    gradebot = Path(__file__).resolve().parents[1] / "fixtures" / "gradebot" / "workflow.yaml"
    run = run_workflow(gradebot, results_dir=tmp_path / "runs", settings={"max_failures": 0})
    halted = next(event for event in run.events if event.get("event") == "run_halted")
    assert halted["attempted"] >= 1
    assert halted["failed"] >= 1
    assert "not_attempted" in halted
    assert halted["attempted_units"]
    assert halted["failed_units"]
    assert "not_attempted_units" in halted
