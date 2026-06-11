"""The layered comparison record (FR-021/FR-022; clarifications Q1-Q2).

Per (student, problem) entry: the workflow's score beside the raw v2 machine
baseline and the published v2-patched baseline, separately. The headline is
per-entry exact-match rate (the metric the 1.7% nondeterminism floor was
measured in). Deltas are quantized, so the implied cause is a lookup, not
analysis. Every disagreement classifies as agrees / expected_human_correction
(known-patched, academic-integrity override) / unexplained - the
unexplained-above-floor figure is what SC-008's cross-session review turns on.
"""

import csv
import json
import sys
from pathlib import Path

CAUSE_LOOKUP = [
    (0.12, "one rubric item flipped"),
    (0.24, "two rubric items flipped"),
    (0.36, "three rubric items flipped"),
    (0.48, "four rubric items flipped"),
    (0.20, "execution penalty differed"),
    (0.10, "one test penalty differed"),
    (0.08, "rubric item vs test penalty differed (0.12 vs 0.20 interplay)"),
    (0.02, "rubric item + test penalty combination"),
]


def implied_cause(delta: float, ours: float, baseline: float) -> str:
    if ours == 0.0 or baseline == 0.0:
        return "threshold crossing (raw below 0.35 on one side)"
    magnitude = round(abs(delta), 2)
    for amount, cause in CAUSE_LOOKUP:
        if magnitude == amount:
            return cause
    return f"composite delta {magnitude} (multiple judgments moved)"


def load_baseline(path: str) -> dict[tuple[str, str], float]:
    scores: dict[tuple[str, str], float] = {}
    with Path(path).open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            scores[(row["Student ID"], row["Problem ID"])] = float(row["Total Score"])
    return scores


def load_patches(path: str) -> set[tuple[str, str]]:
    if not path:
        return set()
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    patched: set[tuple[str, str]] = set()
    for change in manifest.get("changes", []):
        student = str(change.get("student_id", change.get("student", "")))
        meta = str(change.get("problem_id", change.get("problem", "")))
        if student and meta:
            patched.add((student, meta))
    return patched


def main() -> None:
    inputs = json.load(sys.stdin)
    rows = inputs["rows"]
    raw_baseline = load_baseline(inputs["raw_baseline_csv"])
    published_baseline = load_baseline(inputs["published_baseline_csv"])
    patched = load_patches(inputs.get("patch_manifest", ""))
    annotations = (
        json.loads(Path(inputs["annotations_file"]).read_text(encoding="utf-8"))
        if inputs.get("annotations_file")
        else {}
    )
    overrides = {
        str(o["student_id"]): o for o in annotations.get("academic_integrity_overrides", [])
    }
    absent = annotations.get("absent_students", [])

    entries = []
    for row in rows:
        key = (row["student_id"], row["problem_meta"])
        entry = dict(row)
        for label, baseline in (("raw_v2", raw_baseline), ("published", published_baseline)):
            base = baseline.get(key)
            ours = row.get("total")
            if base is None or ours is None:
                entry[label] = {"score": base, "match": None, "delta": None}
                continue
            delta = round(ours - base, 2)
            comparison = {"score": base, "match": delta == 0.0, "delta": delta}
            if delta != 0.0:
                comparison["implied_cause"] = implied_cause(delta, ours, base)
            entry[label] = comparison
        entry["known_patched"] = key in patched
        if row["student_id"] in overrides:
            # Compare against the GRADED score (the raw baseline), surface the
            # override as an annotation - never silently reconcile (US4).
            entry["annotation"] = (
                "academic-integrity override: published score deliberately differs from "
                "graded score - " + overrides[row["student_id"]].get("note", "")
            )
        # Classification against the published (human-reviewed) baseline.
        pub = entry["published"]
        if pub["match"] is None:
            entry["classification"] = "ungraded"
        elif pub["match"]:
            entry["classification"] = "agrees"
        elif entry["known_patched"] or row["student_id"] in overrides:
            entry["classification"] = "expected_human_correction"
        else:
            entry["classification"] = "unexplained"
        entries.append(entry)

    graded = [e for e in entries if e.get("total") is not None]

    def match_rate(label):
        comparable = [e for e in graded if e[label]["match"] is not None]
        if not comparable:
            return None, 0
        return round(sum(e[label]["match"] for e in comparable) / len(comparable), 4), len(
            comparable
        )

    raw_rate, raw_n = match_rate("raw_v2")
    pub_rate, pub_n = match_rate("published")
    counts = {"agrees": 0, "expected_human_correction": 0, "unexplained": 0, "ungraded": 0}
    for entry in entries:
        counts[entry["classification"]] += 1
    unexplained_rate = round(counts["unexplained"] / max(1, len(graded)), 4)

    stats = {
        "entries": len(entries),
        "graded": len(graded),
        "no_submission_rows": sum(1 for e in entries if not e["has_submission"]),
        "raw_v2_exact_match_rate": raw_rate,
        "raw_v2_compared": raw_n,
        "published_exact_match_rate": pub_rate,
        "published_compared": pub_n,
        "classification_counts": counts,
        "unexplained_rate": unexplained_rate,
        "nondeterminism_floor": 0.017,
        "unexplained_above_floor": round(max(0.0, unexplained_rate - 0.017), 4),
        "absent_students_annotated": absent,
    }

    disagreements = [
        e for e in entries if e["classification"] in ("expected_human_correction", "unexplained")
    ]
    lines = [
        "# T2 comparison record",
        "",
        f"Entries: {stats['entries']} ({stats['no_submission_rows']} without submissions).",
        f"Raw v2 exact-match: {raw_rate} over {raw_n}; "
        f"published exact-match: {pub_rate} over {pub_n}.",
        f"Unexplained: {counts['unexplained']} ({unexplained_rate:.1%}), floor 1.7%.",
        "",
        "| Student | Problem | Ours | Raw v2 | Published | Class | Cause |",
        "|---------|---------|------|--------|-----------|-------|-------|",
    ]
    for e in disagreements:
        lines.append(
            f"| {e['student_id']} | {e['problem_key']} | {e.get('total')} "
            f"| {e['raw_v2']['score']} | {e['published']['score']} | {e['classification']} "
            f"| {e['published'].get('implied_cause', '')} |"
        )
    if absent:
        lines += [
            "",
            "Absent students (no baseline rows, annotated): " + ", ".join(map(str, absent)),
        ]

    json.dump({"entries": entries, "stats": stats, "report_markdown": "\n".join(lines)}, sys.stdout)


if __name__ == "__main__":
    main()
