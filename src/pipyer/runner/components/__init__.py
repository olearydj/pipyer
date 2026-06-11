"""Component executors: one callable per component type.

An executor takes (step, resolved_inputs, ctx, unit_index) and returns the
step's projection mapping - the JSON object stored as StepResult.output and the
namespace dotted references resolve into (e.g. file_read → {"content": ...},
shell → {"stdout": ...}). Failures raise StepFailure carrying the taxonomy
category; the engine turns them into failure-status StepResults.

`llm.py` is the ONLY module in src/ that imports pydantic_ai (R10); it is
imported lazily here so loading the registry never pulls the substrate.
"""

from __future__ import annotations

from typing import Any

from pipyer.records.step_result import ErrorCategory, UsageCost


class StepFailure(Exception):
    """A component-level failure with its taxonomy category (never an omission)."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        detail: Any | None = None,
        usage: UsageCost | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.detail = detail
        self.usage = usage


def get_executor(component: str):
    if component in ("file_read", "file_write"):
        from pipyer.runner.components import file_io

        return file_io.execute_read if component == "file_read" else file_io.execute_write
    if component == "shell":
        from pipyer.runner.components.shell import execute as execute_shell

        return execute_shell
    if component == "python":
        from pipyer.runner.components.python_step import execute as execute_python

        return execute_python
    if component == "assertions":
        from pipyer.runner.components.assertions import execute as execute_assertions

        return execute_assertions
    if component in ("llm", "llm_judge"):
        from pipyer.runner.components.llm import execute as execute_llm

        return execute_llm
    raise KeyError(f"unknown component {component!r}")
