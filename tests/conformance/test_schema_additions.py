"""Feature 002 schema additions, conformance-tested in the same change set
(constitution VI; research R16): ModelAlias.output_mode, Llm*/timeout_s, and
the schema_version bump to "2" with its hash-continuity consequences.
"""

import pytest
import yaml
from pydantic import ValidationError

from pipyer.canonical import canonical_bytes
from pipyer.schema.components import LlmConfig, LlmJudgeConfig
from pipyer.schema.workflow import SUPPORTED_SCHEMA_VERSIONS, ModelAlias, Workflow
from pipyer.validation import validate_data


def _minimal(version: str = "2", **overrides) -> dict:
    data = {
        "schema_version": version,
        "name": "minimal",
        "steps": [{"name": "t", "component": "python", "config": {"script": "s.py"}}],
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------ version boundary


def test_supported_versions_is_exactly_v2():
    assert SUPPORTED_SCHEMA_VERSIONS == ("2",)


def test_version_1_rejected_with_legible_error():
    _, issues = validate_data(_minimal("1"))
    codes = [(i.code, i.loc) for i in issues]
    assert ("unsupported_schema_version", "schema_version") in codes
    message = next(i.message for i in issues if i.code == "unsupported_schema_version")
    assert "'1'" in message and "2" in message


def test_version_participates_in_canonical_bytes():
    workflow = Workflow.model_validate(_minimal())
    assert b'"schema_version":"2"' in canonical_bytes(workflow)


# ---------------------------------------------------------------- output_mode


def test_output_mode_accepts_the_three_modes_and_none():
    for mode in ("tool", "native", "prompted", None):
        alias = ModelAlias(model="test", output_mode=mode)
        assert alias.output_mode == mode


def test_output_mode_rejects_unknown_modes():
    with pytest.raises(ValidationError):
        ModelAlias(model="test", output_mode="telepathy")


def test_output_mode_materializes_in_canonical_bytes():
    workflow = Workflow.model_validate(_minimal(models={"m": {"model": "test"}}))
    assert b'"output_mode":null' in canonical_bytes(workflow)


def test_local_alias_without_output_mode_is_a_validation_error():
    data = _minimal(
        models={
            "local": {
                "model": "ollama:qwen3",
                "settings": {"base_url": "http://localhost:11434/v1"},
            }
        }
    )
    _, issues = validate_data(data)
    assert any(
        i.code == "local_alias_output_mode_required" and i.loc == "models.local.output_mode"
        for i in issues
    )


def test_local_alias_with_explicit_output_mode_validates():
    data = _minimal(
        models={
            "local": {
                "model": "ollama:qwen3",
                "settings": {"base_url": "http://localhost:11434/v1"},
                "output_mode": "native",
            }
        }
    )
    _, issues = validate_data(data)
    assert not [i for i in issues if i.code == "local_alias_output_mode_required"]


def test_hosted_alias_without_output_mode_is_fine():
    data = _minimal(models={"hosted": {"model": "anthropic:claude-haiku-4-5"}})
    _, issues = validate_data(data)
    assert not [i for i in issues if i.code == "local_alias_output_mode_required"]


# ------------------------------------------------------------------- timeout_s


def test_timeout_s_accepted_on_llm_and_llm_judge():
    assert LlmConfig(model="m", prompt="p.md", output_schema={}, timeout_s=30).timeout_s == 30
    assert LlmJudgeConfig(model="m", prompt="p.md", timeout_s=600).timeout_s == 600


def test_timeout_s_defaults_to_none_and_rejects_nonpositive():
    assert LlmConfig(model="m", prompt="p.md", output_schema={}).timeout_s is None
    with pytest.raises(ValidationError):
        LlmConfig(model="m", prompt="p.md", output_schema={}, timeout_s=0)


def test_timeout_s_round_trips_through_yaml_surface():
    data = yaml.safe_load(
        """
        schema_version: "2"
        name: t
        models:
          m: {model: test}
        steps:
          - name: ask
            component: llm
            config: {model: m, prompt: p.md, output_schema: {}, timeout_s: 45}
        """
    )
    workflow = Workflow.model_validate(data)
    config = workflow.steps[0].config
    assert isinstance(config, LlmConfig) and config.timeout_s == 45
    assert b'"timeout_s":45' in canonical_bytes(workflow)


# ------------------------------------------------- new event types (records)
# Additive run-record events Feature 002 requires: each_expanded (fixture 7
# pins zero-item expansions as recorded events) and run_resumed (the R20
# resume boundary). Same-change-set conformance per constitution VI.


def test_each_expanded_event_round_trips_including_zero_items():
    import json
    from datetime import UTC, datetime

    from pipyer.records.run import EachExpandedEvent, event_line

    event = EachExpandedEvent(
        schema_version="1",
        run_id="r1",
        step="grade",
        item_count=0,
        at=datetime(2026, 6, 11, tzinfo=UTC),
    )
    parsed = json.loads(event_line(event))
    assert parsed["event"] == "each_expanded"
    assert parsed["item_count"] == 0


def test_run_resumed_event_carries_the_diff_payload():
    import json
    from datetime import UTC, datetime

    import pytest as _pytest
    from pydantic import ValidationError as _ValidationError

    from pipyer.records.run import RunResumedEvent, event_line

    event = RunResumedEvent(
        schema_version="1",
        run_id="r1",
        resumed_from_status="interrupted",
        skipped=["collect"],
        recompute=[{"key": "grade[2]", "reason": "inputs"}],
        failed_not_retried=["run_tests[1]"],
        failed_retried=[],
        lock_reclaimed=True,
        at=datetime(2026, 6, 11, tzinfo=UTC),
    )
    parsed = json.loads(event_line(event))
    assert parsed["event"] == "run_resumed"
    assert parsed["failed_not_retried"] == ["run_tests[1]"]
    assert parsed["lock_reclaimed"] is True
    with _pytest.raises(_ValidationError):
        # extra='forbid' on the record models: a stale event shape fails loudly.
        RunResumedEvent.model_validate(
            {
                "schema_version": "1",
                "run_id": "r1",
                "resumed_from_status": "interrupted",
                "at": "2026-06-11T00:00:00+00:00",
                "surprise_field": True,
            }
        )
