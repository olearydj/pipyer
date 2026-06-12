"""Workflow-schema conformance: valid fixtures accepted, invalid rejected with
location-pathed, coded errors (SC-004); plus the FR-013 uniformity tripwire."""

from pathlib import Path

import pytest
import yaml

from pipyer.schema import workflow as wf_mod
from pipyer.validation import validate_data

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# fixture stem → (expected code, expected loc substring)
INVALID_EXPECTATIONS = {
    "unknown_field": ("extra_forbidden", "sneaky_extra"),
    "dangling_step_ref": ("unknown_step_ref", "steps[1].inputs.test_output"),
    "forward_step_ref": ("forward_step_ref", "steps[0].inputs.later_value"),
    "self_step_ref": ("self_step_ref", "steps[0].inputs.me"),
    "item_outside_each": ("item_outside_each", "steps[0].inputs.value"),
    "unknown_model_alias": ("unknown_model_alias", "steps[0].config.model"),
    "unbound_placeholder": ("unbound_placeholder", "steps[0].config.prompt"),
    "unused_prompt_binding": ("unused_prompt_binding", "steps[0].inputs.stray"),
    "duplicate_step_names": ("duplicate_step_name", "steps[1].name"),
    "unsupported_schema_version": ("unsupported_schema_version", "schema_version"),
    "matrix_non_list": ("list_type", "matrix.model"),
    "matrix_empty_dimension": ("too_short", "matrix.model"),
    "root_prefixed_non_ref": ("malformed_ref", "steps[0].inputs.note"),
    "missing_python_script": ("script_file_missing", "steps[0].config.script"),
}


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted((FIXTURES / "valid").glob("*.yaml")), ids=lambda p: p.stem)
def test_valid_fixture_accepted(path: Path):
    workflow, issues = validate_data(_load(path), base_dir=path.parent)
    assert issues == [], [f"{i.loc}: {i.code}: {i.message}" for i in issues]
    assert workflow is not None


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "invalid").glob("*.yaml")), ids=lambda p: p.stem
)
def test_invalid_fixture_rejected_with_location_and_code(path: Path):
    expected_code, expected_loc = INVALID_EXPECTATIONS[path.stem]
    _, issues = validate_data(_load(path), base_dir=path.parent)
    assert issues, f"{path.stem} unexpectedly validated"
    matches = [i for i in issues if i.code == expected_code and expected_loc in i.loc]
    assert matches, (
        f"{path.stem}: wanted code={expected_code} at loc~{expected_loc}, got "
        + "; ".join(f"{i.loc}:{i.code}" for i in issues)
    )
    # Legible, never unlocatable: every issue names a location.
    assert all(i.loc for i in issues)


def test_every_invalid_fixture_has_an_expectation():
    stems = {p.stem for p in (FIXTURES / "invalid").glob("*.yaml")}
    assert stems == set(INVALID_EXPECTATIONS)


# ---- FR-013 tripwire: uniformity by construction --------------------------------
# These golden field sets exist so any future field addition to the step surface is
# a conscious decision reviewed against FR-013 (no per-item variation mechanism),
# not a silent drift. Update deliberately or not at all.

STEP_SURFACE = {"name", "component", "config", "inputs", "each"}

CONFIG_SURFACES = {
    "FileReadConfig": {"path", "format"},
    "FileWriteConfig": {"path", "format"},
    "ShellConfig": {"command", "parse_stdout", "timeout_s"},
    "PythonConfig": {"script", "timeout_s"},
    "LlmConfig": {"model", "prompt", "output_schema", "max_validation_retries", "timeout_s"},
    "LlmJudgeConfig": {"model", "prompt", "output_schema", "max_validation_retries", "timeout_s"},
    "AssertionsConfig": {"checks"},
}


def test_fr013_tripwire_step_surface_has_no_per_item_variation():
    for step_cls in wf_mod.STEP_CLASSES:
        assert set(step_cls.model_fields) == STEP_SURFACE, step_cls.__name__


def test_fr013_tripwire_component_config_surfaces():
    from pipyer.schema import components

    for name, fields in CONFIG_SURFACES.items():
        cls = getattr(components, name)
        assert set(cls.model_fields) == fields, name


ALIAS_SURFACE = {"model", "settings", "output_mode"}


def test_fr013_tripwire_model_alias_surface():
    assert set(wf_mod.ModelAlias.model_fields) == ALIAS_SURFACE
