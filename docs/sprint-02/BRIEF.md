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
and a summary). Campaign semantics, review queues (ADR-006). New component types. Any
change to validation behavior that `pipyer validate` does not share.

## 5. The Acceptance Run: Re-Grade a Graded Assignment

The feature's exit is an evidence-producing benchmark, not a demo:

1. Corpus: a real, already-graded past assignment (candidate: INSY 7120 spring 2026 HW1 -
   the submissions exist, the issued grades exist, and three of them were hand-reviewed and
   explicitly trusted). Data stays local; nothing is posted or changed anywhere.
2. Run the GradeBot workflow (the Feature 001 fixture, parameterized to the real corpus)
   end to end on a live model alias.
3. Inject an interruption mid-batch; resume; demonstrate zero recomputation of completed
   items and complete per-item evidence including any failures.
4. Produce a comparison record: per-student, the workflow's grade and feedback next to the
   historically issued grade, with agreement statistics in the run summary.

Exit criteria:

- The full batch completes within failure budgets with per-item evidence an instructor can
  audit (every item has a `StepResult` trail; no silent omissions).
- Interrupt/resume behaves per contract (the 8 fixtures all pass unskipped, plus the live
  demonstration).
- The comparison record exists and is legible. Agreement with the human baseline is
  evidence to review, not a pass/fail threshold - grading judgment quality is a consumer
  concern this sprint measures but does not gate on.
- `ruff format --check`, `ruff check`, `ty check` clean on `src/` and `tests/`; suite green.

## 6. Gate

Same rhythm as Feature 001: specify → cross-session review → clarify → plan → analyze →
tasks → implement. One named checkpoint: before the acceptance run's comparison record is
accepted as the feature exit, it comes to cross-session review with the user arbitrating -
"does the runner grade credibly" is this feature's analogue of "is the boundary right."
Never self-graded.
