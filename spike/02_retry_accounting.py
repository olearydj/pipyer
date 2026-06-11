"""Spike 2: retry accounting (FR-002).

Are internal validation retries bounded, countable, visible? Can they silently
multiply with runner-level retries? Deterministic stub throughout - the
accounting mechanics are model-independent.
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import _common as c
from pydantic import BaseModel


class Verdict(BaseModel):
    grade: str


def build_agent(retries: int, fail_first_n: int):
    """Agent whose output validator rejects the first `fail_first_n` attempts."""
    from pydantic_ai import Agent, ModelRetry

    agent = Agent(
        c.make_stub_model(custom_output_args={"grade": "B"}),
        output_type=Verdict,
        retries=retries,
    )
    calls = {"n": 0}

    @agent.output_validator
    def gate(output: Verdict) -> Verdict:
        calls["n"] += 1
        if calls["n"] <= fail_first_n:
            raise ModelRetry(f"spike-forced rejection #{calls['n']}")
        return output

    return agent, calls


def main() -> None:
    from pydantic_ai import capture_run_messages
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    from pydantic_ai.messages import RetryPromptPart

    evidence: dict = {"spike": "02_retry_accounting"}

    # Case A: bounded and visible - fail once, succeed on attempt 2 (retries=2).
    agent, calls = build_agent(retries=2, fail_first_n=1)
    with capture_run_messages() as messages:
        result = agent.run_sync("grade it")
    retry_parts = sum(
        1 for m in messages for p in getattr(m, "parts", []) if isinstance(p, RetryPromptPart)
    )
    evidence["bounded_visible"] = {
        "validator_calls": calls["n"],
        "retry_prompt_parts_in_transcript": retry_parts,
        "usage_requests": result.usage.requests,
        "conclusion": "attempts countable via usage.requests, transcript, and validator hook",
    }

    # Case B: exhaustion - always fail, retries=2 → bounded at retries+1 attempts.
    agent, calls = build_agent(retries=2, fail_first_n=99)
    try:
        with capture_run_messages() as messages:
            agent.run_sync("grade it")
        evidence["exhaustion"] = "UNEXPECTED: run succeeded"
    except UnexpectedModelBehavior as e:
        evidence["exhaustion"] = {
            "exception": type(e).__name__,
            "message": str(e),
            "validator_calls": calls["n"],
            "bound_honored": calls["n"] == 3,  # retries=2 → 3 attempts total
        }

    # Case C: runner-level retries layered outside - no silent multiplication.
    runner_attempts, per_run_validator_calls = 2, []
    for _attempt in range(runner_attempts):
        agent, calls = build_agent(retries=2, fail_first_n=99)
        try:
            agent.run_sync("grade it")
        except UnexpectedModelBehavior:
            pass
        per_run_validator_calls.append(calls["n"])
    evidence["layered"] = {
        "runner_attempts": runner_attempts,
        "internal_attempts_per_run": per_run_validator_calls,
        "total_model_calls": sum(per_run_validator_calls),
        "conclusion": (
            "total = runner_attempts x (retries+1), both bounds explicit and observable; "
            "the substrate performs no hidden transport retries (tenacity transport is "
            "opt-in via pydantic_ai.retries), so layers cannot silently multiply"
        ),
    }

    path = c.write_evidence("02_retry_accounting.json", evidence)
    print(f"evidence → {path}")
    print(f"  bounded_visible: {evidence['bounded_visible']}")
    print(f"  exhaustion bound honored: {evidence['exhaustion']['bound_honored']}")
    print(f"  layered total calls: {evidence['layered']['total_model_calls']}")


if __name__ == "__main__":
    main()
