"""file_read / file_write executors (FR-007).

Reads resolve relative paths against the workflow directory (the workflow
authors against its own tree); writes resolve relative paths under the run's
outputs/ directory (run-directory contract) and are atomic and idempotent -
full content, temp + rename - so a rerun produces the same bytes, and resume
reruns a write only when its input hash changed (R5, engine-level).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pipyer.records.step_result import ErrorCategory
from pipyer.runner.components import StepFailure


def _read_path(raw: str, workflow_dir: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else workflow_dir / path


def _write_path(raw: str, outputs_dir: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else outputs_dir / path


def execute_read(step, resolved_inputs: dict[str, Any], ctx, index) -> dict[str, Any]:
    raw = ctx.resolve(step.config.path, index=index, each_ref=step.each)
    path = _read_path(str(raw), ctx.workflow_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise StepFailure(
            ErrorCategory.UNCLASSIFIED, f"cannot read {path}: {error}", detail=str(error)
        ) from error
    if step.config.format == "json":
        return {"content": json.loads(text)}
    if step.config.format == "jsonl":
        return {"content": [json.loads(line) for line in text.splitlines() if line.strip()]}
    return {"content": text}


def execute_write(step, resolved_inputs: dict[str, Any], ctx, index) -> dict[str, Any]:
    raw = ctx.resolve(step.config.path, index=index, each_ref=step.each)
    path = _write_path(str(raw), ctx.run_dir / "outputs")
    content = resolved_inputs.get("content")
    if step.config.format in ("text", "markdown"):
        payload = content if isinstance(content, str) else json.dumps(content, indent=2)
    elif step.config.format == "json":
        payload = json.dumps(content, indent=2, sort_keys=True)
    else:  # jsonl
        rows = content if isinstance(content, list) else [content]
        payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError as error:
        raise StepFailure(
            ErrorCategory.UNCLASSIFIED, f"cannot write {path}: {error}", detail=str(error)
        ) from error
    return {"path": str(path), "bytes": len(payload.encode("utf-8"))}
