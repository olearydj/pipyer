"""The per-step record: StepResult, UsageCost, StepError (data-model.md; FR-014/015).

The error taxonomy is the R8 first edition, pressure-tested by the spike
(spike-report.md Q3): no enum changes were needed. Two documented mappings for
the Feature 002 llm component: ContentFilterError → provider_error (type
preserved in detail), IncompleteToolCall → output_validation_error (detail).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class ErrorCategory(StrEnum):
    OUTPUT_VALIDATION_ERROR = "output_validation_error"
    TRANSPORT_ERROR = "transport_error"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    NONZERO_EXIT = "nonzero_exit"
    ASSERTION_FAILED = "assertion_failed"
    UPSTREAM_FAILURE = "upstream_failure"
    INTERRUPTED = "interrupted"
    UNCLASSIFIED = "unclassified"


ERROR_CATEGORIES = frozenset(category.value for category in ErrorCategory)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepError(_Model):
    category: ErrorCategory
    message: str
    detail: Any | None = None


class UsageCost(_Model):
    provider: str
    model: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: Decimal | None = None
    cost_table_version: str | None = None
    counts_source: Literal["provider_reported", "estimated"]
    validation_attempts: int = Field(default=1, ge=1)

    @field_serializer("estimated_cost")
    def _cost_as_string(self, value: Decimal | None) -> str | None:
        # String-form decimal, never a float: the penny-drift guard. Decimal
        # arithmetic on read, exact text on disk.
        return None if value is None else str(value)


ComponentType = Literal[
    "file_read", "file_write", "shell", "python", "llm", "llm_judge", "assertions"
]


class StepResult(_Model):
    schema_version: str
    run_id: str
    step: str
    component: ComponentType
    status: Literal["success", "failure", "skipped"]
    attempt: int = Field(default=1, ge=1)
    output: Any | None = None
    error: StepError | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    usage: UsageCost | None = None
    matrix: dict[str, Any] | None = None
    item_index: int | None = Field(default=None, ge=0)
    entity_id: str | None = None
    input_refs: dict[str, str] = Field(default_factory=dict)
    input_hash: str
    component_version: str

    @model_validator(mode="after")
    def _status_constraints(self) -> StepResult:
        if self.status == "success":
            if self.error is not None:
                raise ValueError("success records must not carry an error")
            if self.component in ("llm", "llm_judge") and self.usage is None:
                raise ValueError("usage is required on successful llm/llm_judge records")
        else:
            # Failures carry their failure; skips carry their reason. Never silence.
            if self.error is None:
                raise ValueError(f"{self.status} records must carry an error/reason")
        return self
