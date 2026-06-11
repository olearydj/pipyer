"""assertions executor: evaluate the configured checks against bound inputs."""

from __future__ import annotations

import re
from typing import Any

from pipyer.records.step_result import ErrorCategory
from pipyer.runner.components import StepFailure


def _evaluate(op: str, value: Any, expected: Any) -> bool:
    if op == "equals":
        return value == expected
    if op == "not_equals":
        return value != expected
    if op == "contains":
        return expected in value
    if op == "matches":
        return isinstance(value, str) and re.search(str(expected), value) is not None
    if op == "gte":
        return value >= expected
    if op == "lte":
        return value <= expected
    if op == "exists":
        return value is not None
    if op == "non_empty":
        return bool(value)
    raise ValueError(f"unknown check op {op!r}")


def execute(step, resolved_inputs: dict[str, Any], ctx, index) -> dict[str, Any]:
    results = []
    failures = []
    for check in step.config.checks:
        value = resolved_inputs.get(check.input)
        try:
            passed = _evaluate(check.op, value, check.expected)
        except TypeError:
            passed = False
        results.append(
            {"input": check.input, "op": check.op, "expected": check.expected, "passed": passed}
        )
        if not passed:
            failures.append(f"{check.input} {check.op} {check.expected!r} (got {value!r})")
    if failures:
        raise StepFailure(
            ErrorCategory.ASSERTION_FAILED,
            f"{len(failures)} of {len(results)} checks failed",
            detail={"checks": results, "failed": failures},
        )
    return {"output": {"passed": True, "checks": results}}
