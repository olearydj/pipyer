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
MARKITDOWN_VERSION = "0.1.6"
MARKITDOWN_SPEC = f"markitdown[pdf,docx,pptx]=={MARKITDOWN_VERSION}"
DOCLING_VERSION = "2.114.0"
DOCLING_SPEC = f"docling[vlm]=={DOCLING_VERSION}"
PYTHON_VERSION = "3.12"

EXTRACTION_PROMPT = """Convert the document at {source_path} into faithful, standalone Markdown
for downstream agent use.

Read the entire document, including its rendered visual content. Output only the Markdown
conversion, with no preface, commentary, or code fence.

Use local shell tools when needed to unpack or render binary documents. Keep any temporary
working files under /private/tmp, do not modify the source document or workflow tree, and do
not use the network to obtain document content.

Requirements:
- Preserve all substantive text without summarizing or silently omitting material.
- Preserve reading order, heading hierarchy, lists, links, captions, and tables. Use Markdown
  tables where they remain readable; otherwise use a faithful structured representation.
- For every substantive image, screenshot, chart, diagram, or visual layout, insert a concise
  description at the relevant point in the document. Explain what it shows and why it matters
  in context; do not merely label it as an image.
- For slide decks, preserve slide boundaries and include speaker notes under the corresponding
  slide using a clearly labeled "Speaker notes" block.
- Preserve page or slide numbers when they help navigation, but omit repetitive decorative
  headers and footers.
- Do not invent unreadable text. Mark genuinely unclear content explicitly.
"""


class ConversionError(RuntimeError):
    def __init__(self, message: str, *, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("convert_stage.py reads converter/document from JSON stdin; no arguments")

    inputs = json.loads(sys.stdin.read() or "{}")
    converter = required_text(inputs, "converter")
    document = required_text(inputs, "document")
    fixture_root = resolve_path(inputs.get("fixture_root", "fixtures"))
    source_path = (fixture_root / document).resolve()
    if source_path.parent != fixture_root.resolve() or not source_path.is_file():
        raise SystemExit(f"fixture is missing or escapes fixture_root: {document}")

    output_root = resolve_path(inputs["output_root"])
    tool_cache_root = resolve_path(inputs["tool_cache_root"])
    cell_dir = output_root / converter / source_path.name
    if cell_dir.exists():
        raise SystemExit(f"refusing to overwrite existing cell output: {cell_dir}")
    cell_dir.mkdir(parents=True)
    tool_cache_root.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    try:
        if converter == "markitdown":
            result = run_markitdown(source_path, cell_dir, tool_cache_root)
        elif converter in {"claude_opus_5", "claude_sonnet_5"}:
            result = run_claude(converter, source_path, cell_dir, inputs)
        elif converter in {"codex_sol", "codex_terra"}:
            result = run_codex(converter, source_path, cell_dir, inputs)
        elif converter == "docling":
            result = run_docling(source_path, cell_dir, tool_cache_root)
        else:
            raise ConversionError(f"unknown converter: {converter}", returncode=2)
    except ConversionError as exc:
        record = base_record(converter, source_path, cell_dir, time.perf_counter() - started)
        record.update({"status": "failed", "exit_status": exc.returncode, "error": str(exc)})
        emit(record)
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.returncode) from exc

    output_path = cell_dir / "output.md"
    if not output_path.is_file():
        raise SystemExit(f"converter reported success without {output_path}")
    normalize_markdown(output_path)

    record = base_record(converter, source_path, cell_dir, time.perf_counter() - started)
    record.update(result)
    record.update(
        {
            "status": "succeeded",
            "exit_status": 0,
            "output_path": str(output_path),
            "output_bytes": output_path.stat().st_size,
            "output_sha256": sha256_file(output_path),
            "asset_count": count_assets(cell_dir),
        }
    )
    emit(record)


def run_markitdown(source_path: Path, cell_dir: Path, tool_cache_root: Path) -> dict[str, Any]:
    output_path = cell_dir / "output.md"
    cmd = uvx_command(tool_cache_root, MARKITDOWN_SPEC, "markitdown") + [
        str(source_path),
        "-o",
        str(output_path),
    ]
    proc = run(cmd, cwd=WORKFLOW_DIR)
    write_text(cell_dir / "stderr.log", proc.stderr)
    require_success(proc, "MarkItDown")
    return {
        "tool": "markitdown",
        "tool_version": MARKITDOWN_VERSION,
        "invocation": command_record(cmd),
        "cost_usd": 0.0,
        "usage": None,
    }


def run_claude(
    converter: str,
    source_path: Path,
    cell_dir: Path,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    output_path = cell_dir / "output.md"
    response_path = cell_dir / "claude-response.json"
    model_key = {
        "claude_opus_5": "claude_opus_model",
        "claude_sonnet_5": "claude_sonnet_model",
    }[converter]
    model = required_text(inputs, model_key)
    max_budget = float(inputs.get("claude_max_budget_usd", 5.0))
    prompt = EXTRACTION_PROMPT.format(source_path=source_path)
    cmd = [
        "claude",
        "--safe-mode",
        "-p",
        prompt,
        "--model",
        model,
        "--effort",
        "low",
        "--tools",
        "Read,Bash",
        "--allowed-tools",
        "Read,Bash",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-budget-usd",
        str(max_budget),
    ]
    proc = run(cmd, cwd=WORKFLOW_DIR)
    write_text(cell_dir / "stderr.log", proc.stderr)
    require_success(proc, "Claude Code")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ConversionError(f"Claude Code returned invalid JSON: {exc}") from exc
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = payload.get("result")
    if not isinstance(result, str) or not result.strip():
        raise ConversionError("Claude Code JSON did not contain a non-empty result")
    write_text(output_path, result)

    model_usage = payload.get("modelUsage")
    resolved_models = sorted(model_usage) if isinstance(model_usage, dict) else []
    return {
        "tool": "claude-code",
        "tool_version": observed_version(["claude", "--version"]),
        "requested_model": model,
        "resolved_models": resolved_models,
        "invocation": {
            "command": ["claude", "--safe-mode", "-p", "<prompt>", "--model", model],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        },
        "cost_usd": number_or_none(payload.get("total_cost_usd")),
        "usage": payload.get("usage"),
        "model_usage": model_usage,
        "response_path": str(response_path),
    }


def run_codex(
    converter: str,
    source_path: Path,
    cell_dir: Path,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    output_path = cell_dir / "output.md"
    events_path = cell_dir / "codex-events.jsonl"
    model_key = {
        "codex_sol": "codex_sol_model",
        "codex_terra": "codex_terra_model",
    }[converter]
    model = required_text(inputs, model_key)
    effort = required_text(inputs, "codex_reasoning_effort")
    prompt = EXTRACTION_PROMPT.format(source_path=source_path)
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(WORKFLOW_DIR),
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{effort}"',
        "--json",
        "--output-last-message",
        str(output_path),
        prompt,
    ]
    proc = run(cmd, cwd=WORKFLOW_DIR)
    write_text(cell_dir / "stderr.log", proc.stderr)
    write_text(events_path, proc.stdout)
    require_success(proc, "Codex CLI")
    if not output_path.is_file() or not output_path.read_text(encoding="utf-8").strip():
        raise ConversionError("Codex CLI did not write a non-empty final message")

    usage = None
    thread_id = None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        elif event.get("type") == "turn.completed":
            usage = event.get("usage")

    return {
        "tool": "codex-cli",
        "tool_version": observed_version(["codex", "--version"]),
        "requested_model": model,
        "reasoning_effort": effort,
        "thread_id": thread_id,
        "invocation": {
            "command": [
                "codex",
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--model",
                model,
                "--json",
                "--output-last-message",
                "<output.md>",
                "<prompt>",
            ],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        },
        "cost_usd": None,
        "cost_basis": "Codex CLI JSONL reports tokens but no dollar-cost field",
        "usage": usage,
        "events_path": str(events_path),
    }


def run_docling(source_path: Path, cell_dir: Path, tool_cache_root: Path) -> dict[str, Any]:
    raw_dir = cell_dir / "docling"
    raw_dir.mkdir()
    cmd = uvx_command(tool_cache_root, DOCLING_SPEC, "docling") + [
        "convert",
        str(source_path),
        "--to",
        "md",
        "--image-export-mode",
        "referenced",
        "--device",
        "mps",
        "--document-timeout",
        "3300",
        "--output",
        str(raw_dir),
    ]
    if source_path.suffix.lower() == ".pdf":
        cmd.extend(["--pipeline", "vlm", "--vlm-model", "granite_docling"])
        pipeline = "vlm/granite_docling/auto-inline->mlx"
    else:
        cmd.extend(["--pipeline", "standard", "--enrich-picture-description"])
        pipeline = "office-standard/smolvlm-picture-description/auto-inline->mlx"

    env = {
        "HF_HOME": str(tool_cache_root / "huggingface"),
        "TORCH_HOME": str(tool_cache_root / "torch"),
    }
    proc = run(cmd, cwd=WORKFLOW_DIR, env_overlay=env)
    write_text(cell_dir / "stderr.log", proc.stderr)
    write_text(cell_dir / "stdout.log", proc.stdout)
    require_success(proc, "Docling")
    markdown_candidates = sorted(raw_dir.glob("*.md"))
    if len(markdown_candidates) != 1:
        raise ConversionError(
            f"Docling produced {len(markdown_candidates)} top-level Markdown files; expected one"
        )
    shutil.copy2(markdown_candidates[0], cell_dir / "output.md")
    return {
        "tool": "docling",
        "tool_version": DOCLING_VERSION,
        "pipeline": pipeline,
        "invocation": command_record(cmd),
        "cost_usd": 0.0,
        "usage": None,
    }


def uvx_command(tool_cache_root: Path, package: str, command: str) -> list[str]:
    return [
        "uvx",
        "--no-config",
        "--cache-dir",
        str(tool_cache_root / "uv"),
        "--python",
        PYTHON_VERSION,
        "--from",
        package,
        command,
    ]


def run(
    cmd: list[str],
    *,
    cwd: Path,
    env_overlay: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overlay:
        env.update(env_overlay)
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def require_success(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode == 0:
        return
    detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostic output"
    raise ConversionError(
        f"{label} failed ({proc.returncode}): {detail[-2000:]}",
        returncode=proc.returncode,
    )


def observed_version(cmd: list[str]) -> str | None:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return (proc.stdout or proc.stderr).strip() or None


def command_record(cmd: list[str]) -> dict[str, Any]:
    return {"command": cmd}


def base_record(
    converter: str,
    source_path: Path,
    cell_dir: Path,
    elapsed_seconds: float,
) -> dict[str, Any]:
    return {
        "converter": converter,
        "document": source_path.name,
        "source_path": str(source_path),
        "source_bytes": source_path.stat().st_size,
        "source_sha256": sha256_file(source_path),
        "cell_dir": str(cell_dir),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def required_text(inputs: dict[str, Any], key: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing non-empty string input: {key}")
    return value


def resolve_path(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (WORKFLOW_DIR / path).resolve()


def normalize_markdown(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    path.write_text(text + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n" if text else "", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_assets(cell_dir: Path) -> int:
    excluded = {
        "output.md",
        "stderr.log",
        "stdout.log",
        "claude-response.json",
        "codex-events.jsonl",
    }
    return sum(1 for path in cell_dir.rglob("*") if path.is_file() and path.name not in excluded)


def number_or_none(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def emit(record: dict[str, Any]) -> None:
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
