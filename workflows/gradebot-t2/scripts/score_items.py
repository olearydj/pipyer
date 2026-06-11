"""Deterministic scoring: rubric booleans x configured deductions (data, not code).

Implements the archived T2 scoring rules, all delivered as workflow inputs:
llm_score = 1 - item_deduction * (false rubric items); execution failure takes
the execution penalty and (per config) suppresses test penalties; raw score
under the threshold floors to 0. Scores are quantized by construction - the
property the comparison's cause-lookup relies on (FR-022).
"""

import json
import sys


def main() -> None:
    inputs = json.load(sys.stdin)
    items = inputs["items"]
    test_results = inputs["test_results"]
    grades = inputs["grades"]
    rules = inputs["scoring_rules"]

    rows = []
    for index, item in enumerate(items):
        tests = test_results[index] if index < len(test_results) else None
        grade = grades[index] if index < len(grades) else None
        row = {
            "student_id": item["student_id"],
            "problem_meta": item["problem_meta"],
            "problem_key": item["problem_key"],
            "has_submission": item["has_submission"],
            "points": item["points"],
        }
        if grade is None or tests is None:
            row.update(graded=False, total=None, reason="upstream failure (no grade record)")
            rows.append(row)
            continue

        verdicts = {v["key"]: bool(v["verdict"]) for v in grade["items"]}
        false_keys = sorted(
            k for k in (r["key"] for r in item["rubric"]) if not verdicts.get(k, False)
        )
        llm_score = 1.0 - rules["llm_rubric_item_deduction"] * len(false_keys)

        deductions = []
        if not tests["execution_success"]:
            deductions.append(("execution_failure", rules["execution_failure_penalty"]))
            apply_tests = rules.get("apply_test_penalties_when_execution_fails", False)
        else:
            apply_tests = True
        if apply_tests:
            if not tests["example_passed"]:
                deductions.append(("example_test_failure", rules["example_test_failure_penalty"]))
                if not tests["generalization_passed"]:
                    deductions.append(
                        (
                            "generalization_test_failure",
                            rules["generalization_test_failure_if_example_failed_penalty"],
                        )
                    )
            elif not tests["generalization_passed"]:
                deductions.append(
                    ("generalization_test_failure", rules["generalization_test_failure_penalty"])
                )

        raw = round(llm_score - sum(d for _, d in deductions), 2)
        thresholded = raw < rules["minimum_score_threshold"]
        total = 0.0 if thresholded else round(raw * rules["post_threshold_scaling_factor"], 2)
        row.update(
            graded=True,
            llm_score=round(llm_score, 2),
            false_rubric_keys=false_keys,
            deductions=[{"kind": k, "amount": a} for k, a in deductions],
            raw=raw,
            threshold_applied=thresholded,
            total=total,
            weighted=round(total * item["points"], 2),
        )
        rows.append(row)
    json.dump({"rows": rows}, sys.stdout)


if __name__ == "__main__":
    main()
