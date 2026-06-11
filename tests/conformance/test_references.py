"""Reference-grammar conformance: full-match classification, never prefix-match,
never silent literals (data-model.md reference grammar)."""

import pytest

from pipyer.schema.refs import Kind, classify


@pytest.mark.parametrize(
    "value,root,segments",
    [
        ("steps.run_tests.stdout", "steps", ("run_tests", "stdout")),
        ("inputs.data_dir", "inputs", ("data_dir",)),
        ("matrix.grader_model", "matrix", ("grader_model",)),
        ("models.grader", "models", ("grader",)),
        ("item", "item", ()),
        ("index", "index", ()),
        ("item.feedback_path", "item", ("feedback_path",)),
        ("steps.collect.items.0", "steps", ("collect", "items", "0")),
    ],
)
def test_full_grammar_match_is_a_ref(value, root, segments):
    kind, ref = classify(value)
    assert kind is Kind.REF
    assert ref is not None
    assert ref.root == root
    assert ref.segments == segments


@pytest.mark.parametrize(
    "value",
    [
        "hello world",
        "steps are good",  # root word not followed by '.' or end-of-string
        "Inputs.x",  # roots are case-sensitive
        "stepsX.y",
        "a steps.b.c",  # ref-like text not at string start
        42,
        None,
        ["steps.a.b"],
    ],
)
def test_non_ref_intent_is_literal(value):
    kind, ref = classify(value)
    assert kind is Kind.LITERAL
    assert ref is None


@pytest.mark.parametrize(
    "value",
    [
        "steps.run_tests.stdout plus trailing text",
        "inputs",  # named roots need at least one segment
        "steps",
        "models",
        "steps.",
        "inputs..x",
        "steps.run-tests.out",  # '-' not in segment grammar
        "item.",
    ],
)
def test_root_prefixed_non_grammar_is_an_error_never_a_literal(value):
    kind, ref = classify(value)
    assert kind is Kind.ERROR
    assert ref is None


def test_error_message_names_the_escape_hatch():
    from pipyer.schema.refs import ESCAPE_HATCH

    assert "declare" in ESCAPE_HATCH and "workflow input" in ESCAPE_HATCH


def test_item_scope_enforced_by_validation():
    from pipyer.validation import validate_data

    data = {
        "schema_version": "1",
        "name": "scope",
        "steps": [
            {"name": "src", "component": "python", "config": {"script": "s.py"}},
            {
                "name": "fan",
                "component": "python",
                "config": {"script": "t.py"},
                "each": "steps.src.items",
                "inputs": {"value": "item", "position": "index"},
            },
        ],
    }
    _, issues = validate_data(data, base_dir=None)
    assert issues == [], [f"{i.loc}: {i.code}" for i in issues]
