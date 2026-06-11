"""Canonical-serialization conformance: one definition serving dual-surface
equality, hashing, and resume matching (R7)."""

from pathlib import Path

import yaml

from pipyer.canonical import canonical_bytes, workflow_hash
from pipyer.schema.workflow import PythonConfig, PythonStep, Settings, Workflow

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load_workflow(path: Path) -> Workflow:
    return Workflow.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def test_canonical_bytes_stable_across_repeated_serialization():
    workflow = _load_workflow(FIXTURES / "valid" / "minimal.yaml")
    assert canonical_bytes(workflow) == canonical_bytes(workflow)
    assert workflow_hash(workflow) == workflow_hash(workflow)
    assert workflow_hash(workflow).startswith("sha256:")


def test_defaults_materialize_identically_from_both_surfaces():
    # YAML surface omits every optional section; direct construction materializes
    # defaults explicitly. R7: identical canonical bytes either way.
    from_yaml = _load_workflow(FIXTURES / "valid" / "minimal.yaml")
    constructed = Workflow(
        schema_version="2",
        name="minimal",
        steps=[
            PythonStep(
                name="transform",
                component="python",
                config=PythonConfig(script="scripts/noop.py"),
            )
        ],
        settings=Settings(),
    )
    assert canonical_bytes(from_yaml) == canonical_bytes(constructed)
    assert workflow_hash(from_yaml) == workflow_hash(constructed)


def test_defaults_are_materialized_in_canonical_bytes():
    workflow = _load_workflow(FIXTURES / "valid" / "minimal.yaml")
    blob = canonical_bytes(workflow).decode("utf-8")
    # minimal.yaml declares no settings; the canonical form carries them anyway.
    assert '"concurrency":1' in blob
    assert '"results_dir":"runs"' in blob
    assert '"max_failures":null' in blob


def test_schema_version_participates_in_canonical_bytes():
    workflow = _load_workflow(FIXTURES / "valid" / "minimal.yaml")
    assert '"schema_version":"2"' in canonical_bytes(workflow).decode("utf-8")


def test_canonical_form_is_sorted_compact_json():
    workflow = _load_workflow(FIXTURES / "valid" / "full_featured.yaml")
    blob = canonical_bytes(workflow).decode("utf-8")
    assert ": " not in blob and ", " not in blob  # compact separators
    import json

    data = json.loads(blob)
    assert list(data.keys()) == sorted(data.keys())
