"""python executor (R19).

Subprocess isolation: `sys.executable <script>` with inputs as JSON on stdin
and output as JSON on stdout. The subprocess is the kill boundary that makes
timeout_s enforceable and keeps user code out of the runner process.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pipyer.records.step_result import ErrorCategory
from pipyer.runner.components import StepFailure
from pipyer.runner.components._subproc import CaptureTimeout, run_captured


def execute(step, resolved_inputs: dict[str, Any], ctx, index) -> dict[str, Any]:
    script = ctx.workflow_dir / step.config.script
    if not script.is_file():
        raise StepFailure(ErrorCategory.UNCLASSIFIED, f"script not found: {script}")
    try:
        proc = run_captured(
            [sys.executable, str(script)],
            input_text=json.dumps(resolved_inputs),
            cwd=ctx.workflow_dir,
            timeout_s=step.config.timeout_s,
        )
    except CaptureTimeout as error:
        raise StepFailure(
            ErrorCategory.TIMEOUT,
            f"script exceeded timeout_s={step.config.timeout_s} (process group killed)",
            detail={"script": str(script)},
        ) from error
    if proc.exit_code != 0:
        raise StepFailure(
            ErrorCategory.NONZERO_EXIT,
            f"script exited {proc.exit_code}",
            detail={
                "script": str(script),
                "stderr": proc.stderr[-2000:],
                "stderr_truncated": proc.stderr_truncated,
            },
        )
    try:
        output = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError as error:
        raise StepFailure(
            ErrorCategory.OUTPUT_VALIDATION_ERROR,
            "script stdout is not valid JSON",
            detail={"stdout": proc.stdout[-2000:], "stdout_truncated": proc.stdout_truncated},
        ) from error
    return {"output": output}
