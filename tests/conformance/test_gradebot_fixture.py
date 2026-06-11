"""The first conformance fixture and the falsification test's mechanical half
(SC-003): both surfaces validate, byte-identical canonical serialization, zero
forbidden constructs. The judgment half is the census (exit-notes.md)."""

import re
import sys
from pathlib import Path

import yaml

from pipyer.canonical import canonical_bytes, workflow_hash
from pipyer.validation import validate_data

GRADEBOT = Path(__file__).resolve().parents[1] / "fixtures" / "gradebot"

sys.path.insert(0, str(GRADEBOT))
from construct import build  # noqa: E402  # ty: ignore[unresolved-import]  (sys.path fixture)


def _yaml_workflow():
    data = yaml.safe_load((GRADEBOT / "workflow.yaml").read_text(encoding="utf-8"))
    workflow, issues = validate_data(data, base_dir=GRADEBOT)
    assert issues == [], [f"{i.loc}: {i.code}: {i.message}" for i in issues]
    return workflow


def test_yaml_surface_validates():
    assert _yaml_workflow() is not None


def test_python_construction_surface_validates():
    from pipyer.validation import validate_workflow

    workflow = build()
    issues = validate_workflow(workflow, base_dir=GRADEBOT)
    assert issues == [], [f"{i.loc}: {i.code}: {i.message}" for i in issues]


def test_both_surfaces_produce_byte_identical_canonical_serialization():
    from_yaml = _yaml_workflow()
    constructed = build()
    assert canonical_bytes(from_yaml) == canonical_bytes(constructed)
    assert workflow_hash(from_yaml) == workflow_hash(constructed)


FORBIDDEN_CONSTRUCTS = [
    (re.compile(r"\{\{"), "template interpolation {{"),
    (re.compile(r"\{%"), "template statement {%"),
    (re.compile(r"\$\{"), "shell-style interpolation ${"),
    (re.compile(r"^\s*(if|for|while)\s*:", re.MULTILINE), "control-flow key"),
    (re.compile(r"!\w+\s"), "yaml tag (safe_load would reject, belt and braces)"),
]


def test_fixture_contains_zero_forbidden_constructs():
    text = (GRADEBOT / "workflow.yaml").read_text(encoding="utf-8")
    hits = [label for pattern, label in FORBIDDEN_CONSTRUCTS if pattern.search(text)]
    assert hits == []


def test_fixture_exercises_the_logical_description():
    # SPEC section 9: collect, run tests per submission, grade each against a
    # rubric prompt with structured output, validate, write per-student
    # feedback and a summary report.
    workflow = _yaml_workflow()
    components = [step.component for step in workflow.steps]
    assert components == [
        "python",
        "file_read",
        "shell",
        "file_read",
        "llm",
        "assertions",
        "file_write",
        "python",
        "file_write",
    ]
    each_steps = [step.name for step in workflow.steps if step.each]
    assert each_steps == ["run_tests", "read_submission", "grade", "check_grades", "write_feedback"]
    assert workflow.settings.max_failures is not None  # failure budget present
