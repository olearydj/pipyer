"""derive_summary: the markdown run summary, from the event log alone (R21).

Byte-stable for a given log - no generation timestamps - so regeneration after
deleting summary.md reproduces it exactly (SC-005). Workflow-reported
statistics surface by naming convention: any declared output whose name starts
with `summary_` and resolves to a JSON object renders as its own section; the
runner never learns what the numbers mean.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pipyer.records.run import parse_event_log


def derive_summary(event_log_path: Path) -> str:
    events, corrupt_trailing = parse_event_log(Path(event_log_path).read_text(encoding="utf-8"))
    started = _first(events, "run_started")
    finished = _last(events, "run_finished")
    halted = _last(events, "run_halted")
    resumed = [e for e in events if e.get("event") == "run_resumed"]
    results = [e for e in events if e.get("event") == "step_result"]
    expansions = [e for e in events if e.get("event") == "each_expanded"]

    run_id = (started or {}).get("run_id", "unknown")
    status = (finished or {}).get("status", "in progress" if not finished else "unknown")
    lines: list[str] = []
    add = lines.append

    add(f"# Run {run_id}")
    add("")
    add(f"- Workflow: `{(started or {}).get('workflow_name', '?')}`")
    add(f"- Workflow hash: `{(started or {}).get('workflow_hash', '?')}`")
    add(f"- Status: {status}")
    add(f"- Started: {(started or {}).get('started_at', '?')}")
    if finished:
        add(f"- Finished: {finished.get('finished_at', '?')}")
    if halted:
        add(f"- Halt reason: {halted.get('reason')}")
    if resumed:
        add(f"- Resumed: {len(resumed)} time(s)")
    if corrupt_trailing:
        add("- Note: a corrupt trailing log line was recovered on replay")
    add("")

    totals = (finished or {}).get("totals", {})
    add("## Totals")
    add("")
    add("| Attempted | Succeeded | Failed | Skipped | Not attempted |")
    add("|-----------|-----------|--------|---------|---------------|")
    add(
        f"| {totals.get('attempted', len(results))} | {totals.get('succeeded', '?')} "
        f"| {totals.get('failed', '?')} | {totals.get('skipped', '?')} "
        f"| {totals.get('not_attempted', 0)} |"
    )
    add("")

    if resumed:
        add("## Resume")
        add("")
        for event in resumed:
            add(f"- Resumed from a `{event.get('resumed_from_status')}` run")
            if event.get("lock_reclaimed"):
                add("- A stale writer lock was reclaimed")
            if event.get("failed_retried"):
                add(f"- Failed units retried: {', '.join(event['failed_retried'])}")
            if event.get("failed_not_retried"):
                add(
                    "- Failed units NOT retried (pass --retry-failed to retry): "
                    + ", ".join(event["failed_not_retried"])
                )
        skipped_on_resume = totals.get("resume_skipped", [])
        recomputed = totals.get("recomputed", [])
        add(f"- Units skipped on hash match: {len(skipped_on_resume)}")
        add(f"- Units recomputed: {len(recomputed)}")
        if recomputed:
            add("  - " + ", ".join(recomputed))
        add("")

    add("## Steps")
    add("")
    add("| Step | Component | Success | Failure | Skipped | Items | Duration ms |")
    add("|------|-----------|---------|---------|---------|-------|-------------|")
    step_order: list[str] = []
    by_step: dict[str, list[dict[str, Any]]] = {}
    for event in results:
        if event["step"] not in by_step:
            step_order.append(event["step"])
        by_step.setdefault(event["step"], []).append(event)
    item_counts = {e["step"]: e["item_count"] for e in expansions}
    for step in step_order:
        rows = by_step[step]
        counts = {"success": 0, "failure": 0, "skipped": 0}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        items = item_counts.get(step, "-")
        duration_ms = sum(int(row.get("duration_ms") or 0) for row in rows)
        add(
            f"| {step} | {rows[0]['component']} | {counts['success']} | "
            f"{counts['failure']} | {counts['skipped']} | {items} | {duration_ms} |"
        )
    for step, count in item_counts.items():
        if count == 0:
            add(f"| {step} | - | 0 | 0 | 0 | 0 | 0 |")
    add("")

    cost_rows = [e for e in results if e.get("usage")]
    if cost_rows:
        add("## Cost")
        add("")
        add("| Step | Model | Calls | Input tok | Output tok | Est. cost (USD) | Counts |")
        add("|------|-------|-------|-----------|------------|-----------------|--------|")
        agg: dict[tuple[str, str], dict[str, Any]] = {}
        for event in cost_rows:
            usage = event["usage"]
            key = (event["step"], usage["model"])
            slot = agg.setdefault(
                key,
                {
                    "calls": 0,
                    "in": 0,
                    "out": 0,
                    "cost": Decimal(0),
                    "src": usage["counts_source"],
                    "any_cost": False,
                },
            )
            slot["calls"] += 1
            slot["in"] += usage.get("input_tokens") or 0
            slot["out"] += usage.get("output_tokens") or 0
            if usage.get("estimated_cost") is not None:
                slot["cost"] += Decimal(str(usage["estimated_cost"]))
                slot["any_cost"] = True
        total_cost = Decimal(0)
        any_cost = False
        for (step, model), slot in agg.items():
            cost_text = str(slot["cost"]) if slot["any_cost"] else "n/a"
            if slot["any_cost"]:
                total_cost += slot["cost"]
                any_cost = True
            add(
                f"| {step} | {model} | {slot['calls']} | {slot['in']} | {slot['out']} "
                f"| {cost_text} | {slot['src']} |"
            )
        add("")
        add(f"Total estimated cost: {str(total_cost) if any_cost else 'n/a'} USD")
        add("")

    problems = [e for e in results if e["status"] in ("failure", "skipped")]
    add("## Failures and skips")
    add("")
    if not problems:
        add("None - every unit succeeded.")
    else:
        add("| Unit | Status | Category | Message |")
        add("|------|--------|----------|---------|")
        for event in problems:
            index = event.get("item_index")
            unit = event["step"] if index is None else f"{event['step']}[{index}]"
            error = event.get("error") or {}
            add(
                f"| {unit} | {event['status']} | {error.get('category', '?')} "
                f"| {_cell(error.get('message', ''))} |"
            )
    add("")

    outputs = totals.get("outputs") or {}
    if outputs:
        add("## Declared outputs")
        add("")
        for name in sorted(outputs):
            value = outputs[name]
            preview = _cell(json.dumps(value, default=str)) if value is not None else "null"
            if len(preview) > 120:
                preview = preview[:117] + "..."
            add(f"- `{name}`: {preview}")
        add("")

    for name in sorted(outputs):
        if name.startswith("summary_") and isinstance(outputs[name], dict):
            add(f"## {name.removeprefix('summary_').replace('_', ' ').title()}")
            add("")
            add("```json")
            add(json.dumps(outputs[name], indent=2, sort_keys=True, default=str))
            add("```")
            add("")

    return "\n".join(lines).rstrip() + "\n"


def _first(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    return next((e for e in events if e.get("event") == kind), None)


def _last(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    found = [e for e in events if e.get("event") == kind]
    return found[-1] if found else None


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
