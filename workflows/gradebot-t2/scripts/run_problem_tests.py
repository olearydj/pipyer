"""Execute one problem's test cases against one submission.

A failing submission is a valid grading OUTCOME, not a workflow failure: this
harness always exits 0 and reports execution/test results as data (unlike a CI
gate). The first config test case is the example, the second the
generalization, matching the archived scoring semantics.
"""

import json
import sys


def run_case(fn, case):
    try:
        got = fn(*case["inputs"])
    except Exception as error:  # student code; any failure is an outcome
        return {"description": case["description"], "passed": False, "error": repr(error)}
    expected = case["expected_return"]
    # exact_match with list/tuple leniency (students legitimately return either)
    normalize = lambda v: list(v) if isinstance(v, tuple) else v  # noqa: E731
    passed = normalize(got) == normalize(expected)
    return {
        "description": case["description"],
        "passed": passed,
        "got": repr(got) if not passed else None,
        "expected": repr(expected) if not passed else None,
    }


def main() -> None:
    inputs = json.load(sys.stdin)
    code = inputs["submission_code"]
    function_name = inputs["function_name"]
    cases = inputs["test_cases"]

    result: dict = {"execution_success": False, "cases": [], "error": None}
    namespace: dict = {}
    if not code.strip():
        result["error"] = "no submission"
    else:
        try:
            exec(compile(code, "<submission>", "exec"), namespace)  # trusted course harness
            fn = namespace.get(function_name)
            if fn is None:
                result["error"] = f"function {function_name!r} not defined"
            else:
                result["execution_success"] = True
                result["cases"] = [run_case(fn, case) for case in cases]
        except Exception as error:
            result["error"] = repr(error)

    passed = [c["passed"] for c in result["cases"]]
    result["example_passed"] = bool(passed and passed[0])
    result["generalization_passed"] = bool(len(passed) > 1 and passed[1])
    result["summary"] = (
        f"execution {'ok' if result['execution_success'] else 'FAILED'}; "
        f"{sum(passed)}/{len(cases)} tests passed"
        + (f"; error: {result['error']}" if result["error"] else "")
    )
    json.dump(result, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
