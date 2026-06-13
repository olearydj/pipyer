"""Run-record conformance (contracts/run-record-schema.md): every outcome
representable, costs first-class, positional identity, no silent omissions."""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pipyer.records.run import (
    CheckpointSnapshot,
    RunRecord,
    event_line,
    parse_event_log,
)
from pipyer.records.step_result import (
    ERROR_CATEGORIES,
    StepError,
    StepResult,
    UsageCost,
)

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)

COMPONENTS = ["file_read", "file_write", "shell", "python", "llm", "llm_judge", "assertions"]


def usage(**overrides) -> UsageCost:
    base = dict(
        provider="anthropic",
        model="anthropic:claude-haiku-4-5",
        input_tokens=54,
        output_tokens=7,
        estimated_cost=Decimal("0.002572"),
        cost_table_version="genai-prices 0.0.65",
        counts_source="provider_reported",
        validation_attempts=1,
    )
    base.update(overrides)
    return UsageCost(**base)


def result(**overrides) -> StepResult:
    base = dict(
        schema_version="1",
        run_id="20260611T120000-test",
        step="grade",
        component="python",
        status="success",
        output={"ok": True},
        error=None,
        started_at=NOW,
        finished_at=NOW,
        duration_ms=8,
        usage=None,
        matrix=None,
        item_index=None,
        entity_id=None,
        input_refs={"submission": "steps.collect.submissions"},
        input_hash="sha256:409195554af699aa",
        component_version="0.1.0",
    )
    base.update(overrides)
    return StepResult(**base)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("status", ["success", "failure", "skipped"])
def test_every_status_times_component_is_representable(component, status):
    kwargs: dict = {"component": component, "status": status}
    if status == "success":
        kwargs["output"] = {"ok": True}
        if component in ("llm", "llm_judge"):
            kwargs["usage"] = usage()
    elif status == "failure":
        kwargs["output"] = None
        kwargs["error"] = StepError(category="nonzero_exit", message="exit 1")
    else:
        kwargs["output"] = None
        kwargs["error"] = StepError(category="upstream_failure", message="upstream item failed")
    assert result(**kwargs).status == status


@pytest.mark.parametrize("category", sorted(ERROR_CATEGORIES))
def test_every_taxonomy_category_is_representable(category):
    record = result(
        status="failure",
        output=None,
        error=StepError(category=category, message="observed failure", detail={"raw": "..."}),
    )
    assert record.error is not None
    assert record.error.category == category


def test_taxonomy_is_a_closed_enum():
    with pytest.raises(ValidationError):
        StepError(category="novel_failure_kind", message="nope")


def test_skip_records_carry_their_reason_never_silence():
    record = result(
        status="skipped",
        output=None,
        error=StepError(category="upstream_failure", message="run_tests failed for item 1"),
        item_index=1,
    )
    assert record.error is not None and record.error.category == "upstream_failure"
    with pytest.raises(ValidationError):
        result(status="skipped", output=None, error=None)  # a skip without a reason
    with pytest.raises(ValidationError):
        result(status="failure", output=None, error=None)  # a failure without an error


def test_llm_success_without_usage_is_rejected():
    with pytest.raises(ValidationError):
        result(component="llm", status="success", usage=None)
    # Failure without usage is legitimate (e.g. transport error before any count).
    record = result(
        component="llm",
        status="failure",
        output=None,
        error=StepError(category="transport_error", message="connection refused"),
        usage=None,
    )
    assert record.usage is None


def test_estimated_counts_without_cost_table_local_model_case():
    record = result(
        component="llm",
        usage=usage(
            provider="ollama",
            model="ollama:qwen2.5-coder",
            estimated_cost=None,
            cost_table_version=None,
            counts_source="estimated",
        ),
    )
    assert record.usage is not None and record.usage.estimated_cost is None


def test_unavailable_counts_source_is_valid_for_failure_attempt_metadata():
    record = result(
        component="llm",
        status="failure",
        error=StepError(category="output_validation_error", message="invalid output"),
        usage=usage(
            input_tokens=None,
            output_tokens=None,
            estimated_cost=None,
            counts_source="unavailable",
            validation_attempts=3,
        ),
    )
    assert record.usage is not None
    assert record.usage.counts_source == "unavailable"
    assert record.usage.validation_attempts == 3


def test_estimated_cost_serializes_as_string_form_decimal_never_float():
    record = result(component="llm", usage=usage())
    dumped = record.model_dump(mode="json")
    serialized = dumped["usage"]["estimated_cost"]
    assert isinstance(serialized, str)
    assert Decimal(serialized) == Decimal("0.002572")
    # And through actual JSON text - no float anywhere near money.
    assert '"0.002572"' in json.dumps(dumped)


def test_matrix_params_attach_and_aggregate_by_dimension():
    cells = [
        {"grader_model": "haiku", "cost": "0.0010"},
        {"grader_model": "haiku", "cost": "0.0030"},
        {"grader_model": "qwen", "cost": "0.0000"},
        {"grader_model": "qwen", "cost": "0.0000"},
    ]
    records = [
        result(
            component="llm",
            matrix={"grader_model": cell["grader_model"]},
            usage=usage(estimated_cost=Decimal(cell["cost"])),
            item_index=i,
        )
        for i, cell in enumerate(cells)
    ]
    # Aggregation computed inline in the test - no product aggregation function
    # exists in this feature; the contract guarantees the data supports it.
    totals: dict[str, Decimal] = {}
    for record in records:
        assert record.matrix is not None and record.usage is not None
        assert record.usage.estimated_cost is not None
        key = record.matrix["grader_model"]
        totals[key] = totals.get(key, Decimal(0)) + record.usage.estimated_cost
    assert totals == {"haiku": Decimal("0.0040"), "qwen": Decimal("0.0000")}


def test_duplicate_item_values_distinct_indices_stay_unambiguous():
    a = result(item_index=0, output={"submission": "same.py"})
    b = result(item_index=1, output={"submission": "same.py"})
    assert a.output == b.output and a.item_index != b.item_index
    c = result(item_index=2, entity_id="student-42")
    assert c.entity_id == "student-42"


def test_run_record_with_and_without_git_commit():
    base = dict(
        schema_version="1",
        run_id="20260611T120000-test",
        workflow_name="gradebot_hw",
        workflow_hash="sha256:" + "0" * 64,
        config_snapshot={"inputs": {"submissions_dir": "subs/"}, "aliases": {}},
        started_at=NOW,
        finished_at=NOW,
        status="completed",
        totals={"steps": 6, "items": 3, "failures": 1, "skips": 1},
    )
    assert RunRecord(**base, git_commit="e010a98").git_commit == "e010a98"
    assert RunRecord(**base).git_commit is None
    with pytest.raises(ValidationError):
        RunRecord(**{**base, "status": "halted"})  # halted requires halt_reason


def test_checkpoint_snapshot_validates_as_derived_state():
    snapshot = CheckpointSnapshot(
        schema_version="1",
        run_id="20260611T120000-test",
        workflow_hash="sha256:" + "0" * 64,
        config_hash="sha256:" + "1" * 64,
        completed={
            "run_tests:0": {"input_hash": "sha256:aa", "event_ref": "line:2"},
            "grade:0": {"input_hash": "sha256:bb", "event_ref": "line:3"},
        },
        written_at=NOW,
    )
    assert len(snapshot.completed) == 2


def test_corrupt_trailing_jsonl_line_is_detectable():
    good = result()
    lines = [
        event_line(good),
        event_line(good),
        '{"event": "step_result", "truncated_by_inter',  # interrupted write
    ]
    events, corrupt_trailing = parse_event_log("\n".join(lines))
    assert corrupt_trailing is True
    assert len(events) == 2
    # Corruption anywhere else violates single-writer append-only - loud failure.
    with pytest.raises(ValueError):
        parse_event_log("\n".join([lines[2], event_line(good)]))


def test_event_lines_are_self_contained():
    line = event_line(result())
    event = json.loads(line)
    assert event["event"] == "step_result"
    assert event["schema_version"] == "1"
    assert event["run_id"]
