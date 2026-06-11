# Feature Specification: Workflow Runner (GradeBot Vertical Slice)

**Feature Branch**: `002-workflow-runner`

**Created**: 2026-06-11

**Status**: Draft

**Input**: User description: "based on the contents of @docs/sprint-02/" (consolidated brief at `docs/sprint-02/BRIEF.md`, itself transcribing the Feature 001 record: `docs/sprint-01/SPEC.md` section 6, `docs/sprint-01/BACKLOG.md`, `specs/001-pydanticai-spike-contracts/exit-notes.md`, `specs/001-pydanticai-spike-contracts/spike-report.md`)

## Clarifications

### Session 2026-06-11

- Q: Where is the comparison record produced? → A: Workflow steps: baselines are workflow inputs; a `python` step computes the comparison; results land in declared outputs and the summary surfaces the agreement statistics. No comparison machinery enters the runner (Feature 003 territory).
- Q: What is the agreement metric in the comparison record? → A: Exact-match rate per student × problem entry (the same units as the 1.7% floor, and scores are quantized - rubric booleans times fixed deductions - so exact match asks "did any judgment flip"). Refinements: (1) where baseline rubric booleans exist, report rubric-item agreement as a diagnostic layer beneath the per-entry headline; (2) deltas are self-diagnosing because deductions are quantized - the disagreement listing names the implied cause (e.g., 0.12 = one rubric item flipped, 0.20 = execution penalty differed) via lookup, not analysis; (3) the 12 known-patched entries are tagged as expected disagreements against the patched baseline, so the listing reads as three categories: agrees, disagrees-because-human-corrected (expected), disagrees-unexplained. Unexplained disagreement above the ~2% floor is the number SC-008's review turns on.
- Q: Which model alias does the acceptance run grade with? → A: The same model the archived T2 v2 run used, pinned via alias config, so disagreement isolates the runner change. The 1.7% floor was measured on that model; grading with a different model would conflate runner-fidelity disagreement with model-change disagreement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a validated workflow end to end (Priority: P1)

A workflow author runs `pipyer run <workflow>` on a workflow that already passes `pipyer validate`. The runner executes steps sequentially, expands `each` steps over collections with positional alignment, records a result for every item including failures, skips downstream work for failed items with a recorded reason, halts when a failure budget is exceeded, and captures cost on every LLM step. When the run ends (complete or halted), the run directory contains an append-only event log, a checkpoint, declared outputs, and a human-readable markdown run summary.

**Why this priority**: This is the feature. Without end-to-end execution nothing else (resume, audit, the acceptance benchmark) can exist.

**Independent Test**: Run a single-cell workflow with sequential steps and one `each` step over a collection containing both succeeding and failing items, using the deterministic stub model; verify per-item results, skip records, budget halt behavior, and the produced run directory.

**Acceptance Scenarios**:

1. **Given** a valid workflow with sequential steps, **When** the user runs it, **Then** every step produces a `StepResult`, events append to the JSONL log, and a markdown summary is written.
2. **Given** an `each` step where some items fail, **When** the run completes, **Then** failed items have failure-status `StepResult` records (never silent omissions), downstream steps skip those items with a recorded skip reason, and items within budget continue.
3. **Given** `max_failures` or `max_failure_rate` is exceeded mid-batch, **When** the budget trips, **Then** the workflow halts and the halt is itself a recorded event.
4. **Given** an LLM step executes, **When** its result is recorded, **Then** provider, model, token counts, estimated cost, cost-table version, and reported-vs-estimated flag are present by default.
5. **Given** an invalid workflow, **When** the user runs `pipyer run --dry-run`, **Then** the behavior is exactly that of `pipyer validate` (one implementation), and no run directory is created.

---

### User Story 2 - Interrupt and resume without recomputation (Priority: P1)

A user's long batch run is interrupted (crash, Ctrl-C, power loss). They rerun with `--resume`; completed work whose workflow, input, and configuration hashes match is skipped, diffs against the prior run are reported, and failed items are retried only when `--retry-failed` is passed. The event log is authoritative; checkpoint writes are atomic; a corrupt trailing JSONL line is detected and recovered on replay.

**Why this priority**: Resume is co-equal with execution in this slice; the acceptance run requires a live interrupt/resume demonstration with zero recomputation, and the 8 skip-marked execution fixtures encode it.

**Independent Test**: Start a stub-model batch, kill it mid-`each`, resume, and verify completed items are not re-executed, the diff report is produced, and failed items rerun only with the explicit flag.

**Acceptance Scenarios**:

1. **Given** an interrupted run, **When** the user resumes it, **Then** items whose content hashes match are skipped with zero recomputation and the summary reports what was skipped vs recomputed.
2. **Given** a prior run with failed items, **When** the user resumes without `--retry-failed`, **Then** failed items are not retried; with the flag, they are.
3. **Given** a configuration or input change between runs, **When** the user reruns, **Then** only steps whose input hashes changed recompute, and the run record states what moved.
4. **Given** a crash left a corrupt trailing line in the event log, **When** the run is resumed, **Then** the corruption is detected and recovered per the conformance fixture.
5. **Given** a final `file_write` step already ran, **When** the workflow is resumed with unchanged input hashes, **Then** the write does not rerun (R5: no special-case flag).

---

### User Story 3 - Audit a run from its record (Priority: P2)

An instructor (or any workflow consumer) opens a finished run directory and can account for every unit of work: each student × problem has a result trail, costs are totaled, failures and skips are explained. The markdown summary is derivable from the event log alone and can be regenerated after the fact.

**Why this priority**: Evidence an instructor can audit is the exit bar for the acceptance run, but it depends on stories 1-2 existing.

**Independent Test**: Delete the summary from a completed run directory, regenerate it from the event log alone, and verify it is complete and identical in content.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the summary is regenerated from the event log, **Then** it contains the same run accounting (the run-record contract holds).
2. **Given** any item in the batch, **When** the auditor looks for it, **Then** a `StepResult` trail exists for it - success, failure, or recorded skip; no silent omissions.

---

### User Story 4 - The acceptance run: re-grade a graded test (Priority: P1, feature exit)

The user expresses the INSY 3010 Test 2 grading process as a Pipyer workflow against the archived spring 2026 corpus (47 students, 4 problems, 188 graded rows, 177 with submissions), runs it end to end on a live model alias pinned to the model the archived v2 run used, injects a mid-batch interruption, resumes with zero recomputation, and produces a comparison record: per student × problem, the workflow's scores beside the layered baselines (raw v2 machine output, and the published v2-patched human-reviewed totals), with agreement statistics in the run summary and the measured 1.7% nondeterminism floor as context.

**Why this priority**: The feature is proven by grading a real assignment, not by the runner merely running. This is the evidence-producing benchmark that gates exit.

**Independent Test**: This is the integration test of the whole feature; it is independently verifiable by the cross-session review checkpoint ("does the runner grade credibly"), arbitrated by the user, never self-graded.

**Acceptance Scenarios**:

1. **Given** the T2 corpus referenced by absolute path, **When** the workflow runs end to end within failure budgets, **Then** every student × problem in the corpus (47 students × 4 problems = 188) has an auditable `StepResult` trail, with the empty-submission path exercised by present students who skipped problems (explicit records, not omissions). The 3 absent students are excluded from the corpus and the baseline's 188 rows by the original grading's design; they appear only as roster annotations, never as invented comparison rows.
2. **Given** a mid-batch interruption, **When** the run is resumed, **Then** completed grading is not recomputed and the evidence trail is complete.
3. **Given** the comparison record, **When** reviewed, **Then** it shows agreement against both baselines separately, and the 1 academic-integrity override (published 0 vs graded 100) is compared against the graded score with the override surfaced as an annotation, never silently reconciled.
4. **Given** the corpus contains student PII, **When** the run executes, **Then** no corpus data is copied into the repo, run outputs land in a gitignored or external results directory, and nothing is posted or changed anywhere.

---

### Edge Cases

- Duplicate item values in an `each` collection: alignment is by index, never by item value; duplicates must not break downstream lookup.
- Failure budget trips exactly at the boundary mid-`each`: the halt event records which items completed, failed, and were never attempted.
- Resume requested when no prior run exists, or `--resume last` with an empty results directory: a clear error, not a fresh silent run.
- A second writer attempts to append to a live run's event log: single-writer enforcement rejects it.
- Workflow definition changed between run and resume: canonical-serialization hash mismatch means affected work recomputes; the diff report says so.
- Timeout on a `shell`/`python`/`llm` step: the timeout is enforced and recorded as a failure with its taxonomy category, feeding the failure budget like any item failure.
- Side-effecting steps (shell, file writes) fail transiently: not retried by default; retry ownership rules keep component-internal validation retries bounded, counted, and non-multiplicative with runner retries.
- A local model alias is in play: structured-output mode comes from alias configuration; local aliases are never auto-picked.

## Requirements *(mandatory)*

### Functional Requirements

Binding semantics in FR-001 through FR-010 transcribe `docs/sprint-01/SPEC.md` section 6 and the Feature 001 exit notes; they are decided, not open for re-exploration.

- **FR-001**: The system MUST execute a validated single-cell workflow: load, validate, resolve inputs and settings, execute steps sequentially, expand `each` steps over collections, emit a `StepResult` per execution, append events to a JSONL log, and write checkpoint state for resume.
- **FR-002**: `each` execution MUST use positional alignment (`item` is the value, `index` the position); downstream aligned access is by index, never by item value; item failures MUST produce failure-status `StepResult` records; downstream steps MUST skip failed items with a recorded skip reason (global policy, R2).
- **FR-003**: The system MUST halt the workflow when `max_failures` or `max_failure_rate` is exceeded, and the halt MUST be a recorded event.
- **FR-004**: Resume MUST be content-hash based using the frozen canonical serialization as the single definition of workflow identity: completed work is skipped on hash match, diffs against the prior run are reported, and failed items are retried only with an explicit flag. Checkpoint writes MUST be atomic; the event log is authoritative (R6) and single-writer; corrupt trailing JSONL records MUST be detected and handled on replay.
- **FR-005**: Retry ownership MUST follow the decided split: the runner owns transport-level and run-level retries; component-internal validation retries are bounded, counted, and reported in the `StepResult` without multiplying with runner retries; side-effecting steps are not retried by default.
- **FR-006**: Every LLM step MUST record cost by default: provider, model, token counts, estimated cost, cost-table version, and whether counts are provider-reported or estimated.
- **FR-007**: `file_write` MUST follow the dry-run-gated, idempotent conventions; on resume, final writes rerun only when input hashes changed (R5, no special-case flag).
- **FR-008**: The `llm` component's structured-output mode (tool / native / prompted) MUST be alias-configurable, and local aliases MUST never be auto-picked.
- **FR-009**: Secrets MUST be resolved at call time via the provider chain `auto`/`1password`/`env` (R14), graduating the spike resolver into the package; the provider name lands in the run record, the secret value never does. A run-start preflight additionally verifies that every alias-required credential is resolvable before any work begins (values discarded, resolved again at call time) - resolvability is checked eagerly, resolution stays call-time.
- **FR-010**: The `llm` component MUST map provider errors to the decided taxonomy: HTTP 429 to `rate_limited`, other HTTP errors to `provider_error`, non-HTTP transport failures to `transport_error`, model-behavior and incomplete-tool-call failures to `output_validation_error`, content-filter rejections to `provider_error` with the type in detail.
- **FR-011**: The CLI MUST provide a run command alongside validation, of the approximate shape `pipyer run <workflow> [--input k=v ...] [--resume <run-id>|last] [--retry-failed] [--dry-run]`; `--dry-run` MUST be exactly `validate` - one implementation, no second validation path.
- **FR-012**: Each run MUST produce a run directory under `settings.results_dir` (`<results_dir>/<run_id>/`) containing the event log, checkpoint, declared outputs, and the markdown run summary; exact names and structure are this feature's to decide.
- **FR-013**: The markdown run summary MUST be derivable from the event log alone and regenerable after the fact (run-record contract).
- **FR-014**: The runner MUST enforce timeouts on `shell`, `python`, and `llm` steps and record timeout failures under the existing taxonomy category.
- **FR-015**: Item scheduling MUST honor `settings.concurrency` (default 1) with bounded item-level parallelism within an `each` step.
- **FR-016**: The 8 skip-marked execution fixtures in `tests/conformance/execution/` MUST pass unskipped and unrewritten; if the `pipyer.runner` API they imagine proves wrong, that is a finding surfaced at review, not a silent adaptation.
- **FR-017**: The contract-module import boundary MUST hold with the LLM substrate present in the package: PydanticAI enters `src/` only inside the `llm` component, and `test_import_boundary.py` stays green unmodified.
- **FR-018**: Frozen Feature 001 contracts MUST NOT change without conformance-test changes in the same change set (constitution VI) and a schema version bump when semantics change.
- **FR-019**: Conformance tests MUST use the deterministic stub model; live models are used only where the question demands them (the acceptance run).
- **FR-020**: The acceptance run MUST express T2 scoring parameterization (`t2-config.json` point weights and deduction parameters) as workflow inputs - data, not code - and produce the layered comparison record described in User Story 4.
- **FR-021**: The comparison record MUST be produced by the workflow itself: baseline files declared as workflow inputs, a deterministic `python` step computing the comparison, results landing in declared outputs with agreement statistics surfaced in the run summary. No comparison machinery enters the runner (run comparison tooling is Feature 003).
- **FR-022**: The headline agreement statistic MUST be the per-entry (student × problem) exact-score-match rate against each baseline separately, the same units as the measured nondeterminism floor. The disagreement listing MUST include score deltas with the implied cause named via the quantized-deduction lookup, rubric-item-level agreement as a diagnostic layer where baseline rubric booleans exist, and the 12 known-patched entries tagged as expected disagreements - so every disagreement is classified as expected (human-corrected) or unexplained.
- **FR-023**: The acceptance run MUST grade with the same model the archived T2 v2 run used (`claude-sonnet-4-5-20250929`, per `t2-config.json` and the published run bundle), pinned via alias configuration - and the pin extends to the whole judgment configuration: sampling parameters and prompt-template details documented in the run bundle README are transcribed into the alias settings and prompt files. Only then does disagreement against the raw v2 baseline isolate the execution-substrate change with the 1.7% nondeterminism floor as valid context. If the dated model snapshot is no longer served when the acceptance run executes, that is a HALT-and-rethink on the baseline design, never a silent substitution.

### Key Entities

- **Run**: one execution of a workflow; identified by a run id; owns a run directory; ends complete, halted (budget), or interrupted.
- **Run directory**: `<results_dir>/<run_id>/` holding the event log, checkpoint, declared outputs, and run summary.
- **Event log**: append-only JSONL, single-writer, the authoritative record; checkpoints are reconstructable from it.
- **Checkpoint**: atomic snapshot enabling resume; subordinate to the event log.
- **StepResult**: the per-execution record (per item within `each`); carries status, evidence, cost (LLM steps), retry counts, skip reasons.
- **Run summary**: markdown digest derived from the event log alone; for the acceptance run it carries agreement statistics.
- **Comparison record**: per student × problem table of workflow scores against the layered baselines, with special cases annotated; produced by a `python` step in the workflow from baseline inputs, not by the runner.
- **Workflow identity hash**: content hash via the frozen canonical serialization; the basis of resume matching.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The 8 previously skip-marked execution conformance fixtures pass unskipped, with zero rewrites of fixture expectations.
- **SC-002**: The full T2 batch (47 students × 4 problems) completes within failure budgets with a per-item evidence trail an instructor can audit: all 188 graded rows accounted for, no-submission rows (present students who skipped problems, per the baseline CSV's own accounting) graded through the empty-submission path as explicit records, the 3 absent students handled as roster annotations (they have no baseline rows), zero silent omissions.
- **SC-003**: A live mid-batch interruption followed by resume recomputes zero completed items, demonstrated on the acceptance run and verified from the run record.
- **SC-004**: The comparison record exists and is legible: per-entry exact-match rates against both the raw v2 baseline and the published v2-patched baseline reported separately, with the 1.7% nondeterminism floor stated as context, every disagreement classified as expected (known-patched, academic-integrity override) or unexplained, and the academic-integrity override surfaced as an annotation. Unexplained disagreement above the ~2% floor is the figure the SC-008 review turns on. Agreement is evidence to review, not a pass/fail threshold.
- **SC-005**: A regenerated run summary, produced from the event log alone after deleting the original, matches the original's accounting.
- **SC-006**: `ruff format --check`, `ruff check`, and `ty check` are clean on `src/` and `tests/`; the full suite is green.
- **SC-007**: No student PII enters the repository; all acceptance-run outputs land in a gitignored or external results directory; the closed-semester corpus is untouched.
- **SC-008**: The comparison record passes cross-session review with the user arbitrating ("does the runner grade credibly") before being accepted as feature exit.

## Out of Scope

- Matrix execution and run comparison tooling (Feature 003); the runner executes single-cell workflows only. Stability measurement (the 1.7% / 17.5% numbers) is carried as evidence for Feature 003's spec.
- External CLI orchestration as a proven pattern (Feature 004); `shell` steps run commands, but the twc-bridge composition case waits.
- Grade posting (danvas integration); the workflow ends at written feedback files and a summary.
- The review-and-patch finalization tail (brief section 6): config-iteration re-runs, band-filtered cross-validation, and `patches.yaml`-driven publication are all expressible in the existing schema once the runner exists - workflow steps, not new machinery - and extending the GradeBot workflow with that tail is post-002 work. The acceptance run benchmarks grading, not finalization.
- Campaign semantics and review queues (ADR-006).
- New component types, and any change to validation behavior that `pipyer validate` does not share.

## Assumptions

- The Feature 001 contracts, canonical serialization, and the 8 execution fixtures are frozen inputs; this spec transcribes their semantics rather than re-deciding them.
- The T2 corpus at `/Volumes/Casa/au/teaching/INSY3010-PySQL/_archive/25-26.Sp/grading/t2/` is available read-only at acceptance-run time and is referenced by absolute path only.
- A live model alias suitable for the acceptance run is configured, with secrets resolvable through the R14 provider chain; conformance work needs no network or spend (deterministic stub).
- The pinned baseline model (`claude-sonnet-4-5-20250929`) is still served at acceptance-run time; dated snapshots are eventually deprecated by providers, which argues against letting this feature drift on the calendar.
- The exact CLI flag spelling, run-directory file names, and run-summary format are this feature's planning decisions, within the constraints stated in FR-011 through FR-013.
- The process gate follows the Feature 001 rhythm (specify → cross-session review → clarify → plan → analyze → tasks → implement), with the named checkpoint on the comparison record.
