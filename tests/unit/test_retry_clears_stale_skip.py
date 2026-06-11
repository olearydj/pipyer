"""A unit retried to success must unblock its downstream (acceptance-run finding).

History that exposed it: step A failed → B skipped (R2). Resume with
--retry-failed: A succeeds, but B's prior-segment skip record (and A's prior
failure record) must not keep B blocked - the latest record wins, and the
success/failure/skipped states are mutually exclusive per unit.
"""

from __future__ import annotations

import json
import textwrap

from pipyer.runner import run_workflow


def _write_workflow(tmp_path, results_dir):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "flaky.py").write_text(
        textwrap.dedent(
            """
            import json, pathlib, sys
            inputs = json.load(sys.stdin)
            flag = pathlib.Path(inputs["flag_file"])
            if not flag.exists():
                sys.stderr.write("flag missing; failing this attempt\\n")
                raise SystemExit(1)
            print(json.dumps({"value": 42}))
            """
        )
    )
    (tmp_path / "scripts" / "consume.py").write_text(
        textwrap.dedent(
            """
            import json, sys
            inputs = json.load(sys.stdin)
            print(json.dumps({"doubled": inputs["upstream"]["value"] * 2}))
            """
        )
    )
    (tmp_path / "workflow.yaml").write_text(
        textwrap.dedent(
            f"""
            schema_version: "2"
            name: retry_unblocks
            inputs:
              flag_file:
                type: path
            settings:
              results_dir: {json.dumps(str(results_dir))}
            steps:
              - name: flaky
                component: python
                config:
                  script: scripts/flaky.py
                inputs:
                  flag_file: inputs.flag_file
              - name: consume
                component: python
                config:
                  script: scripts/consume.py
                inputs:
                  upstream: steps.flaky.output
            outputs:
              result: steps.consume.output
            """
        )
    )
    return tmp_path / "workflow.yaml"


def test_retried_success_unblocks_downstream(tmp_path):
    results_dir = tmp_path / "runs"
    flag = tmp_path / "flag"
    wf = _write_workflow(tmp_path, results_dir)

    first = run_workflow(wf, inputs={"flag_file": str(flag)}, results_dir=results_dir)
    assert first.status == "completed"
    assert first.record.totals["failed"] == 1  # flaky failed
    assert first.record.totals["skipped"] == 1  # consume skipped by policy

    flag.write_text("present")  # the operator fixed the world

    # Resume without the flag: failure carries over, downstream stays blocked.
    carried = run_workflow(
        wf, inputs={"flag_file": str(flag)}, results_dir=results_dir, resume=True
    )
    assert carried.record.totals["failed"] == 1
    assert carried.record.totals["succeeded"] == 0

    # Resume with retry: flaky succeeds and consume MUST run (the bug kept it
    # skipped on the stale prior-segment records).
    retried = run_workflow(
        wf, inputs={"flag_file": str(flag)}, results_dir=results_dir, resume=True, retry_failed=True
    )
    assert retried.status == "completed"
    assert retried.record.totals["failed"] == 0
    statuses = {}
    run_dir = results_dir / retried.run_id
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event.get("event") == "step_result":
            statuses[event["step"]] = event["status"]  # latest wins
    assert statuses["flaky"] == "success"
    assert statuses["consume"] == "success", "downstream stayed blocked behind a stale skip"
