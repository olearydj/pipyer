"""Resume: locate the prior run, replay its log, plan what to skip (R20).

The event log is authoritative; the checkpoint is cross-checked when present
and a mismatch is a loud error (run-directory contract). Failed units never
enter `completed` - they re-execute only with --retry-failed. The diff is
accounted at the run_resumed boundary (what replay knows) and in run_finished
totals (what execution decided: resume_skipped / recomputed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipyer.records.run import RunResumedEvent, parse_event_log
from pipyer.runner.checkpoint import build_checkpoint
from pipyer.runner.context import unit_key


class NoPriorRunError(RuntimeError):
    """`resume` was requested but no matching prior run exists."""


class ResumePlan:
    def __init__(self, run_dir: Path, events: list[dict[str, Any]], retry_failed: bool) -> None:
        self.run_dir = run_dir
        self.events = events
        self.run_id = run_dir.name
        self.retry_failed = retry_failed

        self.completed: dict[str, str] = {}  # unit key -> input_hash
        self.projections: dict[str, Any] = {}
        self.attempts: dict[str, int] = {}
        failed: dict[str, bool] = {}
        self.prior_status = "interrupted"
        for event in events:
            kind = event.get("event")
            if kind == "run_finished":
                self.prior_status = event.get("status", "interrupted")
            if kind != "step_result":
                continue
            key = unit_key(event["step"], event.get("item_index"))
            self.attempts[key] = max(self.attempts.get(key, 0), event.get("attempt", 1))
            if event.get("status") == "success":
                self.completed[key] = event["input_hash"]
                self.projections[key] = event.get("output")
                failed.pop(key, None)
            elif event.get("status") == "failure":
                failed[key] = True
                self.completed.pop(key, None)
        self.failed_units = set(failed)
        self.retry_units = self.failed_units if retry_failed else set()

    def boundary_event(self, *, schema_version: str, lock_reclaimed: bool, at) -> RunResumedEvent:
        return RunResumedEvent(
            schema_version=schema_version,
            run_id=self.run_id,
            resumed_from_status=self.prior_status,
            failed_not_retried=sorted(self.failed_units - self.retry_units),
            failed_retried=sorted(self.retry_units),
            lock_reclaimed=lock_reclaimed,
            at=at,
        )


def locate_run(results_dir: Path, run_id: str | None) -> Path:
    if run_id is not None and run_id != "last":
        run_dir = results_dir / run_id
        if not (run_dir / "events.jsonl").is_file():
            raise NoPriorRunError(f"no run {run_id!r} under {results_dir} (no events.jsonl)")
        return run_dir
    candidates = sorted(
        (d for d in results_dir.glob("*") if (d / "events.jsonl").is_file()),
        key=lambda d: d.name,
    )
    if not candidates:
        raise NoPriorRunError(
            f"--resume last: no prior runs under {results_dir} - "
            "a resume never silently starts a fresh run"
        )
    return candidates[-1]


def load_resume_plan(results_dir: Path, *, run_id: str | None, retry_failed: bool) -> ResumePlan:
    run_dir = locate_run(Path(results_dir), run_id)
    text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    events, _corrupt_trailing = parse_event_log(text)  # trailing corruption recovered, by design
    plan = ResumePlan(run_dir, events, retry_failed)

    checkpoint_path = run_dir / "checkpoint.json"
    if checkpoint_path.is_file():
        import json

        on_disk = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        rebuilt = build_checkpoint(events)
        if set(on_disk.get("completed", {})) - set(rebuilt.completed):
            raise RuntimeError(
                f"checkpoint/log mismatch in {run_dir}: the checkpoint claims completed work "
                "the authoritative log does not record (R6) - refusing to resume"
            )
    return plan
