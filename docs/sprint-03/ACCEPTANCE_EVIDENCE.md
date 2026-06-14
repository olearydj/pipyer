# Sprint 03 Acceptance Evidence

This note records the GradeBot rehearsal leg and DEMA acceptance leg for Sprint
03 matrix execution and run comparison. The raw archives are local and
gitignored because they may contain closed-course outputs, student identifiers,
or provider logs; this document keeps only aggregate, decision-grade facts.

## GradeBot T2 Matrix Rehearsal

Archive:

- Local archive: `runs/gradebot-t2-matrix/20260613-220206-12e3eb/`
- Raw run: `runs/gradebot-t2-matrix/20260613-220206-12e3eb/artifacts/run/`
- Cell comparison: `runs/gradebot-t2-matrix/20260613-220206-12e3eb/artifacts/comparison/cell0-vs-cell1/`
- Run ID: `20260613-220206-12e3eb`
- Workflow: `gradebot_t2_matrix`
- Workflow hash: `sha256:12e3ebb29b6d094a95250cc7d3626e208a522ca43f8d366c928d586145968abe`
- Live run launched from commit: `2394aaf4f2cc07bb6cb8eef17bbacb35149aab4b`
- Comparison artifact regenerated after metadata fix: `776e4637b5c547ba2410f2c954c2b0826b9d281f`

Matrix cells:

| Cell | Grader model |
|------|--------------|
| `cell[0]` | `anthropic:claude-sonnet-4-5-20250929` |
| `cell[1]` | `anthropic:claude-sonnet-4-6` |

Run totals:

| Status | Attempted | Succeeded | Failed | Skipped | Not attempted |
|--------|-----------|-----------|--------|---------|---------------|
| completed | 1118 | 1108 | 10 | 20 | 0 |

The 10 failures were deterministic `run_tests` timeouts: the same 5 item indexes in each
cell. They stayed under the cell-local failure budget and produced the expected upstream
skips for grading and feedback.

Cost:

| Model | Calls | Input tokens | Output tokens | Estimated cost |
|-------|-------|--------------|---------------|----------------|
| `claude-sonnet-4-5-20250929` | 183 | 351539 | 40733 | `$1.665612` |
| `claude-sonnet-4-6` | 183 | 351722 | 42494 | `$1.692576` |
| Total | 366 | 703261 | 83227 | `$3.358188` |

Comparison summary:

| Metric | `claude-sonnet-4-5-20250929` | `claude-sonnet-4-6` | Delta |
|--------|------------------------------|---------------------|-------|
| Entries | 188 | 188 | 0 |
| Graded | 183 | 183 | 0 |
| Raw v2 exact match rate | 0.8907 | 0.7978 | -0.0929 |
| Published exact match rate | 0.8689 | 0.8087 | -0.0602 |
| Agrees | 159 | 148 | -11 |
| Expected human correction | 9 | 7 | -2 |
| Unexplained | 15 | 28 | +13 |
| Unexplained rate | 0.082 | 0.153 | +0.071 |
| Unexplained above floor | 0.065 | 0.136 | +0.071 |

Run-to-run comparison counts:

| Same units | Different units | Only left | Only right |
|------------|-----------------|-----------|------------|
| 323 | 246 | 0 | 0 |

Cost and latency deltas from `pipyer compare`:

| Metric | Delta, candidate minus baseline |
|--------|---------------------------------|
| Calls | 0 |
| Input tokens | +183 |
| Output tokens | +1761 |
| Estimated cost | `$0.026964` |
| Latency | +66511 ms |

## GradeBot Decision

The matrix machinery is validated by this rehearsal: both cells completed in one logical
run, per-cell failure budgets behaved correctly, matrix cost aggregation appeared in the
run summary, and `pipyer compare` produced archive-stable markdown and JSON artifacts from
the event log.

For the GradeBot fall model-upgrade question, `claude-sonnet-4-6` should not replace the
pinned `claude-sonnet-4-5-20250929` on the basis of this corpus. The candidate is only
slightly more expensive, but it has materially worse agreement against both baselines and
nearly doubles the unexplained rate.

## DEMA Matrix Acceptance

Archive:

- Local archive: `runs/dema-adjudication-matrix/20260614-150009-07db9e/`
- Raw run: `runs/dema-adjudication-matrix/20260614-150009-07db9e/artifacts/run/`
- Comparison artifacts:
  `runs/dema-adjudication-matrix/20260614-150009-07db9e/artifacts/comparison/cell0-vs-cell1/`,
  `runs/dema-adjudication-matrix/20260614-150009-07db9e/artifacts/comparison/cell0-vs-cell2/`,
  and
  `runs/dema-adjudication-matrix/20260614-150009-07db9e/artifacts/comparison/cell0-vs-cell3/`
- Run ID: `20260614-150009-07db9e`
- Workflow: `dema_adjudication_matrix`
- Workflow hash: `sha256:07db9ee299c2ac62eaaa715729a66a519d7380617be65ce4f344d164478bb08a`
- DEMA dependency lock: `01dec45711c1db06b4b6b2f7fde3cf78870bc22d`

Matrix cells:

| Cell | Adjudicator route | Confidence threshold |
|------|-------------------|----------------------|
| `cell[0]` | `adjudicator_openai` | `0.6` |
| `cell[1]` | `adjudicator_openai` | `0.7` |
| `cell[2]` | `adjudicator_claude` | `0.6` |
| `cell[3]` | `adjudicator_claude` | `0.7` |

Run totals:

| Status | Attempted | Succeeded | Failed | Skipped | Not attempted |
|--------|-----------|-----------|--------|---------|---------------|
| completed | 16 | 16 | 0 | 0 | 0 |

Per-cell metrics:

| Cell | Model | Coverage | Abstain rate | Precision | Recall | Cost total | Latency p95 ms |
|------|-------|----------|--------------|-----------|--------|------------|----------------|
| `cell[0]` | `openai/gpt-4o-mini` | 1.0000 | 0.0000 | 0.0714 | 1.0000 | n/a | 7179.5 |
| `cell[1]` | `openai/gpt-4o-mini` | 1.0000 | 0.0000 | 0.0714 | 1.0000 | n/a | 6377.25 |
| `cell[2]` | `anthropic/claude-sonnet-4-6` | 0.9375 | 0.0625 | 0.0667 | 1.0000 | `$0.161952` | 14007.0 |
| `cell[3]` | `anthropic/claude-sonnet-4-6` | 0.9375 | 0.0625 | 0.0667 | 1.0000 | `$0.153354` | 11314.0 |

Decision-path evidence:

| Cell group | Decisions | Abstains | Adjudication errors | Decision paths |
|------------|-----------|----------|---------------------|----------------|
| OpenAI threshold cells | 16 per cell | 0 per cell | 0 | `chat+schema` |
| Claude `0.6` cell | 16 | 1 | 0 | `tool_call` 14, `tool_call+repair` 1, `tool_call+repair+abstain` 1 |
| Claude `0.7` cell | 16 | 1 | 0 | `tool_call` 15, `tool_call+repair+abstain` 1 |

## DEMA Decision

The DEMA acceptance leg validates the Sprint 03 target beyond the GradeBot
rehearsal: Pipyer expanded a four-cell matrix over two adjudicator routes and
two thresholds, preserved cell-local outputs, completed all downstream steps,
and produced archive-stable comparison artifacts for every requested baseline
comparison.

The run also exercised the DEMA bridge's fail-closed provider-output handling.
Claude returned malformed tool output for one pair; DEMA repaired or converted
that case into a counted `ABSTAIN` rather than dropping the pair. That produced
one decision per input pair, zero adjudication errors, and explicit
`tool_call+repair+abstain` evidence in the logs.

## Supporting Local Evidence

The current local evidence set retained under `runs/gradebot-t2-matrix/`:

- `smoke-20260613-215009-aaa841/`: zero-spend duplicate-`test` cell smoke run.
- `compare-20260611-210517-6a8fb0-vs-20260613-123418-6a8fb0-20260613-215040/`:
  zero-spend comparison of retained GradeBot T2 archives.
- `preflight-20260613-215733/`: dry-run-only preflight of the live matrix workflow,
  recording `live_run_launched: false`.
- `20260613-220206-12e3eb/`: completed live matrix archive.

The current local evidence set retained under `runs/dema-adjudication-matrix/`
includes:

- `preflight-20260614-145851/`: dry-run-only preflight of the locked DEMA matrix
  workflow after the final fail-closed DEMA fix.
- `smoke-20260614-145902-ac114d/`: zero-spend smoke run over duplicate local
  DEMA cells, including compare artifact generation.
- `20260614-150009-07db9e/`: completed live four-cell DEMA matrix archive.

These directories remain intentionally gitignored.
