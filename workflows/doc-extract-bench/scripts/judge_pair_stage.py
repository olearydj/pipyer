from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WORKFLOW_DIR = Path.cwd()

JUDGE_PROMPT = """You are one member of a governed document-conversion evaluation panel.

Evaluate only contextual visual-description fidelity for this blinded pair. Do not reward general
text coverage, OCR quantity, tables, formatting volume, or writing style except where they make a
visual description more faithful. Open and inspect every source image listed below, then read
{candidate_a} and {candidate_b}. The candidate files contain only deterministic excerpts near the
source visual units; an explicit missing-passage marker means that candidate supplied no relevant
description.

Source images:
{reference_files}

Choose the candidate that more faithfully explains what the visuals show, their labels and
relationships, and why they matter at their document location. This is a forced choice: choose A
or B even when both are weak. Do not infer converter or model identity.

Return only one JSON object with exactly these keys; write no text before or after it, keep the
reason to at most 35 words, and JSON-escape any quoted terms:
{{"winner":"A or B","reason":"one concise evidence-based sentence"}}
"""


def main() -> None:
    inputs = json.loads(sys.stdin.read() or "{}")
    pair_id = required_text(inputs, "pair_id")
    judge = required_text(inputs, "judge")
    if judge not in {"claude", "codex"}:
        raise SystemExit(f"unknown judge family: {judge}")
    pair_root = resolve_path(inputs["pair_root"])
    pair_dir = (pair_root / pair_id).resolve()
    if pair_dir.parent != pair_root.resolve() or not (pair_dir / "PAIR.json").is_file():
        raise SystemExit(f"missing or invalid pair: {pair_id}")
    output_root = resolve_path(inputs["output_root"])
    cell_dir = output_root / judge / pair_id
    if cell_dir.exists():
        decision_path = cell_dir / "decision.json"
        if decision_path.is_file():
            print(json.dumps(json.loads(decision_path.read_text(encoding="utf-8")), sort_keys=True))
            return
        raise SystemExit(f"refusing to overwrite incomplete judge cell: {cell_dir}")
    cell_dir.mkdir(parents=True)
    pair_manifest = json.loads((pair_dir / "PAIR.json").read_text(encoding="utf-8"))
    reference_files = pair_manifest.get("reference_visuals", [])
    if not reference_files:
        raise SystemExit(f"pair has no source-image references: {pair_id}")
    prompt = JUDGE_PROMPT.format(
        reference_files="\n".join(f"- {pair_dir / value}" for value in reference_files),
        candidate_a=pair_dir / "candidate-a.md",
        candidate_b=pair_dir / "candidate-b.md",
    )
    started = time.perf_counter()

    if judge == "claude":
        metadata, decision = run_claude(prompt, cell_dir, inputs)
    else:
        metadata, decision = run_codex(prompt, cell_dir, inputs)
    record = {
        "pair_id": pair_id,
        "judge": judge,
        "winner": decision["winner"],
        "reason": decision["reason"],
        "status": "succeeded",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "pair_manifest_sha256": sha256_file(pair_dir / "PAIR.json"),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        **metadata,
    }
    (cell_dir / "decision.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, sort_keys=True))


def run_claude(
    prompt: str,
    cell_dir: Path,
    inputs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    model = required_text(inputs, "claude_judge_model")
    max_budget = float(inputs.get("claude_judge_max_budget_usd", 0.3))
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
        "Read",
        "--allowed-tools",
        "Read",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-budget-usd",
        str(max_budget),
    ]
    proc = subprocess.run(cmd, cwd=WORKFLOW_DIR, text=True, capture_output=True)
    write_text(cell_dir / "stderr.log", proc.stderr)
    require_success(proc, "Claude judge")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Claude judge returned invalid envelope JSON: {exc}") from exc
    (cell_dir / "claude-response.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = payload.get("result")
    if not isinstance(result, str):
        raise SystemExit("Claude judge envelope has no result string")
    decision = parse_decision(result)
    model_usage = payload.get("modelUsage")
    return (
        {
            "tool": "claude-code",
            "tool_version": observed_version(["claude", "--version"]),
            "requested_model": model,
            "resolved_models": sorted(model_usage) if isinstance(model_usage, dict) else [],
            "cost_usd": number_or_none(payload.get("total_cost_usd")),
            "usage": payload.get("usage"),
        },
        decision,
    )


def run_codex(
    prompt: str,
    cell_dir: Path,
    inputs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    model = required_text(inputs, "codex_judge_model")
    effort = required_text(inputs, "codex_judge_reasoning_effort")
    response_path = cell_dir / "codex-response.json"
    events_path = cell_dir / "codex-events.jsonl"
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
        str(response_path),
        prompt,
    ]
    proc = subprocess.run(cmd, cwd=WORKFLOW_DIR, text=True, capture_output=True)
    write_text(cell_dir / "stderr.log", proc.stderr)
    write_text(events_path, proc.stdout)
    require_success(proc, "Codex judge")
    if not response_path.is_file():
        raise SystemExit("Codex judge did not write a final response")
    decision = parse_decision(response_path.read_text(encoding="utf-8"))
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
    return (
        {
            "tool": "codex-cli",
            "tool_version": observed_version(["codex", "--version"]),
            "requested_model": model,
            "reasoning_effort": effort,
            "thread_id": thread_id,
            "cost_usd": None,
            "cost_basis": "Codex CLI reports token usage but no dollar-cost field",
            "usage": usage,
        },
        decision,
    )


def parse_decision(value: str) -> dict[str, str]:
    cleaned = value.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"judge response is not a JSON decision: {exc}: {value[-1000:]}") from exc
    winner = str(payload.get("winner", "")).upper()
    reason = str(payload.get("reason", "")).strip()
    if winner not in {"A", "B"} or not reason:
        raise SystemExit(f"invalid forced-choice decision: {payload}")
    return {"winner": winner, "reason": reason}


def required_text(inputs: dict[str, Any], key: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing non-empty string input: {key}")
    return value


def resolve_path(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (WORKFLOW_DIR / path).resolve()


def require_success(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode == 0:
        return
    detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostic output"
    raise SystemExit(f"{label} failed ({proc.returncode}): {detail[-3000:]}")


def observed_version(cmd: list[str]) -> str | None:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return (proc.stdout or proc.stderr).strip() or None


def number_or_none(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def write_text(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n" if value else "", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
