"""Run the assignment's checks against one submission.

This is the assignment's test harness: it compiles the submission, executes the
assignment's behavioral checks against it, and summarizes the outcome as JSON
for the grader. Exit status follows the shell-component convention: nonzero
when the submission fails, so the item records a failure.
"""

import json
import sys
from pathlib import Path


def check_compiles(source: str, name: str) -> dict:
    try:
        compile(source, name, "exec")
        return {"name": "compiles", "passed": True}
    except SyntaxError as error:
        return {"name": "compiles", "passed": False, "detail": str(error)}


def check_add_behavior(source: str, name: str) -> dict:
    """The assignment: implement add(a, b)."""
    namespace: dict = {}
    try:
        exec(compile(source, name, "exec"), namespace)  # trusted course material
        add = namespace["add"]
        cases = [((1, 2), 3), ((-1, 1), 0), ((0, 0), 0)]
        failures = [f"add{args!r} != {want}" for args, want in cases if add(*args) != want]
        return {"name": "add_behavior", "passed": not failures, "detail": failures or None}
    except BaseException as error:  # missing function, runtime error, sys.exit, ...
        return {"name": "add_behavior", "passed": False, "detail": repr(error)}


def main() -> None:
    inputs = json.load(sys.stdin)
    path = Path(inputs["submission_path"])
    source = path.read_text(encoding="utf-8")

    checks = [check_compiles(source, path.name)]
    if checks[0]["passed"]:
        checks.append(check_add_behavior(source, path.name))

    passed = all(c["passed"] for c in checks)
    json.dump(
        {
            "passed": passed,
            "checks": checks,
            "summary": f"{sum(c['passed'] for c in checks)}/{len(checks)} checks passed",
        },
        sys.stdout,
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
