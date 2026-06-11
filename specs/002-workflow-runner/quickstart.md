# Quickstart Validation: Workflow Runner

Runnable scenarios proving the feature end to end. Contracts: [runner-api.md](contracts/runner-api.md), [run-cli.md](contracts/run-cli.md), [run-directory.md](contracts/run-directory.md). Entities: [data-model.md](data-model.md).

## Prerequisites

```bash
cd /Volumes/Casa/dev/pipyer
uv sync
```

Conformance scenarios need no network and no secrets (deterministic stub). Only scenario 6 (acceptance run) needs a live credential and the archived corpus.

## 1. Conformance gate: the 8 fixtures, unskipped

```bash
uv run pytest tests/conformance/execution/ -v
```

Expected: 8 passed, 0 skipped, with the fixture bodies byte-identical to their Feature 001 form (verify: `git diff 9cd82a7 -- tests/conformance/execution/test_execution_fixtures.py` shows only the removed skip markers - the `@F002` lines plus the now-unused marker definition and `pytest` import - and the removal of obsolete `# ty: ignore[unresolved-import]` comments that became dead once `pipyer.runner` exists; zero assertion changes).

## 2. Full suite and quality gates (SC-006)

```bash
uv run pytest
uv run ruff format --check src tests
uv run ruff check src tests
uv run ty check
```

Expected: suite green including `test_import_boundary.py` unmodified; all checks clean.

## 3. CLI: run, dry-run parity, run directory

```bash
uv run pipyer run tests/fixtures/gradebot/workflow.yaml --results-dir /tmp/pipyer-quickstart
uv run pipyer run tests/fixtures/gradebot/workflow.yaml --dry-run   # identical to: pipyer validate
ls /tmp/pipyer-quickstart/*/
```

Expected: exit 1 - the fixture deliberately contains one failing submission (bob), and completed-with-failures exits 1 per the run-cli contract; the human output reports 25 succeeded, 1 failed, 3 skipped. The run directory matches the run-directory contract (`events.jsonl`, `checkpoint.json`, `run.json`, `summary.md`, `outputs/`); `--dry-run` produces validation output only, exits 0, and creates nothing.

## 4. Interrupt and resume (US2)

Start a stub batch, interrupt with Ctrl-C mid-`each` (or use the recorded test hook via the API), then:

```bash
uv run pipyer run tests/fixtures/gradebot/workflow.yaml --resume last --results-dir /tmp/pipyer-quickstart
```

Expected: exit 1 (the prior failure carries over, un-retried, into the resumed run's accounting); the summary's resume section reports skipped (hash-match) units and `Units recomputed: 0`; `events.jsonl` shows one `run_resumed` boundary naming `run_tests[1]` as failed-not-retried. With a deliberately edited input: only affected units recompute, and the totals name them.

## 5. Summary regeneration (SC-005)

```bash
RUN=$(ls -d /tmp/pipyer-quickstart/*/ | tail -1)
cp "$RUN/summary.md" /tmp/summary-orig.md
rm "$RUN/summary.md"
uv run python -c "from pipyer.runner import derive_summary; from pathlib import Path; print(derive_summary(Path('$RUN/events.jsonl')), end='')" > "$RUN/summary.md"
diff /tmp/summary-orig.md "$RUN/summary.md"
```

Expected: no diff (byte-stable derivation from the log alone).

## 6. Acceptance run: re-grade T2 (US4, gated by cross-session review)

Preconditions: corpus readable at the archived absolute path; the v2-pinned model alias resolves via the R14 chain (`pipyer run ... --dry-run` then preflight will confirm); external/gitignored results dir.

```bash
uv run pipyer run workflows/gradebot-t2/workflow.yaml \
  --input corpus_dir=/Volumes/Casa/au/teaching/INSY3010-PySQL/_archive/25-26.Sp/grading/t2 \
  --results-dir /Volumes/Casa/au/teaching/INSY3010-PySQL/pipyer-runs
# interrupt mid-batch (Ctrl-C), then:
uv run pipyer run workflows/gradebot-t2/workflow.yaml --resume last \
  --input corpus_dir=... --results-dir ...
```

Expected outcomes (SC-002/003/004/007): batch completes within budgets; 188 entries accounted for incl. 3 explicit empty-submission records; resume recomputes zero completed items; `outputs/` holds the comparison record with per-baseline exact-match rates, three-category disagreement classification, and the unexplained-above-floor figure; summary surfaces the agreement statistics; no PII in the repo. The comparison record then goes to cross-session review (SC-008) before the feature exits.
