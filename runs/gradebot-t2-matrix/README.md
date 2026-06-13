# GradeBot T2 Matrix Evidence

This directory holds reproducible Sprint 03 evidence harnesses for GradeBot T2
matrix runs. Generated archives are local and gitignored; the scripts and this
README are the committed surface.

## Scripts

- `compare-existing.sh`: zero-spend comparison of two existing GradeBot T2 run
  archives. Defaults compare the retained `20260611-210517-6a8fb0` and
  `20260613-123418-6a8fb0` archives.
- `smoke-current.sh`: zero-spend matrix smoke run using the PII-free
  `tests/fixtures/gradebot_t2_smoke` corpus and two duplicate `test` model
  cells. It then compares `cell[0]` with `cell[1]`, exercising duplicate-cell
  index disambiguation.
- `run-current.sh`: live acceptance run for the archived T2 corpus. It stages
  the current GradeBot workflow, injects the requested model matrix, validates,
  optionally dry-runs, runs, and writes comparison artifacts outside the raw
  Pipyer run directory.

## Live Matrix Defaults

`run-current.sh` defaults to:

```bash
BASELINE_MODEL=anthropic:claude-sonnet-4-5-20250929
CANDIDATE_MODEL=anthropic:claude-sonnet-4-6
```

Override the full matrix with `MODEL_MATRIX`, comma-separated:

```bash
MODEL_MATRIX=anthropic:claude-sonnet-4-5-20250929,anthropic:claude-sonnet-4-6 ./runs/gradebot-t2-matrix/run-current.sh
```

or add extra cells with `EXTRA_MODELS`, also comma-separated. The script prompts
before live spend unless `--yes` is supplied.

Each archive keeps:

- `artifacts/run/`: the raw Pipyer run, unchanged.
- `artifacts/comparison/`: `pipyer compare` outputs.
- `commands.md` and `transcript.log`: exact commands and captured output.
- `manifest.json`: machine-readable provenance, matrix cells, event counts, and
  comparison summaries.
- `inputs/`: current workflow source, Git state, and sprint/source docs.
