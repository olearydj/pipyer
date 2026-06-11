"""Collect the T2 grading items: one per (student, problem) row of the baseline.

The baseline CSV's own row set is truth (analyze finding U2): exactly its 188
(student, problem) pairs become items, so the comparison aligns by construction
and no-submission rows are explicit items, never omissions. Each item carries
everything downstream steps need - the latest submission's code (filename
timestamps order attempts), the problem's test cases, rubric, and context from
the corpus config - so grading is parameterized by data, not code (FR-020).
"""

import csv
import json
import sys
from pathlib import Path


def main() -> None:
    inputs = json.load(sys.stdin)
    corpus = Path(inputs["corpus_dir"])
    baseline_csv = Path(inputs["baseline_csv"])
    if not baseline_csv.is_absolute():
        baseline_csv = corpus / baseline_csv

    config = json.loads((corpus / inputs["config_file"]).read_text(encoding="utf-8"))
    meta_to_key = config["metadata_problem_id_map"]
    problems = config["problems"]
    weights = inputs["point_weights"]

    pairs: list[tuple[str, str]] = []
    seen = set()
    with baseline_csv.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            pair = (row["Student ID"], row["Problem ID"])
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    pairs.sort()

    items = []
    for student_id, meta in pairs:
        key = meta_to_key[meta]
        problem = problems[key]
        student_dir = corpus / "inputs" / "submissions" / student_id
        candidates = sorted(student_dir.glob(f"{meta}_*.py")) if student_dir.is_dir() else []
        code = candidates[-1].read_text(encoding="utf-8", errors="replace") if candidates else ""
        rubric = problem.get("llm_rubric", [])
        items.append(
            {
                "student_id": student_id,
                "problem_key": key,
                "problem_meta": meta,
                "code": code,
                "has_submission": bool(candidates),
                "function_name": problem["code_runner"]["function_name"],
                "test_cases": problem["code_runner"]["test_cases"],
                "rubric": rubric,
                "rubric_text": "\n".join(f"- `{r['key']}`: {r['statement']}" for r in rubric),
                "problem_context": problem.get("llm_problem_context", problem["description"]),
                "points": weights[meta],
                "feedback_path": f"feedback/{student_id}_{key}.md",
            }
        )

    def resolved(name: str) -> str:
        value = inputs.get(name, "")
        if not value:
            return ""
        path = Path(value)
        return str(path if path.is_absolute() else corpus / path)

    json.dump(
        {
            "items": items,
            "count": len(items),
            "raw_baseline_path": str(baseline_csv),
            "published_baseline_path": resolved("published_baseline_csv"),
            "patch_manifest_path": resolved("patch_manifest"),
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
