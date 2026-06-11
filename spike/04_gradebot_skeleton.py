"""Spike 4: GradeBot skeleton - the boundary test (FR-005, SC-007).

3 simulated submissions, shell-simulated test execution, one structured feedback
call per item, per-item JSONL, one forced failure, interrupt + resume without
recomputing completed items. Question under test: does the substrate help with
anything OUTSIDE the per-item LLM call?

Usage:
  uv run --group spike python spike/04_gradebot_skeleton.py --interrupt-after 1
  uv run --group spike python spike/04_gradebot_skeleton.py --resume
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common as c
from pydantic import BaseModel

DEMO = c.RESULTS_DIR / "gradebot_demo"
EVENTS = DEMO / "events.jsonl"
CHECKPOINT = DEMO / "checkpoint.json"

SUBMISSIONS = {
    "alice.py": "def add(a, b):\n    return a + b\n",
    "bob.py": "def add(a, b)\n    return a + b\n",  # syntax error: the forced failure
    "carol.py": "def add(a, b):\n    return b + a\n",
}


class Feedback(BaseModel):
    score: int
    comments: str


def setup_submissions() -> list[Path]:
    subs = DEMO / "submissions"
    subs.mkdir(parents=True, exist_ok=True)
    for name, body in SUBMISSIONS.items():
        (subs / name).write_text(body)
    return sorted(subs.glob("*.py"))


def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text())
    return {"completed": {}}


def save_checkpoint(state: dict) -> None:
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(CHECKPOINT)  # atomic-rename convention per SPEC section 6


def append_event(record: dict) -> None:
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interrupt-after", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset or not args.resume:
        for f in (EVENTS, CHECKPOINT):
            f.unlink(missing_ok=True)

    from pydantic_ai import Agent

    agent = Agent(
        c.make_stub_model(custom_output_args={"score": 4, "comments": "clean and correct"}),
        output_type=Feedback,
        retries=2,
    )

    submissions = setup_submissions()
    state = load_checkpoint()
    run_id = state.get("run_id") or c.new_run_id("gradebot-skel")
    state["run_id"] = run_id
    computed_this_run = 0

    for index, sub in enumerate(submissions):
        # --- step: run_tests (shell) ---------------------------------------
        key = f"run_tests:{index}"
        ihash = c.input_hash(sub.read_text())
        if state["completed"].get(key) == ihash:
            test_ok = state.setdefault("test_ok", {}).get(str(index), True)
        else:
            started, t0 = c.timed()
            proc = subprocess.run(
                [sys.executable, "-c", f"compile(open({str(sub)!r}).read(), {sub.name!r}, 'exec')"],
                capture_output=True,
                text=True,
            )
            test_ok = proc.returncode == 0
            append_event(
                c.make_step_result(
                    run_id=run_id,
                    step="run_tests",
                    component="shell",
                    status="success" if test_ok else "failure",
                    output={"exit_code": proc.returncode} if test_ok else None,
                    error=None
                    if test_ok
                    else {
                        "category": "nonzero_exit",
                        "message": proc.stderr.strip()[:200] or f"exit {proc.returncode}",
                    },
                    item_index=index,
                    started_at=started,
                    duration_ms=c.ms_since(t0),
                    inputs=sub.read_text(),
                )
            )
            state["completed"][key] = ihash
            state.setdefault("test_ok", {})[str(index)] = test_ok
            computed_this_run += 1

        # --- step: grade (llm), skipped when tests failed -------------------
        key = f"grade:{index}"
        if not test_ok:
            if state["completed"].get(key) != "skipped":
                append_event(
                    c.make_step_result(
                        run_id=run_id,
                        step="grade",
                        component="llm",
                        status="skipped",
                        error={
                            "category": "upstream_failure",
                            "message": f"run_tests failed for item {index} ({sub.name})",
                        },
                        item_index=index,
                        started_at=c.now_iso(),
                        duration_ms=0,
                        inputs=sub.name,
                    )
                )
                state["completed"][key] = "skipped"
        elif state["completed"].get(key) != c.input_hash(sub.read_text()):
            started, t0 = c.timed()
            result = agent.run_sync(f"Grade this submission:\n{sub.read_text()}")
            append_event(
                c.make_step_result(
                    run_id=run_id,
                    step="grade",
                    component="llm",
                    status="success",
                    output=result.output.model_dump(),
                    usage=c.usage_to_cost_fields("stub:testmodel", result.usage, "estimated"),
                    item_index=index,
                    started_at=started,
                    duration_ms=c.ms_since(t0),
                    inputs=sub.read_text(),
                )
            )
            state["completed"][key] = c.input_hash(sub.read_text())
            computed_this_run += 1

        save_checkpoint(state)
        if args.interrupt_after is not None and index + 1 >= args.interrupt_after:
            print(f"INTERRUPTED after item {index} (simulated); resume with --resume")
            sys.exit(3)

    # Summary evidence.
    events = [json.loads(line) for line in EVENTS.read_text().splitlines()]
    summary = {
        "spike": "04_gradebot_skeleton",
        "items": len(submissions),
        "events": len(events),
        "statuses": {
            s: sum(1 for e in events if e["status"] == s) for s in ("success", "failure", "skipped")
        },
        "computed_this_run": computed_this_run,
        "boundary_observation": (
            "the substrate was used strictly inside the per-item grade call; each/iteration, "
            "checkpointing, JSONL evidence, skip policy, and resume were ~60 lines of plain "
            "code the substrate offered nothing for - supporting the standalone-runner "
            "hypothesis boundary"
        ),
    }
    c.write_evidence("04_gradebot_skeleton.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
