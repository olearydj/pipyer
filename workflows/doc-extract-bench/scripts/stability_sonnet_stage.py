from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from convert_stage import EXTRACTION_PROMPT

WORKFLOW_DIR = Path.cwd()


def main() -> None:
    inputs = json.loads(sys.stdin.read() or "{}")
    repeat = int(inputs["repeat"])
    if repeat not in {1, 2, 3}:
        raise SystemExit("repeat must be 1, 2, or 3")
    document = str(inputs.get("document", "marketing-deck.pptx"))
    fixture_root = resolve_path(inputs.get("fixture_root", "fixtures"))
    source_path = (fixture_root / document).resolve()
    if source_path.parent != fixture_root.resolve() or not source_path.is_file():
        raise SystemExit(f"fixture is missing or escapes fixture_root: {document}")
    output_root = resolve_path(inputs["output_root"])
    converter = f"claude_sonnet_5_stability_{repeat}"
    cell_dir = output_root / converter / source_path.name
    if cell_dir.exists():
        raise SystemExit(f"refusing to overwrite stability cell: {cell_dir}")
    cell_dir.mkdir(parents=True)

    model = required_text(inputs, "claude_sonnet_model")
    max_budget = float(inputs.get("claude_max_budget_usd", 1.5))
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
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=WORKFLOW_DIR, text=True, capture_output=True)
    (cell_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise SystemExit(f"Claude stability cell failed ({proc.returncode}): {detail[-2000:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Claude stability cell returned invalid JSON: {exc}") from exc
    result = payload.get("result")
    if not isinstance(result, str) or not result.strip():
        raise SystemExit("Claude stability response did not contain non-empty result")

    output_path = cell_dir / "output.md"
    output_path.write_text(result.strip() + "\n", encoding="utf-8")
    response_path = cell_dir / "claude-response.json"
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    model_usage = payload.get("modelUsage")
    emit(
        {
            "converter": converter,
            "repeat": repeat,
            "document": source_path.name,
            "source_sha256": sha256_file(source_path),
            "output_path": str(output_path),
            "output_bytes": output_path.stat().st_size,
            "output_sha256": sha256_file(output_path),
            "status": "succeeded",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "tool": "claude-code",
            "tool_version": observed_version(["claude", "--version"]),
            "requested_model": model,
            "resolved_models": sorted(model_usage) if isinstance(model_usage, dict) else [],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "cost_usd": number_or_none(payload.get("total_cost_usd")),
            "usage": payload.get("usage"),
            "model_usage": model_usage,
            "response_path": str(response_path),
        }
    )


def required_text(inputs: dict[str, Any], key: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing non-empty string input: {key}")
    return value


def resolve_path(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (WORKFLOW_DIR / path).resolve()


def observed_version(cmd: list[str]) -> str | None:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return (proc.stdout or proc.stderr).strip() or None


def number_or_none(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
