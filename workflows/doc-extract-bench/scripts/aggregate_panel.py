from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate blinded two-family pair judgments")
    parser.add_argument("--pair-key", type=Path, required=True)
    parser.add_argument("--judge-output-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"refusing to overwrite panel aggregation: {output_dir}")
    output_dir.mkdir(parents=True)
    key = read_json(args.pair_key.resolve())["pairs"]
    judge_root = args.judge_output_root.resolve()
    decisions = []
    by_pair: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for item in key:
        for judge in ("claude", "codex"):
            path = judge_root / judge / item["pair_id"] / "decision.json"
            if not path.is_file():
                raise SystemExit(f"missing judge decision: {path}")
            decision = read_json(path)
            winner = item["a_converter"] if decision["winner"] == "A" else item["b_converter"]
            challenger_win = winner == item["challenger"]
            record = {
                "pair_id": item["pair_id"],
                "document": item["document"],
                "judge": judge,
                "winner_label": decision["winner"],
                "winner_converter": winner,
                "challenger": item["challenger"],
                "reference_converter": item["reference_converter"],
                "challenger_win": challenger_win,
                "reason": decision["reason"],
                "cost_usd": decision.get("cost_usd"),
                "usage": decision.get("usage"),
            }
            decisions.append(record)
            by_pair[item["pair_id"]][judge] = record

    panel_pairs = []
    for item in key:
        pair_decisions = by_pair[item["pair_id"]]
        winners = [pair_decisions[judge]["winner_converter"] for judge in ("claude", "codex")]
        panel_pairs.append(
            {
                "pair_id": item["pair_id"],
                "document": item["document"],
                "challenger": item["challenger"],
                "unanimous": winners[0] == winners[1],
                "winner_converter": winners[0] if winners[0] == winners[1] else None,
                "judge_winners": {
                    judge: pair_decisions[judge]["winner_converter"]
                    for judge in pair_decisions
                },
            }
        )

    rankings = build_rankings(decisions)
    kappa = cohen_kappa(by_pair)
    claude_cost = sum(
        float(item["cost_usd"])
        for item in decisions
        if item["judge"] == "claude" and item["cost_usd"] is not None
    )
    payload = {
        "schema_version": 1,
        "panel": ["claude", "codex"],
        "third_family": {
            "available": False,
            "reason": "Gemini CLI was not installed on the benchmark host.",
        },
        "pair_count": len(key),
        "decision_count": len(decisions),
        "decisions": decisions,
        "pairs": panel_pairs,
        "rankings": rankings,
        "agreement": kappa,
        "cost": {
            "claude_usd_total": round(claude_cost, 6),
            "codex_usd_total": None,
            "codex_cost_basis": "CLI exposed token usage but no dollar-cost field.",
        },
    }
    write_json(output_dir / "panel-results.json", payload)
    write_markdown(output_dir / "panel-summary.md", payload)
    print(output_dir)


def build_rankings(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision in decisions:
        grouped[decision["challenger"]].append(decision)
    rankings = []
    for challenger, items in grouped.items():
        wins = sum(1 for item in items if item["challenger_win"])
        by_document = {}
        for document in sorted({item["document"] for item in items}):
            document_items = [item for item in items if item["document"] == document]
            document_wins = sum(1 for item in document_items if item["challenger_win"])
            by_document[document] = {
                "wins": document_wins,
                "decisions": len(document_items),
                "win_rate": round(document_wins / len(document_items), 6),
            }
        rankings.append(
            {
                "challenger": challenger,
                "wins": wins,
                "decisions": len(items),
                "win_rate": round(wins / len(items), 6),
                "by_document": by_document,
            }
        )
    return sorted(rankings, key=lambda item: (-item["win_rate"], item["challenger"]))


def cohen_kappa(
    by_pair: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    labels = []
    for pair_id in sorted(by_pair):
        labels.append(
            (
                by_pair[pair_id]["claude"]["winner_label"],
                by_pair[pair_id]["codex"]["winner_label"],
            )
        )
    observed = sum(1 for left, right in labels if left == right) / len(labels)
    left_counts = Counter(left for left, _ in labels)
    right_counts = Counter(right for _, right in labels)
    expected = sum(
        (left_counts[label] / len(labels)) * (right_counts[label] / len(labels))
        for label in ("A", "B")
    )
    kappa = 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)
    return {
        "cohen_kappa": round(kappa, 6),
        "observed_agreement": round(observed, 6),
        "expected_agreement": round(expected, 6),
        "agreements": sum(1 for left, right in labels if left == right),
        "comparisons": len(labels),
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    agreement = payload["agreement"]
    lines = [
        "# Pairwise Panel Summary",
        "",
        (
            f"Two-family panel: {payload['pair_count']} blinded pairs and "
            f"{payload['decision_count']} forced-choice decisions."
        ),
        "",
        (
            f"Inter-judge agreement: κ={agreement['cohen_kappa']:.3f}; observed "
            f"agreement={agreement['observed_agreement']:.3f} "
            f"({agreement['agreements']}/{agreement['comparisons']})."
        ),
        "",
        "| Challenger | Wins | Decisions | Win rate vs Sonnet |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in payload["rankings"]:
        lines.append(
            f"| {item['challenger']} | {item['wins']} | {item['decisions']} | "
            f"{item['win_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            f"Claude judging cost: ${payload['cost']['claude_usd_total']:.4f}. ",
            "Codex judging dollar cost is unavailable from the CLI.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
