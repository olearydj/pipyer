"""Summarize the batch: per-student table, score statistics, failure roll-up.

Aggregation across aligned per-item collections (grades, test results,
submissions arrive index-aligned). This is genuine domain computation - means,
counts, a readable report - not string assembly around a single value.
"""

import json
import sys


def main() -> None:
    inputs = json.load(sys.stdin)
    submissions = inputs["submissions"]
    grades = inputs["grades"]
    test_results = inputs["test_results"]

    rows = []
    scores = []
    for index, submission in enumerate(submissions):
        grade = grades[index] if index < len(grades) else None
        tests = test_results[index] if index < len(test_results) else None
        if grade is not None:
            scores.append(grade["score"])
            rows.append(
                f"| {submission['student']} | {grade['score']} | "
                f"{(tests or {}).get('summary', 'n/a')} |"
            )
        else:
            rows.append(f"| {submission['student']} | not graded | tests failed |")

    stats = {
        "submissions": len(submissions),
        "graded": len(scores),
        "ungraded": len(submissions) - len(scores),
        "mean_score": round(sum(scores) / len(scores), 1) if scores else None,
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
    }

    report = "\n".join(
        [
            "# Grading summary",
            "",
            f"Submissions: {stats['submissions']}, graded: {stats['graded']}, "
            f"ungraded: {stats['ungraded']}.",
            f"Scores: mean {stats['mean_score']}, min {stats['min_score']}, "
            f"max {stats['max_score']}.",
            "",
            "| Student | Score | Tests |",
            "|---------|-------|-------|",
            *rows,
            "",
        ]
    )
    json.dump({"report_markdown": report, "stats": stats}, sys.stdout)


if __name__ == "__main__":
    main()
