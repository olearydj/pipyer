# Sprint 03 Brief: Matrix Execution and Run Comparison (Feature 003, DEMA Experiment Runner)

Source material for `/speckit.specify`, consolidated 2026-06-12 from the Feature 002 record.
Transcribe decided content; do not re-explore it. Inputs of record:
`docs/sprint-01/SPEC.md` (section 6 matrix semantics are binding),
`docs/sprint-01/BACKLOG.md` (Feature 003 entry and exit criterion),
`specs/002-workflow-runner/acceptance-evidence.md` and `exit-notes.md` (carried items),
DEMA-LLM's TDD Epic 0.3 (`/Volumes/Casa/dev/dema-llm/docs/tdd/`, the consumer's own
specification of this runner).

## 1. Goal

Make the runner execute matrix workflows and make runs comparable. Matrix expansion over
parameters (never topology) with cell parameters attached to every relevant `StepResult` and
cost aggregatable by dimension; and run-to-run comparison as a product capability -
`pipyer compare` over run records, reporting quality, cost, and latency differences down to
per-unit diffs. The feature is proven by real experiments that support real decisions
(section 5), not by machinery existing.

This is the consumer-two slice (ADR-005: DEMA Epic 0.3 is scheduled work in that project's
roadmap). The twc-bridge composition pass is Feature 004.

## 2. Binding Inputs (Decided; Not Open for Re-Exploration)

- Matrix semantics, SPEC section 6: expansion over parameters only, never topology; matrix
  parameters attach to every relevant per-step record; cost totals aggregatable by matrix
  dimension. The schema already expresses `matrix` and R1's alias-target-as-reference is the
  designed mechanism for varying models per cell - validation accepts it today; only
  execution is new.
- The Feature 001/002 contracts and runner semantics are frozen ground: content-hash resume,
  R2 skip policy, R25 no-automatic-in-run-retries (with its named exception below), failure
  budgets, the event log as authority, `summary_*` output convention, R14 secrets, R23 test
  hooks. The 002 conformance suite (208 tests as of the 2026-06-13 audit
  follow-up) stays green throughout.
- Comparison-machinery lineage: 002's FR-021 deliberately kept *domain* comparison (grades
  vs historical baselines) in workflow steps. That boundary stands. What enters the product
  now is *run-to-run* comparison: same workflow, different runs or cells, compared on the
  run record alone - quality via workflow-declared `summary_*` outputs and per-unit results,
  cost and latency from the records. The gradebot-t2 `compare.py` (layered baselines,
  quantized-cause lookup, three-category classification) is design input, not product code.
- Stability measurement is a first-class comparison mode: identical re-runs compared for
  score instability. The consumer already practices this by hand - the archived T2 (1.7%)
  and T1 (17.5% pre-prompt-hardening) numbers are the existing evidence and the validation
  target (Pipyer's measurement of an identical re-run pair should land near the archived
  floor on the same corpus/model).
- R25's named exception comes due, conditionally: DEMA's large matrix runs are the
  documented puller for an in-run `retry:` settings block (explicit, bounded, recorded -
  never a hardcoded default). Pull it only if the acceptance experiments actually demand it;
  the spike's non-multiplication evidence (2 × 3 = 6) is the bound proof.
- Carried candidate contracts touch, decide deliberately at planning: script-file content
  joins unit identity (the 002 acceptance run showed a fixed script is invisible to resume
  and a failed unit needs `--retry-failed` even when the fix is the point). This changes
  `input_hash` semantics, not canonical workflow bytes - settle the versioning treatment
  explicitly (it is resume-matching semantics, the run-record side, not the workflow hash).
- DEMA integration shape: DEMA's stages are CLI commands (`dema-llm triage|adjudicate|
  cluster|eval`), driven as `shell` steps with `uv run --project /Volumes/Casa/dev/dema-llm`.
  This does not pre-empt Feature 004 - 004 proves the twc-bridge composition case; 003 uses
  shell steps because its consumer's pipeline is a CLI, full stop. The problem being
  replaced is documented in that repo: experiment tracking by filename suffix
  (`decisions.openai.tuned.jsonl`, `metrics.A.sqlite`), config fragmented across
  `router.yaml`/flags/env, no manifests. Epic 0.3's own deliverable list (per-run
  `decisions.jsonl`, `metrics.json`, `manifest.json` with config snapshot and git commit) is
  already what Pipyer run records provide - the acceptance demonstrates that mapping.

## 3. New Ground (For Spec and Plan to Decide)

- Cell execution model: expansion order, one run encompassing all cells (params attached per
  record) per SPEC section 6; cell-level concurrency vs item-level concurrency; how failure
  budgets scope (per cell, per run, or both); cell-level resume (a run interrupted mid-matrix
  resumes at the right cell × item).
- Matrix × `each` interplay pinned precisely (cells expand outside `each`; unit keys carry
  both cell and index - the R20 key convention extends, decide the canonical form).
- `pipyer compare` CLI surface: compare two run ids (or cells within one run) on quality
  (declared `summary_*` outputs and per-unit result diffs), cost, latency; stability mode
  for identical re-runs; output as markdown + JSON (the comparison is itself evidence and
  should be derivable from the two event logs alone, like the summary).
- Cost aggregation by matrix dimension in the run summary.
- Whether the in-run `retry:` block is pulled (see binding inputs; consumer-demand test).
- Spend discipline carried forward: stub for conformance; live calls only in the acceptance
  experiments, with the matrix multiplying spend deliberately budgeted up front.

## 4. Out of Scope

External-CLI orchestration as the proven composition pattern (Feature 004, twc-bridge).
Campaign semantics (ADR-006). DocETL/Inspect/DSPy/promptfoo adapters. Dashboards or
visualization beyond markdown/JSON comparison records. The review-and-patch workflow tail
(expressible since 002; still a workflow-authoring exercise, not product). Pareto-frontier
analytics beyond what the comparison record reports (DEMA's research methodology consumes
Pipyer's records; Pipyer does not become the statistics package).

## 5. The Acceptance Experiments

Two legs, cheap rehearsal first, consumer exit second - both producing decision-grade
comparison records, both gated (section 6).

### 5a. Rehearsal: the fall model-upgrade question (GradeBot matrix)

The question Feature 002 left ready-made: should fall grading move off the pinned
`claude-sonnet-4-5-20250929`? One matrix workflow over the archived T2 corpus: dimension
`model = [sonnet-4-5-20250929, <current default candidate>]`, the alias-as-matrix-ref
mechanism doing the binding, everything else identical. The comparison record reports
per-model agreement against the archived baselines (reusing the workflow's own domain
comparison), cost, and latency side by side. Same PII discipline as 002 (corpus by absolute
path, outputs external). Spend: roughly 2× the 002 run (~$4-8 depending on the candidate).
This leg exercises matrix execution, per-cell records, dimension cost aggregation, and
`pipyer compare` end to end with known ground truth.

### 5b. Consumer exit (backlog criterion): a real DEMA experiment from one workflow file

A DEMA adjudication experiment over its existing gold pairs (`out/gold_pairs.jsonl` and the
committed adjudication cases exist in that repo): matrix over adjudicator model × one second
factor the consumer cares about (prompt variant or re-ask policy), stages driven as shell
steps, metrics (precision/recall vs gold) computed by DEMA's own eval as a step, run records
replacing the filename-suffix bookkeeping. Exit per the backlog: the experiment runs from
one workflow file, and two runs (or cells) are comparable on quality, cost, and latency
via `pipyer compare`. A stability pair (identical re-run, compared) validates the
measurement against the archived floor methodology.

## 6. Gate

Same rhythm: specify → cross-session review → clarify → plan → analyze → tasks → implement,
with the named checkpoint on the comparison records: before either acceptance leg counts as
exit, its comparison record comes to cross-session review with the user arbitrating - the
question this time is "do these records support a real decision" (the fall-upgrade call; a
DEMA configuration choice). Never self-graded.
