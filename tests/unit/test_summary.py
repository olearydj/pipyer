"""derive_summary (R21): byte-stable regeneration, summary_* convention,
halted/interrupted rendering, no silent omissions."""

from pathlib import Path

from pipyer.runner import derive_summary, run_workflow

GRADEBOT = Path(__file__).resolve().parents[1] / "fixtures" / "gradebot" / "workflow.yaml"


def test_regeneration_is_byte_identical(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    original = (run.run_dir / "summary.md").read_text(encoding="utf-8")
    (run.run_dir / "summary.md").unlink()
    regenerated = derive_summary(run.event_log_path)
    assert regenerated == original


def test_every_failure_and_skip_is_listed(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    summary = derive_summary(run.event_log_path)
    assert "## Failures and skips" in summary
    assert "run_tests[1]" in summary  # bob's harness failure
    assert "grade[1]" in summary  # and its downstream skips
    assert "upstream_failure" in summary
    assert "nonzero_exit" in summary


def test_halted_run_renders_the_halt_reason(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path, settings={"max_failures": 0})
    summary = derive_summary(run.event_log_path)
    assert "Halt reason" in summary
    assert "failure budget exceeded" in summary


def test_interrupted_run_renders_without_a_finished_event(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path, interrupt_after_items=1)
    summary = derive_summary(run.event_log_path)
    assert run.run_id in summary
    assert "interrupted" in summary


def test_summary_prefixed_object_outputs_render_as_sections(tmp_path):
    """The naming convention: declared output `summary_stats` (a JSON object)
    surfaces as its own section; non-object outputs do not."""
    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    summary = derive_summary(run.event_log_path)
    assert "## Stats" in summary  # from output name summary_stats
    assert '"graded"' in summary
    # `grades` (a list output, no summary_ prefix) gets no section of its own.
    assert "## Grades" not in summary


def test_cost_section_aggregates_llm_usage(tmp_path):
    run = run_workflow(GRADEBOT, results_dir=tmp_path)
    summary = derive_summary(run.event_log_path)
    assert "## Cost" in summary
    assert "| grade | test |" in summary
    assert "Total estimated cost" in summary


def test_resume_section_reports_skip_and_recompute_accounting(tmp_path):
    run_workflow(GRADEBOT, results_dir=tmp_path)
    resumed = run_workflow(GRADEBOT, results_dir=tmp_path, resume=True)
    summary = derive_summary(resumed.event_log_path)
    assert "## Resume" in summary
    assert "Units skipped on hash match" in summary
    assert "Units recomputed: 0" in summary
    assert "run_tests[1]" in summary  # failed-not-retried is named
