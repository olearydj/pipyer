"""The workflow schema: canonical form of a Pipyer workflow (data-model.md).

Structural rules live here (everything `model_validate` can judge); the
cross-checks - reference resolution, prompt coverage, alias existence - live in
pipyer.validation. `extra="forbid"` everywhere: a stale workflow fails loudly.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipyer.schema.components import (
    AssertionsConfig,
    FileReadConfig,
    FileWriteConfig,
    LlmConfig,
    LlmJudgeConfig,
    PythonConfig,
    ShellConfig,
)

NAME_PATTERN = r"^[a-z][a-z0-9_]*$"
SUPPORTED_SCHEMA_VERSIONS = ("2",)

Name = Annotated[str, Field(pattern=NAME_PATTERN)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputDecl(_Model):
    type: Literal["string", "number", "boolean", "path", "json"]
    required: bool = True
    default: Any | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _default_only_when_optional(self) -> InputDecl:
        if self.required and self.default is not None:
            raise ValueError("default is only allowed when required is false")
        return self


class ModelAlias(_Model):
    model: str
    settings: dict[str, Any] = Field(default_factory=dict)
    # Structured-output mode (R16): None = provider default for hosted aliases.
    # Local aliases (settings.base_url) must set it explicitly - never auto-picked;
    # enforced by validation, not here.
    output_mode: Literal["tool", "native", "prompted"] | None = None


class Settings(_Model):
    concurrency: int = Field(default=1, ge=1)
    max_failures: int | None = Field(default=None, ge=0)
    max_failure_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    results_dir: str = "runs"


class _StepBase(_Model):
    name: Name
    inputs: dict[str, Any] = Field(default_factory=dict)
    each: str | None = None


class FileReadStep(_StepBase):
    component: Literal["file_read"]
    config: FileReadConfig


class FileWriteStep(_StepBase):
    component: Literal["file_write"]
    config: FileWriteConfig


class ShellStep(_StepBase):
    component: Literal["shell"]
    config: ShellConfig


class PythonStep(_StepBase):
    component: Literal["python"]
    config: PythonConfig


class LlmStep(_StepBase):
    component: Literal["llm"]
    config: LlmConfig


class LlmJudgeStep(_StepBase):
    component: Literal["llm_judge"]
    config: LlmJudgeConfig


class AssertionsStep(_StepBase):
    component: Literal["assertions"]
    config: AssertionsConfig


STEP_CLASSES = (
    FileReadStep,
    FileWriteStep,
    ShellStep,
    PythonStep,
    LlmStep,
    LlmJudgeStep,
    AssertionsStep,
)

Step = Annotated[
    FileReadStep | FileWriteStep | ShellStep | PythonStep | LlmStep | LlmJudgeStep | AssertionsStep,
    Field(discriminator="component"),
]


class Workflow(_Model):
    schema_version: str
    name: Name
    description: str | None = None
    inputs: dict[Name, InputDecl] = Field(default_factory=dict)
    models: dict[Name, ModelAlias] = Field(default_factory=dict)
    matrix: dict[Name, Annotated[list[Any], Field(min_length=1)]] = Field(default_factory=dict)
    steps: Annotated[list[Step], Field(min_length=1)]
    settings: Settings = Field(default_factory=Settings)
    outputs: dict[Name, str] = Field(default_factory=dict)
