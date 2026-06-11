"""python executor (R19).

Subprocess isolation: `sys.executable <script>` with inputs as JSON on stdin
and output as JSON on stdout. The subprocess is the kill boundary that makes
timeout_s enforceable and keeps user code out of the runner process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from pipyer.records.step_result import ErrorCategory
from pipyer.runner.components import StepFailure


def execute(step, resolved_inputs: dict[str, Any], ctx, index) -> dict[str, Any]:
    script = ctx.workflow_dir / step.config.script
    if not script.is_file():
        raise StepFailure(ErrorCategory.UNCLASSIFIED, f"script not found: {script}")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(resolved_inputs),
            capture_output=True,
            text=True,
            cwd=ctx.workflow_dir,
            timeout=step.config.timeout_s,
        )
    except subprocess.TimeoutExpired as error:
        raise StepFailure(
            ErrorCategory.TIMEOUT,
            f"script exceeded timeout_s={step.config.timeout_s}",
            detail={"script": str(script)},
        ) from error
    if proc.returncode != 0:
        raise StepFailure(
            ErrorCategory.NONZERO_EXIT,
            f"script exited {proc.returncode}",
            detail={"script": str(script), "stderr": proc.stderr[-2000:]},
        )
    try:
        output = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError as error:
        raise StepFailure(
            ErrorCategory.OUTPUT_VALIDATION_ERROR,
            "script stdout is not valid JSON",
            detail={"stdout": proc.stdout[-2000:]},
        ) from error
    return {"output": output}
