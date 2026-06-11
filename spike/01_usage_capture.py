"""Spike 1: usage capture (FR-001).

Can token counts and cost inputs be captured per call into a StepResult shape,
including on validation-retry paths? Legs: deterministic stub, hosted, local.
Each leg records evidence or its unavailability reason - never silence.
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import _common as c
from pydantic import BaseModel


class Feedback(BaseModel):
    score: int
    comments: str


def probe_leg(leg_name: str, model, model_label: str, counts_source: str) -> list[dict]:
    from pydantic_ai import Agent, ModelRetry

    records = []
    run_id = c.new_run_id(f"usage-{leg_name}")

    # Clean path: one structured call, capture usage.
    agent = Agent(model, output_type=Feedback, retries=2)
    started, t0 = c.timed()
    result = agent.run_sync("Grade this submission: print('hello')")
    usage = result.usage
    records.append(
        c.make_step_result(
            run_id=run_id,
            step="grade_clean",
            component="llm",
            status="success",
            output=result.output.model_dump(),
            usage=c.usage_to_cost_fields(model_label, usage, counts_source),
            started_at=started,
            duration_ms=c.ms_since(t0),
            inputs={"path": "clean"},
        )
    )

    # Validation-retry path: output validator rejects the first attempt.
    retry_agent = Agent(model, output_type=Feedback, retries=2)
    calls = {"n": 0}

    @retry_agent.output_validator
    def reject_first(output: Feedback) -> Feedback:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelRetry("first attempt rejected by validator (spike-forced)")
        return output

    started, t0 = c.timed()
    result = retry_agent.run_sync("Grade this submission: print('hello')")
    usage = result.usage
    fields = c.usage_to_cost_fields(model_label, usage, counts_source)
    fields["validator_calls_observed"] = calls["n"]
    records.append(
        c.make_step_result(
            run_id=run_id,
            step="grade_retry_path",
            component="llm",
            status="success",
            output=result.output.model_dump(),
            usage=fields,
            started_at=started,
            duration_ms=c.ms_since(t0),
            inputs={"path": "retry"},
        )
    )

    # Cost inputs: genai-prices ships with pydantic-ai; record what it can do.
    try:
        from genai_prices import calc_price

        price = calc_price(usage, model_ref=model_label.split(":")[-1])
        records.append(
            {
                "leg": leg_name,
                "genai_prices": {
                    "total_price": str(price.total_price),
                    "input_price": str(price.input_price),
                    "output_price": str(price.output_price),
                    "model": getattr(price.model, "name", None),
                    "auto_update_active": None,
                },
            }
        )
    except Exception as e:  # stub/local models have no price table entries - that is evidence
        records.append({"leg": leg_name, "genai_prices": f"unavailable: {type(e).__name__}: {e}"})
    return records


def main() -> None:
    evidence: dict = {"spike": "01_usage_capture", "pydantic_ai": None, "legs": {}}
    import pydantic_ai

    evidence["pydantic_ai"] = pydantic_ai.__version__

    # Stub leg - always available.
    stub = c.make_stub_model(custom_output_args={"score": 4, "comments": "solid"})
    evidence["legs"]["stub"] = probe_leg("stub", stub, "stub:testmodel", "estimated")

    # Hosted leg.
    hosted = c.hosted_model_name()
    if hosted:
        name, via = hosted
        try:
            evidence["legs"]["hosted"] = probe_leg("hosted", name, name, "provider_reported")
            evidence["hosted_secret_provider"] = via
        except Exception as e:
            evidence["legs"]["hosted"] = f"FAILED: {type(e).__name__}: {e}"
    else:
        evidence["legs"]["hosted"] = "unavailable: no ANTHROPIC_API_KEY via op/env chain"

    # Local leg (Ollama via OpenAI-compatible provider).
    tag = c.ollama_available_model()
    if tag:
        try:
            model = c.make_ollama_model(tag)
            evidence["legs"]["local"] = probe_leg("local", model, f"ollama:{tag}", "estimated")
        except Exception as e:
            evidence["legs"]["local"] = f"FAILED: {type(e).__name__}: {e}"
    else:
        evidence["legs"]["local"] = "unavailable: Ollama not reachable"

    path = c.write_evidence("01_usage_capture.json", evidence)
    print(f"evidence → {path}")
    for leg, result in evidence["legs"].items():
        status = "ok" if isinstance(result, list) else result
        print(f"  {leg}: {status if isinstance(status, str) else 'captured'}")


if __name__ == "__main__":
    main()
