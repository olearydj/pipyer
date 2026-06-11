# Contract: `pipyer run`

```text
pipyer run WORKFLOW [--input k=v]... [--resume RUN_ID|last] [--retry-failed]
           [--dry-run] [--results-dir PATH] [--json]
```

| Flag | Semantics |
|------|-----------|
| `--input k=v` | Repeatable. `k` must be a declared workflow input; `v` parses as a YAML scalar. Unknown key or missing required input → exit 2 before any run directory exists. |
| `--resume RUN_ID\|last` | Resume the named run, or the lexically last run id under the results dir. No prior run → exit 2 with a clear error (never a fresh silent run). |
| `--retry-failed` | Re-execute prior failed items. Requires `--resume`; otherwise exit 2. |
| `--dry-run` | Exactly `pipyer validate WORKFLOW` - the same `validate_file()` call and exit codes; no run directory, no preflight. |
| `--results-dir PATH` | Overrides `settings.results_dir`; recorded in the config snapshot. |
| `--json` | Emit the `RunRecord` as JSON to stdout (human summary suppressed). |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | run completed; all units succeeded or were policy-skipped within budget and no step failure remains unresolved |
| 1 | run reached a terminal state with failures: budget halt, or completed with failed items |
| 2 | pre-run error: validation failure, secrets preflight failure, lock conflict, usage error, missing prior run |
| 130 | interrupted (SIGINT) - run directory remains resumable |

## Output

Human mode prints: run id, run directory, terminal status, totals line, cost total, and the summary path. Failure-budget halts print the halt reason. `--json` prints the `RunRecord` only. Secret values never appear in any output; provider names may.

## Signals

SIGINT triggers a graceful interruption: in-flight units finish or are recorded `interrupted`, the checkpoint is flushed, status is `interrupted`, exit 130. A second SIGINT exits immediately (the log's corrupt-trailing-line recovery covers the torn-write case).
