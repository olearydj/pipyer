"""shell executor (R19; fixture 5).

Static argv only - inputs are delivered as JSON on stdin and PIPYER_INPUT_*
environment variables, never interpolated into the command. Nonzero exit is a
failure with exactly one attempt (side-effecting steps are not retried, R25);
TimeoutExpired maps to the timeout category.
"""

from __future__ import annotations

import json
from typing import Any

from pipyer.records.step_result import ErrorCategory
from pipyer.runner.components import StepFailure
from pipyer.runner.components._subproc import CaptureTimeout, run_captured


def _env_overlay(resolved_inputs: dict[str, Any]) -> dict[str, str]:
    overlay = {}
    for key, value in resolved_inputs.items():
        overlay[f"PIPYER_INPUT_{key.upper()}"] = (
            value if isinstance(value, str) else json.dumps(value)
        )
    return overlay


def execute(step, resolved_inputs: dict[str, Any], ctx, index) -> dict[str, Any]:
    import os

    env = {**os.environ, **_env_overlay(resolved_inputs)}
    try:
        proc = run_captured(
            step.config.command,
            input_text=json.dumps(resolved_inputs),
            cwd=ctx.workflow_dir,
            env=env,
            timeout_s=step.config.timeout_s,
        )
    except CaptureTimeout as error:
        raise StepFailure(
            ErrorCategory.TIMEOUT,
            f"command exceeded timeout_s={step.config.timeout_s} (process group killed)",
            detail={"command": step.config.command},
        ) from error
    stdout: Any = proc.stdout
    json_error: json.JSONDecodeError | None = None
    if step.config.parse_stdout == "json":
        try:
            stdout = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError as error:
            json_error = error
            stdout = proc.stdout  # keep raw text; a nonzero exit will say why
    if proc.exit_code != 0:
        raise StepFailure(
            ErrorCategory.NONZERO_EXIT,
            f"command exited {proc.exit_code}",
            detail={
                "exit_code": proc.exit_code,
                "stdout": stdout,
                "stderr": proc.stderr[-2000:],
                "stdout_truncated": proc.stdout_truncated,
                "stderr_truncated": proc.stderr_truncated,
            },
        )
    if json_error is not None:
        raise StepFailure(
            ErrorCategory.OUTPUT_VALIDATION_ERROR,
            "command stdout is not valid JSON",
            detail={"stdout": proc.stdout[-2000:], "stdout_truncated": proc.stdout_truncated},
        )
    return {
        "stdout": stdout,
        "stderr": proc.stderr,
        "exit_code": proc.exit_code,
        "stdout_truncated": proc.stdout_truncated,
        "stderr_truncated": proc.stderr_truncated,
    }
