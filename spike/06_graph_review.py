"""Spike 6: graph and durable execution review (FR-007).

Model a fixed two-step workflow as a pydantic-graph graph; inspect state
representation; check node-output → StepResult mapping and whether durable
execution supports deterministic item-level resume.
Recommendation: use / ignore for v1 / revisit later.
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common as c


def main() -> None:
    evidence: dict = {"spike": "06_graph_review"}

    # Primary finding first: import-time deprecation status of the machinery.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from pydantic_graph import BaseNode, End, Graph, GraphRunContext
        from pydantic_graph.persistence.file import FileStatePersistence
    evidence["deprecation_warnings"] = [str(w.message)[:300] for w in caught]

    @dataclass
    class State:
        test_output: str = ""
        grade: str = ""

    @dataclass
    class RunTests(BaseNode[State]):
        async def run(self, ctx: GraphRunContext[State]) -> Grade:
            ctx.state.test_output = "2 passed"
            return Grade()

    @dataclass
    class Grade(BaseNode[State, None, str]):
        async def run(self, ctx: GraphRunContext[State]) -> End[str]:
            ctx.state.grade = f"B ({ctx.state.test_output})"
            return End(ctx.state.grade)

    graph = Graph(nodes=(RunTests, Grade))

    # Durable execution: run with file persistence, then inspect the snapshots.
    persist_path = c.RESULTS_DIR / "06_graph_state.json"
    persist_path.parent.mkdir(parents=True, exist_ok=True)
    persist_path.unlink(missing_ok=True)
    persistence = FileStatePersistence(persist_path)

    result = graph.run_sync(RunTests(), state=State(), persistence=persistence)
    snapshots = json.loads(persist_path.read_text())
    evidence["run_output"] = result.output
    evidence["snapshot_count"] = len(snapshots)
    evidence["snapshot_keys"] = sorted(snapshots[0].keys()) if snapshots else []
    evidence["snapshot_sample"] = snapshots[0] if snapshots else None

    evidence["observations"] = {
        "step_result_mapping": (
            "snapshots are (node, whole-state, status, timestamps) - node-centric state "
            "checkpoints, not per-step results: no per-node output/error/usage/cost fields; "
            "mapping to StepResult would mean reconstructing outputs from state diffs"
        ),
        "item_level_resume": (
            "persistence resumes at node granularity; item-level resume would require one "
            "node per item, i.e. node count derived from input data at runtime - dynamic "
            "graph construction, colliding with workflows-are-data (ADR-004) and "
            "deterministic topology (Principle II)"
        ),
        "topology_authority": (
            "edges live in code (run() return type annotations) - the graph IS a program, "
            "the exact artifact shape ADR-004 rejects for workflow files"
        ),
        "lifecycle": (
            "the BaseNode Graph runner and its persistence machinery are deprecated for "
            "removal/repurposing in pydantic-graph v2 (GraphBuilder replaces it) - building "
            "the runner on it would chain Pipyer's core to an API scheduled to vanish"
        ),
    }
    evidence["recommendation"] = (
        "ignore for v1: wrong granularity for StepResult, no item-level resume without "
        "data-driven topology, and the machinery is deprecated mid-replacement; revisit "
        "only if GraphBuilder v2 someday offers item-level durable semantics worth wrapping"
    )

    path = c.write_evidence("06_graph_review.json", evidence)
    print(f"evidence → {path}")
    print(f"  deprecation warnings: {len(evidence['deprecation_warnings'])}")
    print(f"  snapshots: {evidence['snapshot_count']} keys={evidence['snapshot_keys']}")
    print("  recommendation: ignore for v1")


if __name__ == "__main__":
    main()
