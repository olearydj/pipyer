from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WORKFLOW_DIR = Path.cwd()
MLX_VLM_VERSION = "0.6.7"
PYTHON_VERSION = "3.12"

MODELS = {
    "docling_qwen3b_hybrid": "mlx-community/Qwen2.5-VL-3B-Instruct-bf16",
    "deepseek_ocr2_mlx": "mlx-community/DeepSeek-OCR-2-bf16",
    "dots_ocr_mlx": "mlx-community/dots.ocr-4bit",
    "qwen7b_hybrid": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
}

DEEPSEEK_PROMPT = "<|grounding|>Convert the document to markdown. "
DOTS_LAYOUT_PROMPT = (
    "Please output the layout information from the PDF image, including each layout "
    "element's bbox, its category, and the corresponding text content within the bbox.\n\n"
    "1. Bbox format: [x1, y1, x2, y2]\n\n"
    "2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', "
    "'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', "
    "'Text', 'Title'].\n\n"
    "3. Text Extraction & Formatting Rules:\n"
    "- Picture: omit the text field.\n"
    "- Formula: format text as LaTeX.\n"
    "- Table: format text as HTML.\n"
    "- All others: format text as Markdown.\n\n"
    "4. Preserve the original text, do not translate, and sort elements in reading order.\n\n"
    "5. Return one JSON value only."
)
DESCRIPTION_PROMPT = (
    "Describe this substantive visual faithfully for insertion at its stated location in a "
    "standalone Markdown conversion. Identify its visual type and explain the labels, layout, "
    "relationships, sequence, and quantitative values that convey meaning. State why the visual "
    "matters in its document context. Do not merely transcribe or call it an image. "
    "Use 150-250 words and avoid repeating labels. Location: {locator}."
)


class ConversionError(RuntimeError):
    pass


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("convert_round2_stage.py reads JSON stdin; no arguments")
    inputs = json.loads(sys.stdin.read() or "{}")
    converter = required_text(inputs, "converter")
    document = required_text(inputs, "document")
    if converter not in MODELS:
        raise SystemExit(f"unknown converter: {converter}")

    fixture_root = resolve_path(inputs.get("fixture_root", "fixtures"))
    source_path = (fixture_root / document).resolve()
    if source_path.parent != fixture_root.resolve() or not source_path.is_file():
        raise SystemExit(f"fixture is missing or escapes fixture_root: {document}")
    output_root = resolve_path(inputs["output_root"])
    tool_cache_root = resolve_path(inputs["tool_cache_root"])
    gold_root = resolve_path(inputs.get("gold_root", "fixtures/gold"))
    round1_docling_root = resolve_path(inputs["round1_docling_root"])
    cell_dir = output_root / converter / source_path.name
    started = time.perf_counter()
    model = MODELS[converter]
    if cell_dir.exists():
        output_path = cell_dir / "output.md"
        if output_path.is_file():
            emit(
                base_record(converter, source_path, cell_dir, started)
                | {
                    "status": "succeeded",
                    "exit_status": 0,
                    "model": model,
                    "model_bytes": model_bytes(tool_cache_root, model),
                    "method": "existing_completed_cell_reuse",
                    "resumed_artifact": True,
                    "output_path": str(output_path),
                    "output_bytes": output_path.stat().st_size,
                    "output_sha256": sha256_file(output_path),
                    "cost_usd": 0.0,
                }
            )
            return
        if converter in {"deepseek_ocr2_mlx", "dots_ocr_mlx"} and source_path.suffix != ".pdf":
            emit(
                base_record(converter, source_path, cell_dir, started)
                | {
                    "status": "not_applicable",
                    "reason": "PDF-only local OCR runtime; Office inputs are intentionally N/A.",
                    "model": model,
                    "model_bytes": model_bytes(tool_cache_root, model),
                    "resumed_artifact": True,
                }
            )
            return
        raise SystemExit(f"refusing to overwrite incomplete cell output: {cell_dir}")
    cell_dir.mkdir(parents=True)
    tool_cache_root.mkdir(parents=True, exist_ok=True)

    if converter in {"deepseek_ocr2_mlx", "dots_ocr_mlx"} and source_path.suffix != ".pdf":
        emit(
            base_record(converter, source_path, cell_dir, started)
            | {
                "status": "not_applicable",
                "reason": "PDF-only local OCR runtime; Office inputs are intentionally N/A.",
                "model": model,
                "model_bytes": model_bytes(tool_cache_root, model),
            }
        )
        return

    try:
        if converter in {"docling_qwen3b_hybrid", "qwen7b_hybrid"}:
            metadata = run_hybrid(
                converter,
                model,
                source_path,
                cell_dir,
                tool_cache_root,
                gold_root,
                round1_docling_root,
            )
        else:
            metadata = run_pdf_ocr(converter, model, source_path, cell_dir, tool_cache_root)
    except ConversionError as exc:
        emit(
            base_record(converter, source_path, cell_dir, started)
            | {"status": "failed", "exit_status": 1, "error": str(exc), "model": model}
        )
        raise SystemExit(1) from exc

    output_path = cell_dir / "output.md"
    normalize_markdown(output_path)
    record = base_record(converter, source_path, cell_dir, started)
    record.update(metadata)
    record.update(
        {
            "status": "succeeded",
            "exit_status": 0,
            "model": model,
            "model_bytes": model_bytes(tool_cache_root, model),
            "output_path": str(output_path),
            "output_bytes": output_path.stat().st_size,
            "output_sha256": sha256_file(output_path),
            "cost_usd": 0.0,
        }
    )
    emit(record)


def run_hybrid(
    converter: str,
    model: str,
    source_path: Path,
    cell_dir: Path,
    tool_cache_root: Path,
    gold_root: Path,
    round1_docling_root: Path,
) -> dict[str, Any]:
    base_path = round1_docling_root / source_path.name / "output.md"
    if not base_path.is_file():
        raise ConversionError(f"missing reused round-1 Docling output: {base_path}")
    visual_units = json.loads((gold_root / "visual-units.json").read_text(encoding="utf-8"))
    units = visual_units["documents"][source_path.name]
    output_path = cell_dir / "output.md"
    shutil.copy2(base_path, output_path)
    if not units:
        return {
            "tool": "round-1-docling-reuse",
            "tool_version": MLX_VLM_VERSION,
            "method": "round1_docling_structure_plus_standalone_mlx_visual_descriptions",
            "base_output_path": str(base_path),
            "visual_units_processed": 0,
            "usage": None,
        }

    request_path = cell_dir / "mlx-request.json"
    response_path = cell_dir / "mlx-response.json"
    items = []
    for unit in units:
        items.append(
            {
                "id": unit["id"],
                "image": str((gold_root / unit["visual_reference"]).resolve()),
                "prompt": DESCRIPTION_PROMPT.format(locator=unit["locator"]),
                "max_tokens": 700,
                "repetition_penalty": 1.05,
            }
        )
    write_json(request_path, {"response_format": "markdown", "items": items})
    proc, cmd = run_mlx(model, request_path, response_path, cell_dir, tool_cache_root)
    require_success(proc, "standalone MLX visual-description pass")
    response = json.loads(response_path.read_text(encoding="utf-8"))

    additions = ["", "## Local VLM visual descriptions", ""]
    by_id = {item["id"]: item for item in response["results"]}
    for unit in units:
        item = by_id[unit["id"]]
        additions.extend(
            [
                f"### {unit['locator']}",
                "",
                item["markdown"].strip(),
                "",
            ]
        )
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(additions).rstrip() + "\n")
    return {
        "tool": "mlx-vlm",
        "tool_version": MLX_VLM_VERSION,
        "method": "round1_docling_structure_plus_standalone_mlx_visual_descriptions",
        "base_output_path": str(base_path),
        "base_output_sha256": sha256_file(base_path),
        "visual_units_processed": len(units),
        "response_path": str(response_path),
        "invocation": command_record(cmd),
        "usage": summarize_usage(response),
    }


def run_pdf_ocr(
    converter: str,
    model: str,
    source_path: Path,
    cell_dir: Path,
    tool_cache_root: Path,
) -> dict[str, Any]:
    pages_dir = cell_dir / "pages"
    pages_dir.mkdir()
    render_cmd = [
        "pdftoppm",
        "-jpeg",
        "-jpegopt",
        "quality=90",
        "-r",
        "180",
        str(source_path),
        str(pages_dir / "page"),
    ]
    render_proc = subprocess.run(render_cmd, text=True, capture_output=True)
    require_success(render_proc, "PDF page rendering")
    page_paths = sorted(pages_dir.glob("page-*.jpg"), key=page_number)
    if not page_paths:
        raise ConversionError("PDF renderer produced no page images")

    if converter == "deepseek_ocr2_mlx":
        prompt = DEEPSEEK_PROMPT
        response_format = "deepseek_grounded_markdown"
        max_tokens = 4096
    else:
        prompt = DOTS_LAYOUT_PROMPT
        response_format = "dots_json"
        max_tokens = 4096
    request_path = cell_dir / "mlx-request.json"
    response_path = cell_dir / "mlx-response.json"
    write_json(
        request_path,
        {
            "response_format": response_format,
            "items": [
                {
                    "id": f"page-{index}",
                    "image": str(path.resolve()),
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                }
                for index, path in enumerate(page_paths, start=1)
            ],
        },
    )
    proc, cmd = run_mlx(model, request_path, response_path, cell_dir, tool_cache_root)
    require_success(proc, f"{converter} MLX conversion")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    sections = []
    for index, item in enumerate(response["results"], start=1):
        sections.extend([f"# Page {index}", "", item["markdown"].strip(), ""])
    (cell_dir / "output.md").write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return {
        "tool": "mlx-vlm",
        "tool_version": MLX_VLM_VERSION,
        "method": "standalone_page_image_ocr",
        "page_render_dpi": 180,
        "pages_processed": len(page_paths),
        "response_path": str(response_path),
        "invocation": command_record(cmd),
        "usage": summarize_usage(response),
    }


def run_mlx(
    model: str,
    request_path: Path,
    response_path: Path,
    cell_dir: Path,
    tool_cache_root: Path,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    cmd = [
        "uvx",
        "--offline",
        "--no-config",
        "--cache-dir",
        str(tool_cache_root / "uv"),
        "--python",
        PYTHON_VERSION,
        "--from",
        f"mlx-vlm=={MLX_VLM_VERSION}",
        "python",
        "scripts/mlx_vlm_stage.py",
        "--model",
        model,
        "--request",
        str(request_path),
        "--output",
        str(response_path),
    ]
    env = os.environ.copy()
    env.update(
        {
            "HF_HOME": str(tool_cache_root / "huggingface-round2"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "UV_TOOL_DIR": str(tool_cache_root / "uv-tools-round2"),
        }
    )
    proc = subprocess.run(cmd, cwd=WORKFLOW_DIR, text=True, capture_output=True, env=env)
    write_text(cell_dir / "mlx-stdout.log", proc.stdout)
    write_text(cell_dir / "mlx-stderr.log", proc.stderr)
    return proc, cmd


def summarize_usage(response: dict[str, Any]) -> dict[str, Any]:
    generations = [item.get("generation", {}) for item in response.get("results", [])]
    return {
        "prompt_tokens": sum(int(item.get("prompt_tokens", 0)) for item in generations),
        "generation_tokens": sum(int(item.get("generation_tokens", 0)) for item in generations),
        "total_tokens": sum(int(item.get("total_tokens", 0)) for item in generations),
        "peak_memory_gb_max": max(
            (float(item.get("peak_memory", 0.0)) for item in generations), default=0.0
        ),
        "load_seconds": response.get("load_seconds"),
        "model_elapsed_seconds": response.get("elapsed_seconds"),
    }


def model_bytes(tool_cache_root: Path, model: str) -> int | None:
    cache_dir = tool_cache_root / "huggingface-round2" / "hub" / (
        "models--" + model.replace("/", "--")
    )
    blobs_dir = cache_dir / "blobs"
    if not blobs_dir.is_dir():
        return None
    return sum(path.stat().st_size for path in blobs_dir.rglob("*") if path.is_file())


def page_number(path: Path) -> int:
    return int(path.stem.rsplit("-", 1)[-1])


def base_record(
    converter: str,
    source_path: Path,
    cell_dir: Path,
    started: float,
) -> dict[str, Any]:
    return {
        "converter": converter,
        "document": source_path.name,
        "source_path": str(source_path),
        "source_bytes": source_path.stat().st_size,
        "source_sha256": sha256_file(source_path),
        "cell_dir": str(cell_dir),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def require_success(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode == 0:
        return
    detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostic output"
    raise ConversionError(f"{label} failed ({proc.returncode}): {detail[-4000:]}")


def required_text(inputs: dict[str, Any], key: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing non-empty string input: {key}")
    return value


def resolve_path(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (WORKFLOW_DIR / path).resolve()


def normalize_markdown(path: Path) -> None:
    if not path.is_file():
        raise ConversionError(f"converter did not produce {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise ConversionError(f"converter produced an empty {path}")
    path.write_text(text + "\n", encoding="utf-8")


def command_record(cmd: list[str]) -> dict[str, Any]:
    redacted = list(cmd)
    try:
        request_index = redacted.index("--request") + 1
        redacted[request_index] = "<request.json>"
        output_index = redacted.index("--output") + 1
        redacted[output_index] = "<response.json>"
    except (ValueError, IndexError):
        pass
    return {"command": redacted}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n" if text else "", encoding="utf-8")


def emit(record: dict[str, Any]) -> None:
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
