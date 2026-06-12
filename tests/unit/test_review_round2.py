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
import textwrap

from pipyer.prompts import extract_placeholders, render_prompt
from pipyer.runner import run_workflow
from pipyer.runner.resume import ResumePlan


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


def test_op_chain_overrides_stale_env_var(monkeypatch):
    from pipyer.runner.components import llm

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stale-env")
    monkeypatch.setattr(llm, "resolve_secret", lambda key, **kw: ("sk-from-op", "1password"))
    import os

    from pipyer.schema.workflow import ModelAlias

    llm._build_model(
        ModelAlias(model="anthropic:claude-haiku-4-5"),
        model_overrides={},
        alias_name="grader",
        force_invalid=False,
    )
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-op"


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
