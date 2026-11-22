from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

ANCHORS = (
    ("meeting-notes.docx", "docling"),
    ("meeting-notes.docx", "qwen7b_hybrid"),
    ("software-doc.pdf", "deepseek_ocr2_mlx"),
    ("software-doc.pdf", "qwen7b_hybrid"),
    ("marketing-deck.pptx", "docling_qwen3b_hybrid"),
    ("marketing-deck.pptx", "qwen7b_hybrid"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the required six-pair human anchor")
    parser.add_argument("--pair-root", type=Path, required=True)
    parser.add_argument("--pair-key", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pair_root = args.pair_root.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"refusing to overwrite human-anchor directory: {output_dir}")
    output_dir.mkdir(parents=True)
    key = read_json(args.pair_key.resolve())["pairs"]
    by_target = {(item["document"], item["challenger"]): item for item in key}
    selected = [by_target[target] for target in ANCHORS]

    lines = [
        "# Human Anchor: Six Blinded Comparisons",
        "",
        "Score the same axis as the model panel: which candidate describes the source visuals "
        "more faithfully in context? Ignore general text coverage, OCR quantity, and prose style. "
        "Choose A or B for every comparison; there are no ties.",
        "",
    ]
    public = []
    private_key = []
    for index, item in enumerate(selected, start=1):
        pair_dir = pair_root / item["pair_id"]
        manifest = read_json(pair_dir / "PAIR.json")
        lines.extend(
            [
                f"## Anchor {index}: {item['document']}",
                "",
                f"Panel pair ID: `{item['pair_id']}`.",
                "",
                "### Source visuals",
                "",
            ]
        )
        for visual in manifest["reference_visuals"]:
            absolute = pair_dir / visual
            relative = os.path.relpath(absolute, output_dir)
            lines.extend([f"![Source visual for anchor {index}]({relative})", ""])
        for label, filename in (("A", "candidate-a.md"), ("B", "candidate-b.md")):
            candidate = (pair_dir / filename).read_text(encoding="utf-8")
            candidate = re.sub(
                r"!\[[^\]]*\]\(anonymized-source-asset\)",
                "[Anonymized source-asset reference; not a description.]",
                candidate,
            )
            lines.extend(
                [
                    f"<details><summary>Candidate {label}</summary>",
                    "",
                    candidate.rstrip(),
                    "",
                    "</details>",
                    "",
                ]
            )
        lines.extend([f"**Your choice for Anchor {index}: A / B**", "", "---", ""])
        public.append(
            {
                "anchor": index,
                "pair_id": item["pair_id"],
                "document": item["document"],
                "winner": None,
            }
        )
        private_key.append(
            {
                "anchor": index,
                "pair_id": item["pair_id"],
                "document": item["document"],
                "a_converter": item["a_converter"],
                "b_converter": item["b_converter"],
                "challenger": item["challenger"],
            }
        )
    lines.extend(
        [
            "## Response form",
            "",
            "Reply with six choices, for example: `1:A, 2:B, 3:A, 4:A, 5:B, 6:B`.",
            "",
        ]
    )
    (output_dir / "human-anchor.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(output_dir / "human-anchor-response.json", {"anchors": public})
    write_json(output_dir / "human-anchor-key.json", {"anchors": private_key})
    print(output_dir)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
