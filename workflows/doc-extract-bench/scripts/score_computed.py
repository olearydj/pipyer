from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
DEFAULT_GOLD = ROOT / "fixtures" / "gold"
DEFAULT_RUN_ROOTS = [
    REPO_ROOT / "runs" / "doc-extract-bench" / "2026-07-27-harness-02",
    REPO_ROOT / "runs" / "doc-extract-bench" / "2026-07-27-docling-01",
    REPO_ROOT / "runs" / "doc-extract-bench" / "2026-07-27-round2-convert-01",
]

DOCUMENTS = (
    "meeting-notes.docx",
    "software-doc.pdf",
    "marketing-deck.pptx",
    "ti-datasheet.pdf",
)


class CellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"td", "th"}:
            if self._depth == 0:
                self._parts = []
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag not in {"td", "th"} or self._depth == 0:
            return
        self._depth -= 1
        if self._depth == 0:
            self.cells.append(" ".join(self._parts))
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._parts.append(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score deterministic document metrics")
    parser.add_argument("--gold-root", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--run-root", type=Path, action="append", dest="run_roots")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-unverified", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold_root = args.gold_root.resolve()
    manifest = read_json(gold_root / "MANIFEST.json")
    if manifest.get("status") != "verified" and not args.allow_unverified:
        raise SystemExit(
            "gold references are not verified; pass --allow-unverified only for provisional scoring"
        )
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"refusing to overwrite computed-metrics directory: {output_dir}")
    output_dir.mkdir(parents=True)

    gold = load_gold(gold_root)
    run_roots = [path.resolve() for path in (args.run_roots or DEFAULT_RUN_ROOTS)]
    cells = discover_cells(run_roots)
    metrics = [score_cell(cell, gold, gold_root) for cell in cells]
    payload = {
        "schema_version": 1,
        "status": "provisional" if manifest.get("status") != "verified" else "final",
        "gold_status": manifest.get("status"),
        "gold_manifest_sha256": sha256_file(gold_root / "MANIFEST.json"),
        "metric_definitions": metric_definitions(),
        "run_roots": [str(path) for path in run_roots],
        "cells": metrics,
    }
    write_json(output_dir / "computed-metrics.json", payload)
    write_json(output_dir / "cell-registry.json", {"cells": cells})
    write_csv(output_dir / "computed-metrics.csv", metrics)
    write_summary(output_dir / "computed-summary.md", payload)
    print(output_dir)


def load_gold(gold_root: Path) -> dict[str, Any]:
    return {
        "outlines": read_json(gold_root / "outlines.json")["documents"],
        "notes": read_json(gold_root / "speaker-notes.json")["notes"],
        "tables": read_json(gold_root / "table-grids.json")["documents"],
        "visuals": read_json(gold_root / "visual-units.json")["documents"],
        "raw_text": {
            document: (gold_root / "raw-text" / f"{document}.txt").read_text(encoding="utf-8")
            for document in DOCUMENTS
        },
    }


def discover_cells(run_roots: list[Path]) -> list[dict[str, Any]]:
    cells = []
    seen = set()
    for run_root in run_roots:
        artifacts = run_root / "artifacts"
        if not artifacts.is_dir():
            raise SystemExit(f"run root has no artifacts directory: {run_root}")
        for output_path in sorted(artifacts.glob("*/*/output.md")):
            converter = output_path.parents[1].name
            document = output_path.parent.name
            key = (run_root.name, converter, document)
            if key in seen:
                raise SystemExit(f"duplicate cell discovered: {key}")
            seen.add(key)
            cells.append(
                {
                    "cell_id": f"{run_root.name}/{converter}/{document}",
                    "run": run_root.name,
                    "converter": converter,
                    "document": document,
                    "status": "succeeded",
                    "output_path": str(output_path.resolve()),
                    "output_sha256": sha256_file(output_path),
                    "output_bytes": output_path.stat().st_size,
                }
            )

    round2_root = next(
        (path for path in run_roots if path.name == "2026-07-27-round2-convert-01"), None
    )
    if round2_root:
        for converter in ("deepseek_ocr2_mlx", "dots_ocr_mlx"):
            for document in ("meeting-notes.docx", "marketing-deck.pptx"):
                key = (round2_root.name, converter, document)
                if key in seen:
                    continue
                cells.append(
                    {
                        "cell_id": f"{round2_root.name}/{converter}/{document}",
                        "run": round2_root.name,
                        "converter": converter,
                        "document": document,
                        "status": "not_applicable",
                        "reason": "PDF-only local OCR runtime; Office input intentionally N/A.",
                        "output_path": None,
                        "output_sha256": None,
                        "output_bytes": None,
                    }
                )
    return sorted(cells, key=lambda item: item["cell_id"])


def score_cell(
    cell: dict[str, Any],
    gold: dict[str, Any],
    gold_root: Path,
) -> dict[str, Any]:
    result = dict(cell)
    if cell["status"] != "succeeded":
        result["metrics"] = None
        return result
    output_path = Path(cell["output_path"])
    output = output_path.read_text(encoding="utf-8", errors="replace")
    document = cell["document"]

    notes = score_notes(output, gold["notes"]) if document == "marketing-deck.pptx" else None
    outline = score_outline(output, gold["outlines"][document])
    table = (
        score_tables(output, gold["tables"][document])
        if document in gold["tables"]
        else None
    )
    coverage = score_coverage(output, gold["raw_text"][document])
    images = score_images(output, output_path, gold["visuals"][document], gold_root)
    applicable = [
        notes["normalized_recall"] if notes else None,
        outline["recall"],
        table["f1"] if table else None,
        min(coverage["ratio"], 1.0),
        images["recall"] if images["total"] else None,
    ]
    values = [value for value in applicable if value is not None]
    result["metrics"] = {
        "speaker_notes": notes,
        "outline": outline,
        "table_cells": table,
        "coverage": coverage,
        "image_accounting": images,
        "computed_mean": round(sum(values) / len(values), 6) if values else None,
    }
    return result


def score_notes(output: str, notes: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_output = normalize_match(output)
    exact_hits = [note["id"] for note in notes if note["text"] in output]
    normalized_hits = [
        note["id"] for note in notes if normalize_match(note["text"]) in normalized_output
    ]
    total = len(notes)
    return {
        "total": total,
        "exact_hits": exact_hits,
        "normalized_hits": normalized_hits,
        "exact_recall": ratio(len(exact_hits), total),
        "normalized_recall": ratio(len(normalized_hits), total),
    }


def score_outline(output: str, outline: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = extract_outline_candidates(output)
    normalized_candidates = [normalize_outline(value) for value in candidates]
    matches = []
    misses = []
    for item in outline:
        target = normalize_outline(item["text"])
        if any(outline_match(target, candidate) for candidate in normalized_candidates):
            matches.append(item["text"])
        else:
            misses.append(item["text"])
    return {
        "total": len(outline),
        "matched": len(matches),
        "recall": ratio(len(matches), len(outline)),
        "matches": matches,
        "misses": misses,
        "candidate_count": len(candidates),
    }


def extract_outline_candidates(output: str) -> list[str]:
    candidates = []
    for line in output.splitlines():
        stripped = line.strip()
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*$", stripped)
        if match:
            candidates.append(match.group(1))
        elif re.match(r"^Table\s+\d+(?:[-.]\d+)+\b", stripped, flags=re.I):
            candidates.append(stripped)
    candidates.extend(
        html.unescape(re.sub(r"<[^>]+>", " ", match))
        for match in re.findall(r"<h[1-6][^>]*>.*?</h[1-6]>", output, flags=re.I | re.S)
    )
    return candidates


def outline_match(target: str, candidate: str) -> bool:
    if not target or not candidate:
        return False
    if target == candidate:
        return True
    target_tokens = set(target.split())
    candidate_tokens = set(candidate.split())
    if len(target_tokens) < 3 or len(candidate_tokens) < 3:
        return False
    overlap = len(target_tokens & candidate_tokens) / len(target_tokens | candidate_tokens)
    return overlap >= 0.8


def score_tables(output: str, tables: list[dict[str, Any]]) -> dict[str, Any]:
    gold_cells = []
    for table in tables:
        gold_cells.extend(table["header"])
        for row in table["rows"]:
            gold_cells.extend(row)
    output_cells = extract_table_cells(output)
    gold_counter = Counter(normalize_cell(cell) for cell in gold_cells)
    output_counter = Counter(normalize_cell(cell) for cell in output_cells)
    gold_counter.pop("", None)
    output_counter.pop("", None)
    true_positive = sum((gold_counter & output_counter).values())
    precision = ratio(true_positive, sum(output_counter.values()))
    recall = ratio(true_positive, sum(gold_counter.values()))
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "gold_cells": sum(gold_counter.values()),
        "output_cells": sum(output_counter.values()),
        "true_positive_cells": true_positive,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def extract_table_cells(output: str) -> list[str]:
    parser = CellParser()
    parser.feed(output)
    cells = list(parser.cells)
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        pieces = [piece.strip() for piece in split_markdown_row(stripped[1:-1])]
        if pieces and all(re.fullmatch(r":?-{3,}:?", piece) for piece in pieces):
            continue
        cells.extend(pieces)
    return cells


def split_markdown_row(row: str) -> list[str]:
    return re.split(r"(?<!\\)\|", row)


def score_coverage(output: str, raw_text: str) -> dict[str, Any]:
    output_text = normalize_match(strip_markup(output))
    reference_text = normalize_match(raw_text)
    ratio_value = ratio(len(output_text), len(reference_text))
    return {
        "output_normalized_characters": len(output_text),
        "reference_normalized_characters": len(reference_text),
        "ratio": round(ratio_value, 6),
        "alarm_below_0_5": ratio_value < 0.5,
    }


def score_images(
    output: str,
    output_path: Path,
    units: list[dict[str, Any]],
    gold_root: Path,
) -> dict[str, Any]:
    del gold_root
    normalized_output = normalize_match(output)
    references = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", output)
    resolved_references = 0
    for reference in references:
        if reference.startswith("data:"):
            resolved_references += 1
            continue
        path = Path(reference)
        if (path if path.is_absolute() else output_path.parent / path).is_file():
            resolved_references += 1
    asset_covers_all = bool(units) and resolved_references >= len(units)
    details = []
    for unit in units:
        term_hits = [
            term
            for term in unit["description_terms"]
            if normalize_match(term) in normalized_output
        ]
        accounted = bool(term_hits) or asset_covers_all
        details.append(
            {
                "id": unit["id"],
                "locator": unit["locator"],
                "accounted": accounted,
                "term_hits": term_hits,
                "asset_fallback": asset_covers_all and not term_hits,
            }
        )
    accounted_count = sum(1 for item in details if item["accounted"])
    return {
        "total": len(units),
        "accounted": accounted_count,
        "missed": len(units) - accounted_count,
        "recall": ratio(accounted_count, len(units)) if units else None,
        "resolved_image_references": resolved_references,
        "details": details,
    }


def metric_definitions() -> dict[str, str]:
    return {
        "speaker_notes": "Exact and normalized substring recall over six OOXML note payloads.",
        "outline": (
            "Recall of source outline entries against Markdown/HTML headings and table titles."
        ),
        "table_cells": "Multiset cell precision/recall/F1 including repeated source table headers.",
        "coverage": (
            "Normalized visible-output character count divided by source raw-text count; "
            "alarm <0.5."
        ),
        "image_accounting": (
            "Each substantive visual is accounted by a source-specific semantic term or, when "
            "enough valid image references exist, a one-to-one asset fallback."
        ),
    }


def write_csv(path: Path, metrics: list[dict[str, Any]]) -> None:
    fields = [
        "cell_id",
        "run",
        "converter",
        "document",
        "status",
        "output_bytes",
        "notes_exact_recall",
        "notes_normalized_recall",
        "outline_recall",
        "table_cell_f1",
        "coverage_ratio",
        "coverage_alarm",
        "image_recall",
        "computed_mean",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cell in metrics:
            item = cell.get("metrics") or {}
            notes = item.get("speaker_notes") or {}
            outline = item.get("outline") or {}
            table = item.get("table_cells") or {}
            coverage = item.get("coverage") or {}
            images = item.get("image_accounting") or {}
            writer.writerow(
                {
                    "cell_id": cell["cell_id"],
                    "run": cell["run"],
                    "converter": cell["converter"],
                    "document": cell["document"],
                    "status": cell["status"],
                    "output_bytes": cell.get("output_bytes"),
                    "notes_exact_recall": notes.get("exact_recall"),
                    "notes_normalized_recall": notes.get("normalized_recall"),
                    "outline_recall": outline.get("recall"),
                    "table_cell_f1": table.get("f1"),
                    "coverage_ratio": coverage.get("ratio"),
                    "coverage_alarm": coverage.get("alarm_below_0_5"),
                    "image_recall": images.get("recall"),
                    "computed_mean": item.get("computed_mean"),
                }
            )


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Computed Metrics",
        "",
        f"> Status: {payload['status']}; gold status: `{payload['gold_status']}`.",
        "",
        (
            "| Converter | Document | Notes N | Outline | Table F1 | Coverage | Alarm | "
            "Images | Mean |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: |",
    ]
    for cell in payload["cells"]:
        if cell["status"] != "succeeded":
            lines.append(
                f"| {cell['converter']} | {cell['document']} | N/A | N/A | N/A | N/A | "
                "N/A | N/A | N/A |"
            )
            continue
        metrics = cell["metrics"]
        notes = metrics["speaker_notes"]
        table = metrics["table_cells"]
        images = metrics["image_accounting"]
        lines.append(
            "| "
            + " | ".join(
                [
                    cell["converter"],
                    cell["document"],
                    format_metric(notes["normalized_recall"] if notes else None),
                    format_metric(metrics["outline"]["recall"]),
                    format_metric(table["f1"] if table else None),
                    format_metric(metrics["coverage"]["ratio"]),
                    "yes" if metrics["coverage"]["alarm_below_0_5"] else "no",
                    format_metric(images["recall"] if images["total"] else None),
                    format_metric(metrics["computed_mean"]),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def normalize_outline(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = re.sub(r"^\s*(?:slide|page)\s+\d+\s*[:.-]?\s*", "", value, flags=re.I)
    value = re.sub(r"^\s*\d+(?:\.\d+)*\s*[:.-]?\s*", "", value)
    return normalize_match(value)


def normalize_cell(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = re.sub(r"[*_`]", "", value)
    return normalize_match(value)


def normalize_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def strip_markup(value: str) -> str:
    value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"[#*_`>|~-]+", " ", value)


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


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
