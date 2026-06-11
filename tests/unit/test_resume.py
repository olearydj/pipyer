"""Resume semantics beyond the fixtures (R5, R20, R25): config-change
recompute scope, retry-failed gating, stale-lock reclaim, checkpoint/log
mismatch refusal."""

import json
from pathlib import Path

import pytest

from pipyer.runner import NoPriorRunError, run_workflow
from pipyer.runner.resume import load_resume_plan

GRADEBOT = Path(__file__).resolve().parents[1] / "fixtures" / "gradebot" / "workflow.yaml"


def _failures(run):
    return [e for e in run.events if e.get("event") == "step_result" and e["status"] == "failure"]


def test_identical_rerun_recomputes_nothing(tmp_path):
    first = run_workflow(GRADEBOT, results_dir=tmp_path)
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)
    assert resumed.recomputed_step_count == 0
    # Everything completed before is skipped on hash match.
    skipped = resumed.record.totals["resume_skipped"]
    assert len(skipped) == first.record.totals["succeeded"]


def test_input_change_recomputes_only_the_affected_tail(tmp_path):
    run_workflow(GRADEBOT, results_dir=tmp_path)
    # Changing summary_file moves only write_summary's input hash (the v1→v2
    # config-iteration pattern from the brief: rerun recomputes the tail only).
    resumed = run_workflow(
        GRADEBOT,
        results_dir=tmp_path,
        resume=True,
        inputs={"summary_file": "grades/summary-v2.md"},
    )
    assert resumed.record.totals["recomputed"] == ["write_summary"]


def test_failed_items_stay_failed_without_retry_flag(tmp_path):
    first = run_workflow(GRADEBOT, results_dir=tmp_path)
    assert _failures(first), "fixture must contain a failing submission"
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)
    # bob's run_tests does not re-execute: the resumed log carries no new
    # failure events beyond the boundary, and the diff names it not-retried.
    boundary = next(e for e in resumed.events if e.get("event") == "run_resumed")
    assert "run_tests[1]" in boundary["failed_not_retried"]
    assert boundary["failed_retried"] == []
    after_boundary = resumed.events[resumed.events.index(boundary) :]
    assert not [
        e
        for e in after_boundary
        if e.get("event") == "step_result"
        and e.get("step") == "run_tests"
        and e.get("item_index") == 1
    ], "a failed unit must not re-execute without --retry-failed (R20)"


def test_retry_failed_reexecutes_failed_units_with_incremented_attempt(tmp_path):
    run_workflow(GRADEBOT, results_dir=tmp_path)
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True, retry_failed=True)
    boundary = next(e for e in resumed.events if e.get("event") == "run_resumed")
    assert "run_tests[1]" in boundary["failed_retried"]
    retried = [
        e
        for e in resumed.events[resumed.events.index(boundary) :]
        if e.get("event") == "step_result"
        and e.get("step") == "run_tests"
        and e.get("item_index") == 1
    ]
    assert retried, "the failed unit must re-execute under --retry-failed"
    assert all(e["attempt"] == 2 for e in retried)


def test_resume_with_no_prior_run_is_a_clear_error(tmp_path):
    with pytest.raises(NoPriorRunError, match="never silently"):
        run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)


def test_stale_lock_is_reclaimed_and_noted(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path, interrupt_after_items=1)
    # Simulate the crash that left the lock behind, held by a dead pid.
    (run.run_dir / "events.jsonl.lock").write_text(
        json.dumps({"pid": 2**22 + 54321, "started_at": "2026-01-01T00:00:00+00:00"})
    )
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)
    boundary = next(e for e in resumed.events if e.get("event") == "run_resumed")
    assert boundary["lock_reclaimed"] is True


def test_checkpoint_log_mismatch_refuses_to_resume(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path, interrupt_after_items=1)
    checkpoint = json.loads(run.checkpoint_path.read_text())
    checkpoint["completed"]["fabricated_step"] = {
        "input_hash": "sha256:" + "0" * 64,
        "event_ref": "999",
    }
    run.checkpoint_path.write_text(json.dumps(checkpoint))
    with pytest.raises(RuntimeError, match="checkpoint/log mismatch"):
        load_resume_plan(tmp_path, run_id=None, retry_failed=False)


def test_corrupt_trailing_line_is_recovered_on_resume(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path, interrupt_after_items=1)
    with run.event_log_path.open("a", encoding="utf-8") as fh:
        fh.write('{"event": "step_result", "torn-wri')  # interrupted write
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)
    assert resumed.status == "completed"
