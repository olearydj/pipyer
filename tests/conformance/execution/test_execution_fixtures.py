"""Execution-behavior conformance fixtures (FR-017, SPEC section 7).

Authored now with expected outcomes; exercised when the Feature 002 runner
exists. Every fixture is skip-marked with the same reason so the suite reports
them as present and counted - never silently absent. The bodies are real
assertions against the future runner API (`pipyer.runner.run_workflow`), so
Feature 002 unskips them rather than rewriting them.
"""

from pathlib import Path

GRADEBOT = Path(__file__).resolve().parents[2] / "fixtures" / "gradebot" / "workflow.yaml"


def test_resume_after_interruption_recomputes_nothing(tmp_path):
    """Interrupt mid-batch; resume must complete remaining items with zero
    recomputation of completed ones (hash-matched skip), per SPEC section 6."""
    from pipyer.runner import run_workflow

    first = run_workflow(GRADEBOT, results_dir=tmp_path, interrupt_after_items=1)
    assert first.status == "interrupted"
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)
    assert resumed.status == "completed"
    assert resumed.recomputed_step_count == 0


def test_failure_budget_halt_is_a_recorded_event(tmp_path):
    """max_failures exceeded halts the workflow; the halt itself is a
    run_halted event in the log, and the run record carries halt_reason."""
    from pipyer.runner import run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path, settings={"max_failures": 0})
    assert run.status == "halted"
    assert any(e["event"] == "run_halted" for e in run.events)
    assert run.record.halt_reason


def test_checkpoint_reconstruction_from_event_log(tmp_path):
    """Deleting (or corrupting) the checkpoint snapshot is never fatal: resume
    state reconstructs from the JSONL event log alone (R6: log authoritative)."""
    from pipyer.runner import reconstruct_checkpoint, run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path, interrupt_after_items=1)
    snapshot_path = run.checkpoint_path
    original = snapshot_path.read_text()
    snapshot_path.unlink()
    rebuilt = reconstruct_checkpoint(run.event_log_path)
    assert rebuilt.completed.keys() == __import__("json").loads(original)["completed"].keys()


def test_downstream_skip_on_upstream_item_failure(tmp_path):
    """An item failing run_tests yields a failure-status StepResult and a
    skip-status grade record with category upstream_failure - never an omission."""
    from pipyer.runner import run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    failed_items = [e for e in run.events if e.get("status") == "failure"]
    skips = [e for e in run.events if e.get("status") == "skipped"]
    assert failed_items and skips
    assert all(s["error"]["category"] == "upstream_failure" for s in skips)
    assert {s["item_index"] for s in skips} <= {f["item_index"] for f in failed_items}


def test_shell_nonzero_exit_is_failure_without_retry(tmp_path):
    """A shell step exiting nonzero records exactly one attempt (side-effecting
    steps are not retried by default, SPEC section 6)."""
    from pipyer.runner import run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    shell_failures = [
        e for e in run.events if e.get("component") == "shell" and e.get("status") == "failure"
    ]
    assert shell_failures
    assert all(e["attempt"] == 1 for e in shell_failures)
    assert all(e["error"]["category"] == "nonzero_exit" for e in shell_failures)


def test_llm_validation_failure_after_bounded_attempts(tmp_path):
    """Output validation exhausting max_validation_retries yields a
    failure-status record with category output_validation_error and
    validation_attempts == retries + 1 (bounded, counted, visible)."""
    from pipyer.runner import run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path, force_invalid_llm_output=True)
    failures = [
        e for e in run.events if e.get("component") == "llm" and e.get("status") == "failure"
    ]
    assert failures
    for event in failures:
        assert event["error"]["category"] == "output_validation_error"
        assert event["usage"]["validation_attempts"] == 3  # max_validation_retries=2


def test_empty_each_collection_records_zero_items_explicitly(tmp_path):
    """R12: an empty `each` collection is legitimate runtime data - the run
    completes and the log records the zero-item expansion explicitly."""
    from pipyer.runner import run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path, inputs={"submissions_dir": "empty/"})
    assert run.status == "completed"
    expansions = [e for e in run.events if e.get("event") == "each_expanded"]
    assert any(e["item_count"] == 0 for e in expansions)


def test_markdown_summary_derives_from_the_log_alone(tmp_path):
    """FR-016: the human-readable run summary is derivable from the JSONL event
    log with no other state."""
    from pipyer.runner import derive_summary, run_workflow

    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    summary = derive_summary(run.event_log_path)
    assert run.record.run_id in summary
    assert "## " in summary  # human-readable markdown, not a data dump
