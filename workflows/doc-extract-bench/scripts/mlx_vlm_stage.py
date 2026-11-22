from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from mlx_vlm import load
from mlx_vlm.generate import generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import (
    StoppingCriteria,
    get_model_path,
    load_config,
    load_image_processor,
    load_model,
    load_tokenizer,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one pinned MLX VLM over image requests")
    parser.add_argument("--model", required=True)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    items = request.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit("request must contain a non-empty items list")

    started = time.perf_counter()
    model, processor = load_model_and_processor(args.model)
    config = load_config(args.model)
    load_seconds = time.perf_counter() - started
    results = []

    for index, item in enumerate(items, start=1):
        image_path = Path(required_text(item, "image")).resolve()
        if not image_path.is_file():
            raise SystemExit(f"request image does not exist: {image_path}")
        prompt = required_text(item, "prompt")
        max_tokens = int(item.get("max_tokens", 4096))
        repetition_penalty = float(item.get("repetition_penalty", 1.0))
        formatted_prompt = apply_chat_template(
            processor,
            config,
            prompt,
            num_images=1,
        )
        item_started = time.perf_counter()
        generation = generate(
            model,
            processor,
            formatted_prompt,
            image=[str(image_path)],
            max_tokens=max_tokens,
            temperature=0.0,
            repetition_penalty=repetition_penalty,
            verbose=False,
        )
        text = generation.text.strip()
        empty_result = not text
        if empty_result:
            text = "[Model returned no content for this page.]"
        raw_name = f"{index:03d}-{safe_name(str(item.get('id', index)))}.txt"
        raw_path = args.output.parent / "raw" / raw_name
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(text + "\n", encoding="utf-8")
        result = {
            "id": item.get("id", str(index)),
            "image": str(image_path),
            "prompt": prompt,
            "max_tokens": max_tokens,
            "repetition_penalty": repetition_penalty,
            "text": text,
            "markdown": to_markdown(text, str(request.get("response_format", "markdown"))),
            "raw_path": str(raw_path),
            "elapsed_seconds": round(time.perf_counter() - item_started, 3),
            "generation": serializable_generation(generation),
            "empty_result": empty_result,
        }
        results.append(result)
        print(
            json.dumps(
                {
                    "progress": f"{index}/{len(items)}",
                    "id": result["id"],
                    "elapsed_seconds": result["elapsed_seconds"],
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )

    payload = {
        "model": args.model,
        "load_seconds": round(load_seconds, 3),
        "response_format": request.get("response_format", "markdown"),
        "results": results,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_model_and_processor(model_id: str) -> tuple[Any, Any]:
    if "DeepSeek-OCR-2" not in model_id:
        return load(model_id)

    from mlx_vlm.models.deepseekocr_2.processing_deepseekocr import DeepseekOCR2Processor

    model_path = get_model_path(model_id)
    model = load_model(model_path)
    processor = DeepseekOCR2Processor.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    tokenizer = processor.tokenizer
    detokenizer_class = load_tokenizer(model_path, return_tokenizer=False)
    processor.detokenizer = detokenizer_class(tokenizer)
    tokenizer.stopping_criteria = StoppingCriteria(model.config.eos_token_id, tokenizer)
    image_processor = load_image_processor(model_path, local_files_only=True)
    if image_processor is not None:
        processor.image_processor = image_processor
    return model, processor


def to_markdown(text: str, response_format: str) -> str:
    if response_format == "dots_json":
        return dots_json_to_markdown(text)
    if response_format == "deepseek_grounded_markdown":
        return deepseek_to_markdown(text)
    return text.strip()


def deepseek_to_markdown(text: str) -> str:
    cleaned = re.sub(r"<\|(?:grounding|ref|det)\|>", "", text)
    cleaned = re.sub(
        r"(?m)^(?:figure_title|table|sub_title|text|title|image|caption)"
        r"<\|/ref\|><\|/det\|>\s*\n?",
        "",
        cleaned,
    )
    cleaned = cleaned.replace("<|/ref|><|/det|>", "")
    cleaned = re.sub(r"\[\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\]", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def dots_json_to_markdown(text: str) -> str:
    payload = parse_json_fragment(text)
    elements: list[Any]
    if isinstance(payload, list):
        elements = payload
    elif isinstance(payload, dict):
        candidate = payload.get("layout") or payload.get("elements") or payload.get("result")
        elements = candidate if isinstance(candidate, list) else [payload]
    else:
        return text.strip()

    lines = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        category = str(element.get("category") or element.get("label") or "Text")
        content = str(element.get("text") or element.get("content") or "").strip()
        if category.casefold() == "picture" and not content:
            lines.append("> [Picture region present; dots.ocr emits no description.]\n")
        elif not content:
            continue
        elif category.casefold() == "title":
            lines.append(f"# {content}\n")
        elif category.casefold() == "section-header":
            lines.append(f"## {content}\n")
        elif category.casefold() == "list-item":
            lines.append(f"- {content}\n")
        else:
            lines.append(content + "\n")
    return "\n".join(lines).strip() or text.strip()


def parse_json_fragment(text: str) -> Any:
    candidates = [text.strip()]
    for opening, closing in (("[", "]"), ("{", "}")):
        start = text.find(opening)
        end = text.rfind(closing)
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def serializable_generation(generation: Any) -> dict[str, Any]:
    fields = (
        "prompt_tokens",
        "generation_tokens",
        "total_tokens",
        "prompt_tps",
        "generation_tps",
        "peak_memory",
        "cached_tokens",
        "finish_reason",
    )
    return {field: getattr(generation, field, None) for field in fields}


def required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing non-empty request string: {key}")
    return value


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "item"


if __name__ == "__main__":
    main()
