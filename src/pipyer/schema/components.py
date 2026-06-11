"""Per-component configuration models (data-model.md component table).

`python` is a distinct component so transformation steps are visible and
countable by the falsification census (R11). `shell` commands are static argv
lists - inputs are delivered via stdin JSON and PIPYER_INPUT_* env vars, never
interpolated (runner semantics, Feature 002).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileReadConfig(_Config):
    path: str
    format: Literal["text", "json", "jsonl"] = "text"


class FileWriteConfig(_Config):
    path: str
    format: Literal["text", "json", "jsonl", "markdown"] = "text"


class ShellConfig(_Config):
    command: Annotated[list[str], Field(min_length=1)]
    parse_stdout: Literal["text", "json"] = "text"
    timeout_s: int | None = Field(default=None, ge=1)


class PythonConfig(_Config):
    script: str
    timeout_s: int | None = Field(default=None, ge=1)


class LlmConfig(_Config):
    model: str
    prompt: str
    output_schema: str | dict[str, Any]
    max_validation_retries: int = Field(default=2, ge=0)


DEFAULT_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "score": {"type": ["number", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["verdict", "reasoning"],
}


class LlmJudgeConfig(_Config):
    model: str
    prompt: str
    output_schema: str | dict[str, Any] = Field(
        default_factory=lambda: dict(DEFAULT_VERDICT_SCHEMA)
    )
    max_validation_retries: int = Field(default=2, ge=0)


CheckOp = Literal[
    "equals", "not_equals", "contains", "matches", "gte", "lte", "exists", "non_empty"
]


class Check(_Config):
    input: str
    op: CheckOp
    expected: Any | None = None


class AssertionsConfig(_Config):
    checks: Annotated[list[Check], Field(min_length=1)]
