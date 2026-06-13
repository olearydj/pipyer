"""Run-to-run comparison from event logs.

The event log is the source of truth: resumed invocations, skipped units, and
recomputed units are folded into one logical run before comparison.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pipyer.records.run import parse_event_log
from pipyer.runner.context import event_unit_key

COMPARE_SCHEMA_VERSION = "1"


class CompareError(RuntimeError):
    pass


@dataclass(frozen=True)
class CellSelector:
    params: dict[str, Any] | None = None
    cell_index: int | None = None


@dataclass
class LogicalRun:
    run_dir: Path
    run_id: str
    workflow_name: str | None
    workflow_hash: str | None
    events: list[dict[str, Any]]
    final_totals: dict[str, Any]
    latest_units: dict[str, dict[str, Any]]
    cells: dict[int, dict[str, Any]]


def compare_runs(
    left: str | Path,
    right: str | Path | None = None,
    *,
    results_dir: Path,
    left_selector: CellSelector | None = None,
    right_selector: CellSelector | None = None,
    stability: bool = False,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    left_run = load_logical_run(resolve_run_dir(left, results_dir))
    right_run = left_run if right is None else load_logical_run(resolve_run_dir(right, results_dir))

    left_cell = select_cell(left_run, left_selector)
    right_cell = select_cell(right_run, right_selector)
    if right is None and (left_cell is None or right_cell is None):
        raise CompareError("comparing cells within one run requires both cell selectors")

    left_view = _view(left_run, left_cell)
    right_view = _view(right_run, right_cell)
    record = _build_record(left_view, right_view, stability=stability)

    target_dir = output_dir or _default_output_dir(results_dir, left_view, right_view)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "comparison.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (target_dir / "comparison.md").write_text(render_markdown(record), encoding="utf-8")
    return record, target_dir


def resolve_run_dir(value: str | Path, results_dir: Path) -> Path:
    path = Path(value)
    if (path / "events.jsonl").is_file():
        return path
    candidate = results_dir / str(value)
    if (candidate / "events.jsonl").is_file():
        return candidate
    raise CompareError(f"no run found for {value!r} (looked directly and under {results_dir})")


def load_logical_run(run_dir: Path) -> LogicalRun:
    events, _corrupt = parse_event_log((run_dir / "events.jsonl").read_text(encoding="utf-8"))
    started = next((e for e in events if e.get("event") == "run_started"), {})
    final = next((e for e in reversed(events) if e.get("event") == "run_finished"), {})
    latest: dict[str, dict[str, Any]] = {}
    cells: dict[int, dict[str, Any]] = {}
    for event in events:
        if event.get("event") == "cell_started":
            cells[event["cell_index"]] = dict(event.get("matrix") or {})
        elif event.get("event") == "step_result":
            latest[event_unit_key(event)] = event
            if event.get("cell_index") is not None:
                cells.setdefault(event["cell_index"], dict(event.get("matrix") or {}))
    return LogicalRun(
        run_dir=run_dir,
        run_id=str(started.get("run_id") or run_dir.name),
        workflow_name=started.get("workflow_name"),
        workflow_hash=started.get("workflow_hash"),
        events=events,
        final_totals=final.get("totals") or {},
        latest_units=latest,
        cells=cells,
    )


def select_cell(run: LogicalRun, selector: CellSelector | None) -> int | None:
    if selector is None or (selector.cell_index is None and not selector.params):
        return None
    if selector.cell_index is not None:
        if selector.cell_index not in run.cells:
            raise CompareError(f"{run.run_id}: no cell[{selector.cell_index}]")
        if selector.params:
            matrix = run.cells[selector.cell_index]
            if any(matrix.get(k) != v for k, v in selector.params.items()):
                raise CompareError(
                    f"{run.run_id}: cell[{selector.cell_index}] does not match selector"
                )
        return selector.cell_index
    assert selector.params is not None
    matches = [
        index
        for index, matrix in run.cells.items()
        if all(matrix.get(key) == value for key, value in selector.params.items())
    ]
    if not matches:
        raise CompareError(f"{run.run_id}: no cell matches {selector.params}")
    if len(matches) > 1:
        cells = ", ".join(f"cell[{i}]" for i in sorted(matches))
        raise CompareError(
            f"{run.run_id}: selector {selector.params} matches multiple cells ({cells}); "
            "use --left-cell-index/--right-cell-index"
        )
    return matches[0]


def _view(run: LogicalRun, cell_index: int | None) -> dict[str, Any]:
    units = {
        _unit_label(event): _normalize_paths(event, run.run_dir)
        for event in run.latest_units.values()
        if cell_index is None or event.get("cell_index") == cell_index
    }
    step_events = [
        event
        for event in run.events
        if event.get("event") == "step_result"
        and (cell_index is None or event.get("cell_index") == cell_index)
    ]
    summaries = _summary_outputs(run, cell_index)
    return {
        "run_id": run.run_id,
        "run_dir": str(run.run_dir),
        "workflow_name": run.workflow_name,
        "workflow_hash": run.workflow_hash,
        "cell_index": cell_index,
        "matrix": None if cell_index is None else run.cells.get(cell_index, {}),
        "summaries": _normalize_paths(summaries, run.run_dir),
        "units": units,
        "cost": _cost(step_events),
        "latency_ms": sum(int(e.get("duration_ms") or 0) for e in step_events),
        "counts": {
            "units": len(units),
            "success": sum(1 for e in units.values() if e.get("status") == "success"),
            "failure": sum(1 for e in units.values() if e.get("status") == "failure"),
            "skipped": sum(1 for e in units.values() if e.get("status") == "skipped"),
        },
    }


def _summary_outputs(run: LogicalRun, cell_index: int | None) -> dict[str, Any]:
    outputs = run.final_totals.get("outputs") or {}
    summaries: dict[str, Any] = {}
    for name, value in outputs.items():
        if not name.startswith("summary_"):
            continue
        if cell_index is None:
            summaries[name] = value
        elif isinstance(value, list):
            match = next((row for row in value if row.get("cell_index") == cell_index), None)
            summaries[name] = None if match is None else match.get("value")
        else:
            summaries[name] = value
    return summaries


def _build_record(
    left: dict[str, Any], right: dict[str, Any], *, stability: bool
) -> dict[str, Any]:
    left_units = left["units"]
    right_units = right["units"]
    common = sorted(set(left_units) & set(right_units))
    only_left = sorted(set(left_units) - set(right_units))
    only_right = sorted(set(right_units) - set(left_units))
    changed = []
    same = 0
    for key in common:
        l_out = left_units[key].get("output")
        r_out = right_units[key].get("output")
        if l_out == r_out and left_units[key].get("status") == right_units[key].get("status"):
            same += 1
        else:
            changed.append(
                {
                    "unit": key,
                    "left_status": left_units[key].get("status"),
                    "right_status": right_units[key].get("status"),
                    "left_output": l_out,
                    "right_output": r_out,
                }
            )

    summary_diffs = {}
    for name in sorted(set(left["summaries"]) | set(right["summaries"])):
        l_val = left["summaries"].get(name)
        r_val = right["summaries"].get(name)
        summary_diffs[name] = {
            "left": l_val,
            "right": r_val,
            "equal": l_val == r_val,
            "delta": _numeric_delta(l_val, r_val),
        }

    return {
        "schema_version": COMPARE_SCHEMA_VERSION,
        "mode": "stability" if stability else "comparison",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "left": _side_meta(left),
        "right": _side_meta(right),
        "summaries": summary_diffs,
        "units": {
            "same": same,
            "different": len(changed),
            "only_left": only_left,
            "only_right": only_right,
            "changed": changed,
        },
        "cost": _pair_delta(left["cost"], right["cost"]),
        "latency_ms": {
            "left": left["latency_ms"],
            "right": right["latency_ms"],
            "delta": right["latency_ms"] - left["latency_ms"],
        },
    }


def _side_meta(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": view["run_id"],
        "run_dir": view["run_dir"],
        "workflow_name": view["workflow_name"],
        "workflow_hash": view["workflow_hash"],
        "cell_index": view["cell_index"],
        "matrix": view["matrix"],
        "counts": view["counts"],
    }


def _cost(events: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    cost = Decimal(0)
    any_cost = False
    calls = 0
    for event in events:
        usage = event.get("usage")
        if not usage:
            continue
        calls += 1
        input_tokens += usage.get("input_tokens") or 0
        output_tokens += usage.get("output_tokens") or 0
        if usage.get("estimated_cost") is not None:
            cost += Decimal(str(usage["estimated_cost"]))
            any_cost = True
    return {
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": str(cost) if any_cost else None,
    }


def _pair_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    delta_cost = None
    if left.get("estimated_cost") is not None and right.get("estimated_cost") is not None:
        delta_cost = str(
            Decimal(str(right["estimated_cost"])) - Decimal(str(left["estimated_cost"]))
        )
    return {
        "left": left,
        "right": right,
        "delta": {
            "calls": right["calls"] - left["calls"],
            "input_tokens": right["input_tokens"] - left["input_tokens"],
            "output_tokens": right["output_tokens"] - left["output_tokens"],
            "estimated_cost": delta_cost,
        },
    }


def _numeric_delta(left: Any, right: Any) -> Any:
    if isinstance(left, int | float) and isinstance(right, int | float):
        return right - left
    if isinstance(left, dict) and isinstance(right, dict):
        out = {}
        for key in sorted(set(left) | set(right)):
            delta = _numeric_delta(left.get(key), right.get(key))
            if delta is not None:
                out[key] = delta
        return out or None
    return None


def _unit_label(event: dict[str, Any]) -> str:
    unit = event["step"]
    if event.get("item_index") is not None:
        unit += f"[{event['item_index']}]"
    return unit


def _normalize_paths(value: Any, run_dir: Path) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_paths(v, run_dir) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_paths(v, run_dir) for v in value]
    if not isinstance(value, str):
        return value
    path = Path(value)
    try:
        if path.is_absolute() and path.is_relative_to(run_dir):
            return str(path.relative_to(run_dir))
    except ValueError:
        pass
    marker = "/outputs/"
    if marker in value:
        suffix = value.split(marker, 1)[1]
        if (run_dir / "outputs" / suffix).exists():
            return str(Path("outputs") / suffix)
    return value


def _default_output_dir(results_dir: Path, left: dict[str, Any], right: dict[str, Any]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    left_id = _safe_id(left["run_id"], left.get("cell_index"))
    right_id = _safe_id(right["run_id"], right.get("cell_index"))
    return results_dir / "comparisons" / f"{stamp}-{left_id}-vs-{right_id}"


def _safe_id(run_id: str, cell_index: int | None) -> str:
    text = run_id if cell_index is None else f"{run_id}-cell{cell_index}"
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)


def render_markdown(record: dict[str, Any]) -> str:
    lines = [
        "# Pipyer Comparison",
        "",
        f"Mode: `{record['mode']}`",
        "",
        "| Side | Run | Cell | Matrix | Units |",
        "|------|-----|------|--------|-------|",
    ]
    for side in ("left", "right"):
        meta = record[side]
        cell = "-" if meta["cell_index"] is None else f"cell[{meta['cell_index']}]"
        matrix = _md(json.dumps(meta.get("matrix") or {}, sort_keys=True))
        counts = meta["counts"]
        lines.append(
            f"| {side} | `{meta['run_id']}` | {cell} | {matrix} | "
            f"{counts['success']} ok / {counts['failure']} failed / {counts['skipped']} skipped |"
        )
    lines += [
        "",
        "## Summary Outputs",
        "",
    ]
    if not record["summaries"]:
        lines.append("No `summary_*` outputs found.")
    else:
        lines += ["| Output | Equal | Delta |", "|--------|-------|-------|"]
        for name, diff in record["summaries"].items():
            lines.append(f"| `{name}` | {diff['equal']} | {_md(json.dumps(diff['delta']))} |")
    lines += [
        "",
        "## Units",
        "",
        f"- Same: {record['units']['same']}",
        f"- Different: {record['units']['different']}",
        f"- Only left: {len(record['units']['only_left'])}",
        f"- Only right: {len(record['units']['only_right'])}",
        "",
        "## Cost And Latency",
        "",
        f"- Left cost: {record['cost']['left']['estimated_cost'] or 'n/a'}",
        f"- Right cost: {record['cost']['right']['estimated_cost'] or 'n/a'}",
        f"- Cost delta: {record['cost']['delta']['estimated_cost'] or 'n/a'}",
        f"- Latency delta ms: {record['latency_ms']['delta']}",
        "",
    ]
    return "\n".join(lines)


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
