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


def test_retried_each_expansion_clears_stale_scalar_skip(tmp_path):
    results_dir = tmp_path / "runs"
    flag = tmp_path / "flag"
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "collect.py").write_text(
        textwrap.dedent(
            """
            import json, pathlib, sys
            inputs = json.load(sys.stdin)
            if not pathlib.Path(inputs["flag_file"]).exists():
                raise SystemExit(1)
            print(json.dumps({"items": [1, 2]}))
            """
        )
    )
    (tmp_path / "scripts" / "item.py").write_text(
        "import json, sys\n"
        "inputs = json.load(sys.stdin)\n"
        "print(json.dumps({'value': inputs['x']}))\n"
    )
    (tmp_path / "scripts" / "consume.py").write_text(
        textwrap.dedent(
            """
            import json, sys
            rows = json.load(sys.stdin)["rows"]
            if len(rows) != 2 or any(row is None for row in rows):
                raise SystemExit(1)
            print(json.dumps({"count": len(rows)}))
            """
        )
    )
    wf = tmp_path / "workflow.yaml"
    wf.write_text(
        textwrap.dedent(
            f"""
            schema_version: "2"
            name: retry_each_skip
            inputs:
              flag_file:
                type: path
            settings:
              results_dir: {json.dumps(str(results_dir))}
            steps:
              - name: collect
                component: python
                config:
                  script: scripts/collect.py
                inputs:
                  flag_file: inputs.flag_file
              - name: expand
                component: python
                each: steps.collect.output.items
                config:
                  script: scripts/item.py
                inputs:
                  x: item
              - name: consume
                component: python
                config:
                  script: scripts/consume.py
                inputs:
                  rows: steps.expand.output
            outputs:
              result: steps.consume.output
            """
        )
    )

    first = run_workflow(wf, inputs={"flag_file": str(flag)}, results_dir=results_dir)
    assert first.record.totals["failed"] == 1
    assert first.record.totals["skipped"] == 2

    flag.write_text("present")
    retried = run_workflow(
        wf, inputs={"flag_file": str(flag)}, results_dir=results_dir, resume=True, retry_failed=True
    )
    statuses = {
        (event["step"], event.get("item_index")): event["status"]
        for event in retried.events
        if event.get("event") == "step_result"
    }
    assert statuses[("expand", 0)] == "success"
    assert statuses[("expand", 1)] == "success"
    assert statuses[("consume", None)] == "success"


def test_each_expansion_failure_carries_over_without_retry_failed(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "item.py").write_text(
        "import json, sys\nprint(json.dumps({'value': json.load(sys.stdin)['x']}))\n"
    )
    wf = tmp_path / "workflow.yaml"
    wf.write_text(
        textwrap.dedent(
            """
            schema_version: "2"
            name: retry_each_failure
            inputs:
              items:
                type: json
            steps:
              - name: expand
                component: python
                each: inputs.items
                config:
                  script: scripts/item.py
                inputs:
                  x: item
            """
        )
    )
    results_dir = tmp_path / "runs"

    first = run_workflow(wf, inputs={"items": "not-a-list"}, results_dir=results_dir)
    assert first.record.totals["failed"] == 1

    carried = run_workflow(wf, inputs={"items": [1]}, results_dir=results_dir, resume=True)
    assert carried.record.totals["failed"] == 1
    boundary = next(event for event in carried.events if event.get("event") == "run_resumed")
    after_boundary = carried.events[carried.events.index(boundary) :]
    assert not [
        event
        for event in after_boundary
        if event.get("event") == "step_result" and event.get("step") == "expand"
    ]
