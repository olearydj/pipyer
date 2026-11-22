from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import statistics
from itertools import combinations
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze three Sonnet stability outputs")
    parser.add_argument("--stability-run-root", type=Path, required=True)
    parser.add_argument("--computed-metrics", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_root = args.stability_run_root.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"refusing to overwrite stability analysis: {output_dir}")
    output_dir.mkdir(parents=True)
    metrics_payload = read_json(args.computed_metrics.resolve())
    metric_by_converter = {
        cell["converter"]: cell["metrics"]
        for cell in metrics_payload["cells"]
        if cell["converter"].startswith("claude_sonnet_5_stability_")
    }

    cells = []
    for repeat in (1, 2, 3):
        converter = f"claude_sonnet_5_stability_{repeat}"
        cell_dir = run_root / "artifacts" / converter / "marketing-deck.pptx"
        output_path = cell_dir / "output.md"
        response_path = cell_dir / "claude-response.json"
        if not output_path.is_file() or not response_path.is_file():
            raise SystemExit(f"missing stability evidence for repeat {repeat}: {cell_dir}")
        response = read_json(response_path)
        text = output_path.read_text(encoding="utf-8")
        cells.append(
            {
                "repeat": repeat,
                "converter": converter,
                "output_path": str(output_path),
                "output_sha256": sha256_file(output_path),
                "output_bytes": output_path.stat().st_size,
                "normalized_text": normalize(text),
                "cost_usd": response.get("total_cost_usd"),
                "metrics": metric_by_converter.get(converter),
            }
        )

    pairwise = []
    for left, right in combinations(cells, 2):
        similarity = difflib.SequenceMatcher(
            None,
            left["normalized_text"],
            right["normalized_text"],
            autojunk=False,
        ).ratio()
        pairwise.append(
            {
                "left_repeat": left["repeat"],
                "right_repeat": right["repeat"],
                "normalized_similarity": round(similarity, 6),
                "normalized_diff_magnitude": round(1.0 - similarity, 6),
                "metric_deltas": metric_deltas(left["metrics"], right["metrics"]),
            }
        )

    sizes = [cell["output_bytes"] for cell in cells]
    costs = [float(cell["cost_usd"]) for cell in cells if cell["cost_usd"] is not None]
    payload = {
        "schema_version": 1,
        "fixture": "marketing-deck.pptx",
        "repeats": [without_text(cell) for cell in cells],
        "unique_output_hashes": len({cell["output_sha256"] for cell in cells}),
        "output_bytes": {
            "minimum": min(sizes),
            "maximum": max(sizes),
            "mean": round(statistics.mean(sizes), 3),
            "population_stddev": round(statistics.pstdev(sizes), 3),
        },
        "cost_usd_total": round(sum(costs), 6),
        "pairwise": pairwise,
        "maximum_normalized_diff_magnitude": max(
            item["normalized_diff_magnitude"] for item in pairwise
        ),
        "maximum_metric_delta": max(
            (
                value
                for pair in pairwise
                for value in pair["metric_deltas"].values()
                if value is not None
            ),
            default=None,
        ),
    }
    write_json(output_dir / "stability.json", payload)
    write_markdown(output_dir / "stability.md", payload)
    print(output_dir)


def metric_deltas(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    if left is None or right is None:
        return {}
    paths = {
        "notes_exact_recall": ("speaker_notes", "exact_recall"),
        "notes_normalized_recall": ("speaker_notes", "normalized_recall"),
        "outline_recall": ("outline", "recall"),
        "coverage_ratio": ("coverage", "ratio"),
        "image_recall": ("image_accounting", "recall"),
        "computed_mean": ("computed_mean",),
    }
    deltas = {}
    for name, path in paths.items():
        left_value = nested(left, path)
        right_value = nested(right, path)
        deltas[name] = (
            None
            if left_value is None or right_value is None
            else round(abs(float(left_value) - float(right_value)), 6)
        )
    return deltas


def nested(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def without_text(cell: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in cell.items() if key != "normalized_text"}


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Sonnet Stability",
        "",
        f"Fixture: `{payload['fixture']}`; unique outputs: {payload['unique_output_hashes']}/3.",
        "",
        "| Pair | Normalized similarity | Diff magnitude | Largest metric delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for pair in payload["pairwise"]:
        metric_values = [value for value in pair["metric_deltas"].values() if value is not None]
        largest = max(metric_values, default=None)
        lines.append(
            f"| {pair['left_repeat']} vs {pair['right_repeat']} | "
            f"{pair['normalized_similarity']:.3f} | "
            f"{pair['normalized_diff_magnitude']:.3f} | "
            f"{format_metric(largest)} |"
        )
    lines.extend(
        [
            "",
            f"Total reported Claude cost: ${payload['cost_usd_total']:.4f}.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def format_metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
