"""Checkpoint: atomic snapshot, reconstructible from the log (R6; contracts/runner-api.md).

The event log is authoritative; the checkpoint is derived state for fast
resume. `reconstruct_checkpoint` rebuilds it from events.jsonl alone -
tolerating a corrupt trailing line - and must equal the on-disk snapshot for
any cleanly written run (fixture 3 deletes the file and compares).
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pipyer.records.run import CheckpointSnapshot, CompletedEntry, parse_event_log
from pipyer.runner.context import unit_key

RECORD_SCHEMA_VERSION = "1"
# Deterministic timestamp inside snapshots so log-reconstruction equals the
# on-disk file byte-for-byte fields-wise; the log carries the real times.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def write_checkpoint(path: Path, snapshot: CheckpointSnapshot) -> None:
    """Atomic write: temp file in the same directory, flush, fsync, rename."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".checkpoint-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(snapshot.model_dump_json())
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def build_checkpoint(
    events: list[dict], *, written_at: datetime | None = None
) -> CheckpointSnapshot:
    """Fold parsed events into the snapshot the run would have written."""
    run_id = ""
    workflow_hash = ""
    config_hash = ""
    completed: dict[str, CompletedEntry] = {}
    for index, event in enumerate(events):
        kind = event.get("event")
        if kind == "run_started":
            run_id = event["run_id"]
            workflow_hash = event["workflow_hash"]
            config_hash = event.get("config_snapshot", {}).get("config_hash", "")
        elif kind == "step_result" and event.get("status") == "success":
            key = unit_key(event["step"], event.get("item_index"))
            completed[key] = CompletedEntry(input_hash=event["input_hash"], event_ref=str(index))
        elif kind == "step_result":
            key = unit_key(event["step"], event.get("item_index"))
            completed.pop(key, None)
    return CheckpointSnapshot(
        schema_version=RECORD_SCHEMA_VERSION,
        run_id=run_id,
        workflow_hash=workflow_hash,
        config_hash=config_hash,
        completed=completed,
        written_at=written_at or _EPOCH,
    )


def reconstruct_checkpoint(event_log_path: Path) -> CheckpointSnapshot:
    """Rebuild the checkpoint purely from the event log (public API)."""
    events, _corrupt_trailing = parse_event_log(event_log_path.read_text(encoding="utf-8"))
    return build_checkpoint(events)
