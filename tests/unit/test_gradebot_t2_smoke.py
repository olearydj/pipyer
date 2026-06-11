"""T035: full T2 pipeline rehearsal on the PII-free smoke corpus, stub model.

Exercises collect -> harness -> grade -> score -> feedback -> compare end to
end via model_overrides, including the no-submission row path and the
expected-disagreement classifications, before any live spend (FR-019).
"""

from pathlib import Path

import pytest

from pipyer.runner import run_workflow

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows" / "gradebot-t2" / "workflow.yaml"
SMOKE = ROOT / "tests" / "fixtures" / "gradebot_t2_smoke"


@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory):
    from pydantic_ai.models.test import TestModel

    # The stub answers every rubric verdict True with empty feedback.
    stub = TestModel(
        custom_output_args={
            "items": [
                {"key": "returns_value", "verdict": True},
                {"key": "uses_multiplication", "verdict": True},
                {"key": "uses_upper", "verdict": True},
                {"key": "appends_bang", "verdict": True},
            ],
            "feedback": "",
        }
    )
    return run_workflow(
        WORKFLOW,
        results_dir=tmp_path_factory.mktemp("t2-smoke"),
        inputs={
            "corpus_dir": str(SMOKE),
            "raw_baseline_csv": "published/scored/grading_results_smoke.csv",
            "published_baseline_csv": "published/final/grading_results_smoke.csv",
            "patch_manifest": "published/patched/patch_manifest.json",
            "annotations_file": str(SMOKE / "annotations.json"),
            "point_weights": {"test2.1-double_it": 30, "test2.2-shout": 20},
        },
        model_overrides={"grader": stub},
    )


def test_pipeline_completes_with_every_baseline_row_as_an_item(smoke_run):
    assert smoke_run.status == "completed"
    collect = next(
        e
        for e in smoke_run.events
        if e.get("step") == "collect" and e.get("event") == "step_result"
    )
    assert collect["output"]["output"]["count"] == 6  # 3 students x 2 problems, from the CSV


def test_no_submission_rows_are_explicit_items_not_omissions(smoke_run):
    stats = smoke_run.record.totals["outputs"]["summary_agreement"]
    assert stats["entries"] == 6
    assert stats["no_submission_rows"] == 3  # 100002/shout + 100003 both problems


def test_classifications_cover_the_three_categories(smoke_run):
    entries = next(
        e
        for e in smoke_run.events
        if e.get("step") == "compare" and e.get("event") == "step_result"
    )["output"]["output"]["entries"]
    by = {(e["student_id"], e["problem_key"]): e for e in entries}
    # 100001 matches both baselines exactly (all-True rubric, passing tests -> 1.0)
    assert by[("100001", "double_it")]["classification"] == "agrees"
    # 100002 double_it: ours 0.8 (gen test fails: x+x+1), raw v2 says 0.68 ->
    # disagrees with raw, matches published 0.80, and is known-patched.
    entry = by[("100002", "double_it")]
    assert entry["known_patched"] is True
    assert entry["published"]["match"] is True
    assert entry["raw_v2"]["match"] is False
    # 100003 carries the academic-integrity annotation, never silently reconciled.
    assert "academic-integrity override" in by[("100003", "double_it")]["annotation"]


def test_quantized_deltas_name_an_implied_cause(smoke_run):
    entries = next(
        e
        for e in smoke_run.events
        if e.get("step") == "compare" and e.get("event") == "step_result"
    )["output"]["output"]["entries"]
    causes = [
        e["raw_v2"].get("implied_cause") for e in entries if e["raw_v2"].get("match") is False
    ]
    assert causes and all(causes)


def test_agreement_statistics_surface_in_the_run_summary(smoke_run):
    summary = (smoke_run.run_dir / "summary.md").read_text(encoding="utf-8")
    assert "## Agreement" in summary
    assert "unexplained_above_floor" in summary


def test_feedback_and_comparison_land_in_outputs(smoke_run):
    outputs = smoke_run.run_dir / "outputs"
    assert (outputs / "comparison" / "comparison.json").is_file()
    assert (outputs / "comparison" / "comparison.md").is_file()
    assert (outputs / "feedback" / "100001_double_it.md").is_file()
