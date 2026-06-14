# DEMA Adjudication Matrix Evidence

This directory holds reproducible Sprint 03 evidence harnesses for running DEMA
through Pipyer. Generated archives are local and gitignored; the scripts and
this README are the committed surface.

## Scripts

- `smoke-current.sh`: zero-spend smoke using DEMA's `adjudicator_stub` route and
  two confidence-threshold cells. It runs `triage`, `adjudicate`, `cluster`, and
  `eval`, then compares `cell[0]` with `cell[1]`.
- `run-current.sh`: live matrix run from the current repo state. It stages the
  workflow, injects route and confidence-threshold matrices, validates, optionally
  dry-runs, runs, archives raw Pipyer and DEMA artifacts, and writes comparison
  artifacts outside the raw run directory.

## Live Defaults

`run-current.sh` defaults to a 2x2 matrix:

```bash
ROUTE_MATRIX=adjudicator_openai,adjudicator_claude
CONFIDENCE_MATRIX=0.60,0.70
MAX_PAIRS=16
```

The DEMA repository defaults to `/Volumes/Casa/dev/dema-llm`. Override it with
`DEMA_REPO` if needed. The script prompts before live spend unless `--yes` is
supplied.

Each archive keeps:

- `artifacts/run/`: the raw Pipyer run, unchanged.
- `artifacts/dema/`: DEMA side-effect outputs produced by the workflow wrapper.
- `artifacts/comparison/`: `pipyer compare` outputs.
- `commands.md` and `transcript.log`: exact commands and captured output.
- `manifest.json`: machine-readable provenance, matrix cells, event counts, and
  DEMA eval metrics.
- `inputs/`: Pipyer workflow source, Pipyer Git state, and DEMA Git/input
  snapshots used by the run.
