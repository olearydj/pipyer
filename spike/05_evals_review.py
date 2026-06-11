"""Spike 5: Pydantic Evals review (FR-006).

The 2 cases x 2 prompts x 2 model-alias scenario: does Pydantic Evals provide
first-class matrix semantics? Can usage be collected per combination?
Recommendation: native / integrate / defer.
"""

from __future__ import annotations

import inspect
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import _common as c
from pydantic import BaseModel


class Verdict(BaseModel):
    grade: str
    reasoning: str


def main() -> None:
    from pydantic_ai import Agent
    from pydantic_evals import Case, Dataset

    evidence: dict = {"spike": "05_evals_review"}

    # The matrix: 2 prompts x 2 "model aliases" (stub variants), 2 cases each.
    prompts = {
        "strict": "Grade strictly. Submission: {sub}",
        "lenient": "Grade kindly. Submission: {sub}",
    }
    aliases = {
        "grader_a": c.make_stub_model(custom_output_args={"grade": "B", "reasoning": "ok"}),
        "grader_b": c.make_stub_model(custom_output_args={"grade": "A", "reasoning": "great"}),
    }
    cases = [
        Case(name="add_fn", inputs="def add(a,b): return a+b"),
        Case(name="sub_fn", inputs="def sub(a,b): return a-b"),
    ]

    # Is there first-class matrix support? Inspect the API surface first.
    evidence["dataset_evaluate_signature"] = str(inspect.signature(Dataset.evaluate_sync))
    evidence["case_fields"] = [p for p in inspect.signature(Case.__init__).parameters][1:]

    # Run the matrix the only way the API allows: one evaluate call per combination.
    combos = {}
    for p_name, p_tmpl in prompts.items():
        for a_name, model in aliases.items():
            agent = Agent(model, output_type=Verdict)

            async def task(inputs: str, _agent=agent, _tmpl=p_tmpl) -> str:
                result = await _agent.run(_tmpl.format(sub=inputs))
                return result.output.grade

            dataset = Dataset(cases=cases)
            report = dataset.evaluate_sync(task)
            # What does the report expose per case - durations? usage? tokens?
            first = report.cases[0]
            combos[f"{p_name}/{a_name}"] = {
                "cases_run": len(report.cases),
                "report_case_attrs": sorted(a for a in vars(first) if not a.startswith("_"))[:15],
                "has_usage_on_case": any("usage" in a.lower() for a in vars(first)),
                "task_duration_present": hasattr(first, "task_duration"),
            }
    evidence["combos"] = combos
    evidence["observations"] = {
        "matrix_semantics": (
            "no first-class matrix: Dataset.evaluate binds ONE task; varying prompt or "
            "model means an outer loop constructing closures per combination - exactly the "
            "loop Pipyer's matrix expansion would own, with cell parameters as data"
        ),
        "matrix_params_attachment": (
            "report cases carry no cell parameters; attaching {prompt, model} per record "
            "is caller bookkeeping - Pipyer's StepResult.matrix field does this natively"
        ),
        "fit": (
            "Evals is case-level scoring (evaluators, LLMJudge) orthogonal to matrix "
            "execution; usable INSIDE an llm_judge step later without owning topology"
        ),
    }
    evidence["recommendation"] = (
        "defer: no matrix semantics to reuse; revisit post-v1 as an optional judge/eval "
        "engine invoked inside steps (composition, not reimplementation)"
    )

    path = c.write_evidence("05_evals_review.json", evidence)
    print(f"evidence → {path}")
    print(f"  combos run: {list(combos)}")
    print(f"  recommendation: {evidence['recommendation'][:60]}...")


if __name__ == "__main__":
    main()
