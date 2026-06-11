"""Run-level records, JSONL event framing, checkpoint snapshot (data-model.md; R6).

The JSONL event log is the single source of truth - append-only, single-writer,
each line a self-contained event carrying schema_version and run_id. The
checkpoint snapshot is derived state: atomically written, reconstructible from
the log, never authoritative over it.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipyer.records.step_result import StepResult


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


RunStatus = Literal["completed", "halted", "interrupted"]


class RunRecord(_Model):
    schema_version: str
    run_id: str
    workflow_name: str
    workflow_hash: str
    config_snapshot: dict[str, Any]  # resolved inputs, alias table, settings - never secrets
    git_commit: str | None = None
    started_at: datetime
    finished_at: datetime
    status: RunStatus
    halt_reason: str | None = None
    totals: dict[str, Any]

    @model_validator(mode="after")
    def _halts_are_explained(self) -> RunRecord:
        if self.status == "halted" and not self.halt_reason:
            raise ValueError("halted runs must record a halt_reason")
        return self


class CompletedEntry(_Model):
    input_hash: str
    event_ref: str


class CheckpointSnapshot(_Model):
    schema_version: str
    run_id: str
    workflow_hash: str
    config_hash: str
    completed: dict[str, CompletedEntry] = Field(default_factory=dict)
    written_at: datetime


# ------------------------------------------------------------------ event framing


class RunStartedEvent(_Model):
    event: Literal["run_started"] = "run_started"
    schema_version: str
    run_id: str
    workflow_name: str
    workflow_hash: str
    config_snapshot: dict[str, Any]
    git_commit: str | None = None
    started_at: datetime


class StepResultEvent(StepResult):
    event: Literal["step_result"] = "step_result"


class EachExpandedEvent(_Model):
    """An `each` collection's expansion is itself recorded - including zero items
    (R12: an empty collection is legitimate runtime data, never a silent no-op)."""

    event: Literal["each_expanded"] = "each_expanded"
    schema_version: str
    run_id: str
    step: str
    item_count: int = Field(ge=0)
    at: datetime


class RunResumedEvent(_Model):
    """The resume boundary: one event whose payload is the resume diff (R20).

    Keys in the lists follow the execution-unit convention: "<step>" for scalar
    steps, "<step>[<index>]" for `each` items.
    """

    event: Literal["run_resumed"] = "run_resumed"
    schema_version: str
    run_id: str
    resumed_from_status: str
    skipped: list[str] = Field(default_factory=list)
    recompute: list[dict[str, str]] = Field(default_factory=list)  # {key, reason}
    failed_not_retried: list[str] = Field(default_factory=list)
    failed_retried: list[str] = Field(default_factory=list)
    lock_reclaimed: bool = False
    at: datetime


class RunHaltedEvent(_Model):
    event: Literal["run_halted"] = "run_halted"
    schema_version: str
    run_id: str
    reason: str
    at: datetime


class RunFinishedEvent(_Model):
    event: Literal["run_finished"] = "run_finished"
    schema_version: str
    run_id: str
    status: RunStatus
    finished_at: datetime
    totals: dict[str, Any]


Event = (
    RunStartedEvent
    | StepResultEvent
    | EachExpandedEvent
    | RunResumedEvent
    | RunHaltedEvent
    | RunFinishedEvent
)


def event_line(event: Event | StepResult) -> str:
    """Serialize one event as one self-contained JSONL line."""
    if isinstance(event, StepResult) and not isinstance(event, StepResultEvent):
        event = StepResultEvent(**event.model_dump())
    return json.dumps(event.model_dump(mode="json"), separators=(",", ":"))


def parse_event_log(text: str) -> tuple[list[dict[str, Any]], bool]:
    """Parse a JSONL event log, detecting a corrupt trailing line.

    A trailing line that fails to parse is the signature of an interrupted
    write: it is dropped and flagged (corrupt_trailing=True). A parse failure
    anywhere else violates the append-only single-writer guarantee and raises.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    events: list[dict[str, Any]] = []
    corrupt_trailing = False
    for i, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            if i == len(lines) - 1:
                corrupt_trailing = True
            else:
                raise ValueError(
                    f"corrupt event log: line {i + 1} of {len(lines)} is unparseable "
                    "(only the trailing line may be, after an interrupted write)"
                ) from error
    return events, corrupt_trailing
