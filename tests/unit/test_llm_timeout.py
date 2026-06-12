"""timeout_s on LLM steps is a real wall-clock bound (review finding).

The previous form raised on timeout but then blocked at ThreadPoolExecutor
context exit until the hung call returned. The fix cancels the in-flight call
via asyncio.wait_for; this test hangs the model far longer than the timeout
and asserts the run finishes promptly with a recorded timeout failure.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
import time

from pydantic_ai.models.function import FunctionModel

from pipyer.runner import run_workflow

HANG_SECONDS = 60


async def _hung_model(messages, agent_info):  # noqa: ANN001 - pydantic_ai signature
    await asyncio.sleep(HANG_SECONDS)
    raise AssertionError("the hung call was never cancelled")


def test_llm_timeout_is_wall_clock(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("Judge this: {payload}\n")
    (tmp_path / "workflow.yaml").write_text(
        textwrap.dedent(
            """
            schema_version: "2"
            name: hung_call
            models:
              grader:
                model: anthropic:claude-haiku-4-5
            steps:
              - name: judge
                component: llm
                config:
                  model: grader
                  prompt: prompts/p.md
                  output_schema:
                    type: object
                    properties:
                      verdict: {type: string}
                    required: [verdict]
                  timeout_s: 1
                inputs:
                  payload: "hello"
            """
        )
    )

    started = time.monotonic()
    run = run_workflow(
        tmp_path / "workflow.yaml",
        results_dir=tmp_path / "runs",
        model_overrides={"grader": FunctionModel(_hung_model)},
    )
    elapsed = time.monotonic() - started

    assert elapsed < HANG_SECONDS / 4, f"run took {elapsed:.1f}s - timeout did not bound the call"
    assert run.record.totals["failed"] == 1
    events = [json.loads(line) for line in (run.run_dir / "events.jsonl").read_text().splitlines()]
    failures = [e for e in events if e.get("event") == "step_result" and e["status"] == "failure"]
    assert failures and failures[0]["error"]["category"] == "timeout"
