from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = ROOT / "fixtures" / "gold"
TARGETS = {
    "meeting-notes.docx": [
        "markitdown",
        "claude_opus_5",
        "codex_sol",
        "codex_terra",
        "docling",
        "docling_qwen3b_hybrid",
        "qwen7b_hybrid",
    ],
    "software-doc.pdf": [
        "markitdown",
        "claude_opus_5",
        "codex_sol",
        "codex_terra",
        "docling",
        "docling_qwen3b_hybrid",
        "deepseek_ocr2_mlx",
        "dots_ocr_mlx",
        "qwen7b_hybrid",
    ],
    "marketing-deck.pptx": [
        "markitdown",
        "claude_opus_5",
        "codex_sol",
        "codex_terra",
        "docling",
        "docling_qwen3b_hybrid",
        "qwen7b_hybrid",
    ],
}
REFERENCE = "claude_sonnet_5"
PAIR_SEED = "doc-extract-round2-pair-order-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build blinded visual-description pairs")
    parser.add_argument("--cell-registry", type=Path, required=True)
    parser.add_argument("--gold-root", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"refusing to overwrite pair directory: {output_dir}")
    output_dir.mkdir(parents=True)
    gold_root = args.gold_root.resolve()
    registry = read_json(args.cell_registry.resolve())["cells"]
    paths = {
        (cell["converter"], cell["document"]): Path(cell["output_path"])
        for cell in registry
        if cell["status"] == "succeeded"
    }
    visual_units = read_json(gold_root / "visual-units.json")["documents"]
    outlines = read_json(gold_root / "outlines.json")["documents"]
    key = []
    public_manifest = []
    pair_number = 0

    for document, challengers in TARGETS.items():
        reference_path = require_cell(paths, REFERENCE, document)
        for challenger in challengers:
            challenger_path = require_cell(paths, challenger, document)
            pair_number += 1
            pair_id = f"pair-{pair_number:03d}"
            pair_dir = output_dir / pair_id
            pair_dir.mkdir()
            reference_text = extract_residue(
                reference_path.read_text(encoding="utf-8", errors="replace"),
                document,
                visual_units[document],
                outlines[document],
            )
            challenger_text = extract_residue(
                challenger_path.read_text(encoding="utf-8", errors="replace"),
                document,
                visual_units[document],
                outlines[document],
            )
            swap = stable_bit(f"{PAIR_SEED}:{pair_id}:{document}:{challenger}")
            ordered = (
                [(challenger, challenger_text), (REFERENCE, reference_text)]
                if swap
                else [(REFERENCE, reference_text), (challenger, challenger_text)]
            )
            (pair_dir / "candidate-a.md").write_text(ordered[0][1], encoding="utf-8")
            (pair_dir / "candidate-b.md").write_text(ordered[1][1], encoding="utf-8")
            references_dir = pair_dir / "references"
            references_dir.mkdir()
            reference_names = []
            for unit in visual_units[document]:
                source = gold_root / unit["visual_reference"]
                name = source.name
                shutil.copy2(source, references_dir / name)
                reference_names.append(f"references/{name}")
            write_json(
                pair_dir / "PAIR.json",
                {
                    "pair_id": pair_id,
                    "document": document,
                    "candidate_labels": ["A", "B"],
                    "reference_visuals": reference_names,
                    "instruction": "Forced choice on contextual visual-description fidelity only.",
                },
            )
            public_manifest.append(
                {
                    "pair_id": pair_id,
                    "document": document,
                    "pair_dir": str(pair_dir),
                    "reference_visuals": reference_names,
                }
            )
            key.append(
                {
                    "pair_id": pair_id,
                    "document": document,
                    "a_converter": ordered[0][0],
                    "b_converter": ordered[1][0],
                    "reference_converter": REFERENCE,
                    "challenger": challenger,
                    "source_paths": {
                        REFERENCE: str(reference_path),
                        challenger: str(challenger_path),
                    },
                }
            )

    write_json(output_dir / "pairs-manifest.json", {"pairs": public_manifest})
    write_json(output_dir / "pair-key.json", {"seed": PAIR_SEED, "pairs": key})
    print(output_dir)


def extract_residue(
    text: str,
    document: str,
    units: list[dict[str, Any]],
    outline: list[dict[str, Any]],
) -> str:
    if document == "meeting-notes.docx":
        windows = unit_windows(text, units, radius=2400)
    elif document == "software-doc.pdf":
        windows = unit_windows(text, units, radius=4200)
    else:
        title_by_slide = {item.get("slide"): item["text"] for item in outline}
        enriched_units = []
        for unit in units:
            slide_match = re.search(r"(\d+)", unit["locator"])
            slide = int(slide_match.group(1)) if slide_match else None
            enriched_units.append(
                unit
                | {
                    "description_terms": unit["description_terms"]
                    + ([title_by_slide[slide]] if slide in title_by_slide else [])
                }
            )
        windows = unit_windows(text, enriched_units, radius=1800)
    header = (
        "# Anonymized visual-description residue\n\n"
        "Only passages near the source visual units are included. "
        "Missing passages are explicit.\n\n"
    )
    return anonymize_residue(header + "\n\n".join(windows).rstrip() + "\n")


def anonymize_residue(text: str) -> str:
    text = re.sub(
        r"(!\[[^\]]*\])\([^)\n]+\)",
        r"\1(anonymized-source-asset)",
        text,
    )
    return re.sub(
        r"local\s+vlm\s+visual\s+descriptions",
        "Visual descriptions",
        text,
        flags=re.IGNORECASE,
    )


def unit_windows(text: str, units: list[dict[str, Any]], *, radius: int) -> list[str]:
    normalized_text = text.casefold()
    outputs = []
    for unit in units:
        locator_index = normalized_text.rfind(unit["locator"].casefold())
        needles = unit["description_terms"]
        locations = []
        for needle in needles:
            normalized_needle = needle.casefold()
            start = 0
            while len(locations) < 6:
                index = normalized_text.find(normalized_needle, start)
                if index < 0:
                    break
                locations.append(index)
                start = index + max(1, len(normalized_needle))
        if locator_index >= 0:
            location = locator_index
        elif locations:
            location = min(locations)
        else:
            location = None
        if location is None:
            excerpt = "[No relevant visual-description passage found.]"
        else:
            start = max(0, location - radius)
            end = min(len(text), location + radius)
            excerpt = text[start:end].strip()
        outputs.append(f"## {unit['locator']}\n\n{excerpt}")
    return outputs


def require_cell(paths: dict[tuple[str, str], Path], converter: str, document: str) -> Path:
    try:
        return paths[(converter, document)]
    except KeyError as exc:
        raise SystemExit(f"missing succeeded cell for pair build: {converter}/{document}") from exc


def stable_bit(value: str) -> bool:
    return bool(hashlib.sha256(value.encode("utf-8")).digest()[0] & 1)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
