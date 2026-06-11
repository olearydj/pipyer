"""Spike 3: error shapes (FR-003).

What do failures look like after retry exhaustion, transport failure, and rate
limiting? Map each observed shape to the R8 taxonomy; flag what the taxonomy
cannot represent honestly.
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import _common as c
from pydantic import BaseModel


class Verdict(BaseModel):
    grade: str


def shape(e: BaseException) -> dict:
    return {
        "type": type(e).__name__,
        "mro": [k.__name__ for k in type(e).__mro__[:4]],
        "message": str(e)[:300],
        "attrs": {
            k: repr(getattr(e, k))[:120]
            for k in ("status_code", "model_name", "body")
            if hasattr(e, k)
        },
    }


def main() -> None:
    from pydantic_ai import Agent, ModelRetry
    from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
    from pydantic_ai.messages import ModelMessage, ModelResponse
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    evidence: dict = {"spike": "03_error_shapes", "shapes": {}}

    # Shape 1: validation-retry exhaustion → taxonomy: output_validation_error
    agent = Agent(
        c.make_stub_model(custom_output_args={"grade": "B"}), output_type=Verdict, retries=1
    )

    @agent.output_validator
    def always_reject(output: Verdict) -> Verdict:
        raise ModelRetry("spike-forced permanent rejection")

    try:
        agent.run_sync("grade")
    except UnexpectedModelBehavior as e:
        evidence["shapes"]["retry_exhaustion"] = {
            **shape(e),
            "taxonomy": "output_validation_error",
        }

    # Shape 2: transport failure (unreachable endpoint) → taxonomy: transport_error
    # Uses the Anthropic model class against a dead local port - no live network needed.
    try:
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        dead = AnthropicModel(
            "claude-haiku-4-5",
            provider=AnthropicProvider(base_url="http://127.0.0.1:9", api_key="spike-dummy"),
        )
        try:
            Agent(dead, output_type=Verdict, retries=0).run_sync("grade")
            evidence["shapes"]["transport"] = "UNEXPECTED: succeeded against dead endpoint"
        except Exception as e:
            evidence["shapes"]["transport"] = {**shape(e), "taxonomy": "transport_error"}
    except ImportError as e:
        evidence["shapes"]["transport"] = f"leg unavailable: {e}"

    # Shape 3: rate limiting → taxonomy: rate_limited
    # Simulated by a model raising the provider's 429 shape; live confirmation is a
    # one-line rerun against the hosted leg outside the sandbox.
    def rate_limited_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(
            status_code=429,
            model_name="sim:rate-limit",
            body={"error": {"type": "rate_limit_error"}},
        )

    try:
        Agent(FunctionModel(rate_limited_model), output_type=Verdict, retries=2).run_sync("grade")
        evidence["shapes"]["rate_limited"] = "UNEXPECTED: succeeded"
    except ModelHTTPError as e:
        evidence["shapes"]["rate_limited"] = {
            **shape(e),
            "taxonomy": "rate_limited",
            "note": (
                "propagated immediately despite retries=2: Agent retries cover output "
                "validation only; HTTP-level retry is opt-in (pydantic_ai.retries tenacity "
                "transport) - runner owns transport retry policy, confirming the boundary"
            ),
        }

    # Taxonomy gap scan: substrate failure types with no obvious R8 home.
    import pydantic_ai.exceptions as ex

    evidence["taxonomy_gap_candidates"] = {
        "ContentFilterError": "provider refused content - candidate new category or "
        "provider_error; flagged for 001b",
        "IncompleteToolCall": "truncated structured output (length limits) - maps to "
        "output_validation_error or provider_error; flagged for 001b",
        "FallbackExceptionGroup": "only with FallbackModel (multi-provider) - out of v1 scope",
        "all_public_exceptions": sorted(
            n for n in dir(ex) if n[0].isupper() and n not in ("Any", "TYPE_CHECKING")
        ),
    }

    path = c.write_evidence("03_error_shapes.json", evidence)
    print(f"evidence → {path}")
    for name, s in evidence["shapes"].items():
        print(f"  {name}: {s['type'] if isinstance(s, dict) else s}")


if __name__ == "__main__":
    main()
