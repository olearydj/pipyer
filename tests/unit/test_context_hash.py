"""Unit identity and hashing (R17, R20): positional keys, hash sensitivity,
run-id collision behavior."""

from datetime import UTC, datetime
from pathlib import Path

import yaml

from pipyer.runner.context import RunContext, new_run_id, stable_hash, unit_key
from pipyer.schema.workflow import Settings, Workflow

GRADEBOT = Path(__file__).resolve().parents[1] / "fixtures" / "gradebot" / "workflow.yaml"


def _ctx(tmp_path) -> RunContext:
    workflow = Workflow.model_validate(yaml.safe_load(GRADEBOT.read_text(encoding="utf-8")))
    return RunContext(
        workflow,
        inputs={"submissions_dir": "submissions", "rubric_file": "rubric.md", "output_dir": "f"},
        settings=Settings(),
        workflow_dir=GRADEBOT.parent,
        run_dir=tmp_path,
        run_id="r1",
        secret_providers={},
    )


def test_unit_keys_are_positional_never_value_based():
    assert unit_key("grade", None) == "grade"
    assert unit_key("grade", 0) == "grade[0]"
    assert unit_key("grade", 7) == "grade[7]"
    assert unit_key("grade", None, 0) == "cell[0]/grade"
    assert unit_key("grade", 7, 0) == "cell[0]/grade[7]"
    # Duplicate item VALUES are irrelevant: two items with identical content
    # still occupy distinct indices, so distinct keys.
    assert unit_key("grade", 0) != unit_key("grade", 1)


def test_input_hash_moves_with_inputs_config_and_workflow_independently(tmp_path):
    ctx = _ctx(tmp_path)
    base = ctx.unit_input_hash("s", {"a": 1}, {"c": 1})
    assert ctx.unit_input_hash("s", {"a": 2}, {"c": 1}) != base  # inputs moved
    assert ctx.unit_input_hash("s", {"a": 1}, {"c": 2}) != base  # config moved
    assert ctx.unit_input_hash("s", {"a": 1}, {"c": 1}) == base  # stable
    other = _ctx(tmp_path)
    other.workflow_hash = "sha256:" + "f" * 64  # workflow moved
    assert other.unit_input_hash("s", {"a": 1}, {"c": 1}) != base


def test_stable_hash_is_order_insensitive_for_dict_keys():
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})
    assert stable_hash([1, 2]) != stable_hash([2, 1])  # lists are positional


def test_run_id_collision_appends_suffix_preserving_order(tmp_path):
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    wf_hash = "sha256:" + "abcdef" + "0" * 58
    first = new_run_id(tmp_path, wf_hash, now=now)
    (tmp_path / first).mkdir()
    second = new_run_id(tmp_path, wf_hash, now=now)
    (tmp_path / second).mkdir()
    third = new_run_id(tmp_path, wf_hash, now=now)
    assert first == "20260611-120000-abcdef"
    assert second == "20260611-120000-abcdef-2"
    assert third == "20260611-120000-abcdef-3"
    assert sorted([first, second, third]) == [first, second, third]


def test_duplicate_each_item_values_resolve_by_index(tmp_path):
    """The R2 guarantee at runtime: identical item values, distinct units."""
    from pipyer.runner.context import StepState

    ctx = _ctx(tmp_path)
    ctx.steps["collect_submissions"] = StepState(
        each=False,
        projections={"collect_submissions": {"output": {"submissions": ["same", "same"]}}},
    )
    first = ctx.resolve("item", index=0, each_ref="steps.collect_submissions.output.submissions")
    second = ctx.resolve("item", index=1, each_ref="steps.collect_submissions.output.submissions")
    assert first == second == "same"
    assert (
        ctx.resolve("index", index=1, each_ref="steps.collect_submissions.output.submissions") == 1
    )
