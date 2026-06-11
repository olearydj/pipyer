# Sprint 02 Brief: The Runner (Feature 002, GradeBot Vertical Slice)

Source material for `/speckit.specify`, consolidated 2026-06-11 from the Feature 001 record.
Transcribe decided content; do not re-explore it. Inputs of record: `docs/sprint-01/SPEC.md`
(section 6 is binding), `docs/sprint-01/BACKLOG.md` (Feature 002 entry),
`specs/001-pydanticai-spike-contracts/exit-notes.md` (carried items),
`specs/001-pydanticai-spike-contracts/spike-report.md` (the GO'd boundary).

## 1. Goal

Build the minimal runner that executes a validated workflow end to end: sequential steps,
`each` over collections with positional alignment, failure budgets, content-hash resume,
append-only JSONL event log plus a derived markdown run summary, and cost capture on LLM
steps. `pipyer run` joins `pipyer validate`. The feature is proven by grading a real
assignment (section 5), not by the runner merely running.

This is the consumer-one slice (ADR-005). Matrix execution is Feature 003; external-CLI
orchestration is Feature 004. The runner executes single-cell workflows in this feature.

## 2. Binding Inputs (Decided; Not Open for Re-Exploration)

- Execution semantics: `docs/sprint-01/SPEC.md` section 6 in full - `each` positional
  alignment with explicit failure records, skip-on-upstream-failure as global policy (R2),
  failure budgets halting with a recorded event, content-hash resume (completed work skipped
  on hash match, diffs reported, failed items retried only with an explicit flag), retry
  ownership (runner owns transport and run-level retries; component validation retries
  bounded and counted; side-effecting steps not retried by default), atomic checkpoint
  writes with the event log authoritative (R6), cost recorded by default.
- The Feature 001 contracts are frozen. Any schema change lands with conformance-test
  changes in the same change set (constitution VI) and bumps the relevant schema version if
  semantics change. The canonical serialization in `src/pipyer/canonical.py` is the single
  definition of workflow identity; resume matching uses it as-is.
- The 8 skip-marked execution fixtures in `tests/conformance/execution/` are acceptance
  tests, authored in Feature 001 against the `pipyer.runner` API they expect. They are
  unskipped, never rewritten. If the API they imagine proves wrong, that is a finding to
  surface at review, not silently adapt.
- Carried items from `exit-notes.md`, verbatim obligations:
  - The `llm` component's structured-output mode (tool / native / prompted) is
    alias-configurable; local aliases are never auto-picked. Driver: every local model
    failed tool-mode structured output in the spike's live leg and succeeded immediately
    with NativeOutput; the DEMA air-gap path depends on this.
  - The secrets resolver graduates from `spike/_common.py` to `src/pipyer/secrets.py`
    (R14: provider chain `auto`/`1password`/`env`, `op read`, `PIPYER_<KEY>_OP_REFERENCE`
    then conventional env var, `(secret, provider_name)` return - provider name lands in
    the run record, the value never does).
  - Error-shape mappings for the `llm` component: catch `AgentRunError`; `ModelHTTPError`
    by status (429 → `rate_limited`, else `provider_error`); non-HTTP `ModelAPIError` →
    `transport_error`; `UnexpectedModelBehavior` → `output_validation_error`;
    ContentFilterError → `provider_error` (type in detail); IncompleteToolCall →
    `output_validation_error` (detail).
- The import boundary comes due: PydanticAI enters `src/` only inside the `llm` component.
  The contract-module guard (`test_import_boundary.py`) stays green unmodified - Feature 002
  strengthens it by demonstrating the boundary holds with the substrate actually present in
  the package.
- Side-effect conventions: `file_write` follows the dry-run-gated, idempotent danvas
  conventions; final writes rerun on resume only when input hashes changed (R5 - no
  special-case flag).

## 3. New Ground (For Spec and Plan to Decide)

- Runner architecture: execution loop, step dispatch, item scheduling under
  `settings.concurrency` (default 1; bounded item-level parallelism within an `each` step).
- Run directory layout under `settings.results_dir` (`<results_dir>/<run_id>/`): event log,
  checkpoint, run summary, declared outputs - names and structure.
- The markdown run summary: format and content, derivable from the event log alone
  (run-record contract), regenerable after the fact.
- CLI surface: `pipyer run <workflow> [--input k=v ...] [--resume <run-id>|last]
  [--retry-failed] [--dry-run]` or similar - spec decides the exact shape; `--dry-run`
  must be exactly `validate` (one implementation, per the library-parity precedent).
- Event-log single-writer enforcement and crash behavior (corrupt-trailing-line recovery is
  one of the 8 fixtures).
- Timeout enforcement for `shell`/`python`/`llm` steps (taxonomy category exists; semantics
  of enforcement are runner work).
- Test spend discipline, carried from the spike: deterministic stub for all conformance
  work; live models only where the question demands them (the acceptance run).

## 4. Out of Scope

Matrix execution and run comparison (Feature 003). External CLI orchestration as a proven
pattern (Feature 004; `shell` steps obviously run commands, but the twc-bridge composition
case waits). Grade posting (danvas integration; the workflow ends at written feedback files
and a summary). The review-and-patch finalization flow (section 6 - implications recorded,
amendment records deferred as a named candidate feature). Campaign semantics, review queues
(ADR-006). New component types. Any change to validation behavior that `pipyer validate`
does not share.

## 5. The Acceptance Run: Re-Grade a Graded Test

The feature's exit is an evidence-producing benchmark, not a demo. GradeBot's real domain is
INSY 3010 tests, and the canonical reproduction corpus is the spring 2026 archive:
`/Volumes/Casa/au/teaching/INSY3010-PySQL/_archive/25-26.Sp/grading/` - per-test folders
(`t1`, `t2`, `t3`, `final`) each holding `inputs/` (submissions, roster, problems), a
grading config, `runs/` (the manual iteration history: `dryrun`, `phase1-v2`,
`regrade-contamination` - the filename-suffix evidence gap, live), `published/` (the
selected, patched, published totals), and grading notes documenting every decision.

Primary corpus: Test 2 (47 students, 4 problems, 188 graded rows, 177 with submissions).
It has the cleanest record: a `v2-patched` published baseline, per-version change notes,
and a measured LLM-nondeterminism floor - 1.7% of entries changed score on an identical
full re-run (T1's was 17.5% before prompt hardening). That floor is the expected noise
level for any agreement statistics.

The run:

1. Express the T2 grading process as a Pipyer workflow (the Feature 001 fixture adapted:
   real collection from `inputs/submissions`, the test harness per problem, the T2 rubric
   prompts, scoring parameterization from `t2-config.json` as workflow inputs - point
   weights and deduction parameters are data, not code).
2. Run end to end on a live model alias; inject an interruption mid-batch; resume;
   demonstrate zero recomputation and complete per-item evidence.
3. Produce a comparison record: per student × problem, the workflow's scores next to the
   baseline, with agreement statistics in the run summary.

Comparison design - the baseline is layered, and the layers are informative separately:

- Against the raw v2 run (pre-patch machine output): measures whether Pipyer's uniform
  execution reproduces GradeBot's machine judgment, with the ~2% nondeterminism floor as
  context.
- Against `published/2026-04-03-v2-patched` (post-human-review): measures distance from
  final human judgment; the 12 known patches and 74 feedback sanitizations are exactly
  where disagreement is expected and explainable.
- Known special cases the comparison must represent honestly, not trip over: 3 absent
  students (the empty-submission path - per-item records, not omissions), and 1
  academic-integrity override where the published score (0) deliberately differs from the
  graded score (100) - compare against the graded score and surface the override as an
  annotation, never silently reconcile it.

Data discipline: the corpus contains student PII. It is referenced by absolute path, never
copied into this repo; run outputs land under a gitignored or external results directory;
nothing is posted or changed anywhere - this is a benchmark against a closed semester.

Exit criteria:

- The full batch completes within failure budgets with per-item evidence an instructor can
  audit (every student × problem has a `StepResult` trail; no silent omissions).
- Interrupt/resume behaves per contract (the 8 fixtures pass unskipped, plus the live
  demonstration).
- The comparison record exists and is legible, with the layered baselines and special
  cases above. Agreement is evidence to review, not a pass/fail threshold - grading
  judgment quality is a consumer concern this sprint measures but does not gate on.
- `ruff format --check`, `ruff check`, `ty check` clean on `src/` and `tests/`; suite green.

## 6. Review-and-Patch: Out of Scope, Implications Recorded

The archived process does not end when the batch completes. The observed finalization flow
for every test: production run → analyze failures and rubric behavior → config corrections
validated by targeted dry runs → full re-run → cross-validation (two review agents over the
0.44-0.88 score band) → human-approved patches (rubric corrections, feedback sanitization)
→ published totals with overrides (academic integrity) → Canvas CSVs. This sprint does NOT
implement that flow. What each piece implies:

- Config-iteration re-runs (v1 → v2) need no new machinery: a config change alters input
  hashes, the runner recomputes what changed, and the run record diffs say what moved.
  Feature 002 gets this for free from the resume semantics; the v1/v2 pattern is just two
  runs of one workflow.
- Stability measurement (the 1.7% / 17.5% nondeterminism numbers) is run comparison over
  identical re-runs - a concrete, already-practiced consumer use case for Feature 003's
  comparison tooling. Carried as evidence for that feature's spec.
- Band-filtered cross-validation (review agents over 0.44-0.88 scorers) is expressible in
  the existing schema - a `python` filter step feeding an `llm_judge` `each` step - and
  needs no new components. A candidate second workflow, post-002.
- Patching and publication are the genuinely new concept: human-approved corrections to
  individual item results, and a published view derived from (run + amendments). Pipyer
  records are immutable events, so the fit is amendment records - append-only corrections
  referencing the original `StepResult` (target, field, old, new, reason, author,
  timestamp), with published totals as a derived artifact, never a mutation. The
  academic-integrity override is the same shape (published ≠ graded, with reason and
  preserved evidence). This is deferred with a named consumer (this exact grading process,
  every term) and belongs in the backlog as a candidate Feature 005 - it composes with
  ADR-006's append-friendly records and the evidence-layer philosophy: corrections are
  events too.

## 7. Gate

Same rhythm as Feature 001: specify → cross-session review → clarify → plan → analyze →
tasks → implement. One named checkpoint: before the acceptance run's comparison record is
accepted as the feature exit, it comes to cross-session review with the user arbitrating -
"does the runner grade credibly" is this feature's analogue of "is the boundary right."
Never self-graded.
