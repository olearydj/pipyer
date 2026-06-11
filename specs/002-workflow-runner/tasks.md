# Tasks: Workflow Runner (GradeBot Vertical Slice)

**Input**: Design documents from `/specs/002-workflow-runner/`

**Prerequisites**: plan.md, spec.md, research.md (R15-R24), data-model.md, contracts/ (runner-api, run-cli, run-directory), quickstart.md

**Tests**: Conformance tests are MANDATORY per constitution VI and ship in the same change set as any schema change. The 8 execution fixtures in `tests/conformance/execution/test_execution_fixtures.py` already exist; tasks below remove their skip markers per story - fixture bodies are never edited (FR-016). Unit tests listed are for runner internals the fixtures don't reach.

**Organization**: Tasks grouped by user story. US1 (run end to end), US2 (resume), US3 (audit) are P1/P1/P2 engine work; US4 (acceptance run) is the P1 feature exit and depends on US1-US3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1-US4 from spec.md

## Phase 1: Setup

**Purpose**: Dependency and package scaffolding

- [ ] T001 Move `pydantic-ai` from the `spike` dependency group to runtime dependencies in `pyproject.toml` via `uv add pydantic-ai` (leave `anthropic` in the spike group); `uv sync`
- [ ] T002 Create the `src/pipyer/runner/` package skeleton per plan.md: `__init__.py` (declaring `run_workflow`, `reconstruct_checkpoint`, `derive_summary` as the public surface), `engine.py`, `context.py`, `events.py`, `checkpoint.py`, `resume.py`, `summary.py`, `components/__init__.py` - module docstrings and signatures only, no logic
- [ ] T003 [P] Create `tests/unit/__init__.py` and confirm pytest discovers `tests/unit/` (testpaths already `tests`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Contract changes, secrets graduation, and the persistence substrate every story needs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Graduate the secrets resolver from `spike/_common.py` to `src/pipyer/secrets.py`: `resolve_secret(key, provider=None) -> tuple[str, str]`, provider chain `auto`/`1password`/`env`, `PIPYER_<KEY>_OP_REFERENCE` then conventional env var, `SecretResolutionError` carrying key and providers tried (R14, exit-note obligation)
- [ ] T005 [P] Conformance tests for the secrets chain in `tests/conformance/test_secrets.py`: env path, op-reference path (subprocess mocked), chain order under `auto`, provider-name return, exhaustion error message names alias/key/providers; no real `op` calls
- [ ] T006 Schema additions in `src/pipyer/schema/workflow.py` and `src/pipyer/schema/components.py`: `ModelAlias.output_mode: Literal["tool","native","prompted"] | None = None`; `LlmConfig.timeout_s` and `LlmJudgeConfig.timeout_s: int | None = None` (ge=1); bump workflow `schema_version` to `"2"` and set the supported-version set to `{"2"}` (R16 hash-continuity rule)
- [ ] T007 Same change set as T006 - conformance tests in `tests/conformance/test_schema_additions.py`: new fields accepted and round-trip canonically, version-`"1"` files rejected with the legible unsupported-version error, both fields added to the FR-013 field-tripwire census in `tests/conformance/test_workflow_schema.py`; update every in-repo workflow fixture under `tests/fixtures/` to `schema_version: "2"` and re-pin canonical-hash expectations in `tests/conformance/test_canonical.py`
- [ ] T008 Validation rule in `src/pipyer/validation.py`: a local model alias (local base URL) without explicit `output_mode` is a validation error ("local aliases are never auto-picked", enforced at validation per R16); conformance cases added to `tests/conformance/test_schema_additions.py`
- [ ] T009 Single-writer event appender in `src/pipyer/runner/events.py`: `events.jsonl.lock` via `O_CREAT|O_EXCL` with `{pid, started_at}`, `RunLockedError` on live lock, stale-pid reclaim flagged for the resume diff, in-process queue so worker threads funnel to one writing thread, append via existing `event_line()` (R18)
- [ ] T010 [P] Unit tests for the lock in `tests/unit/test_events_lock.py`: second-writer rejection, stale reclaim, clean-exit lock removal, queue ordering under concurrent producers
- [ ] T011 Run context and unit hashing in `src/pipyer/runner/context.py`: resolved inputs (CLI overlay on `InputDecl` defaults), alias table with secret provider names (never values), `ExecutionUnit` keys `"<step>"` / `"<step>[<index>]"`, `input_hash` = SHA-256 over canonical JSON of resolved inputs + step config + workflow hash (R20); run-id generation `<utc-stamp>-<hash6>` with `-2`/`-3` collision suffix and run-directory creation per `contracts/run-directory.md` (R17)
- [ ] T012 [P] Unit tests for hashing and identity in `tests/unit/test_context_hash.py`: duplicate `each` item values yield distinct keys, hash moves with inputs vs config vs workflow independently, collision suffix preserves lexical ordering
- [ ] T013 Checkpoint in `src/pipyer/runner/checkpoint.py`: atomic write (temp + flush + fsync + rename) of `CheckpointSnapshot`, and `reconstruct_checkpoint(event_log_path)` replaying the log via `parse_event_log` incl. corrupt-trailing-line tolerance, keys per R20 (contract: `contracts/runner-api.md`)

**Checkpoint**: Contracts amended with tests, secrets and persistence substrate ready - story implementation can begin

---

## Phase 3: User Story 1 - Run a validated workflow end to end (Priority: P1) 🎯 MVP

**Goal**: `pipyer run` executes a validated single-cell workflow: sequential steps, `each` with positional alignment, skip-on-upstream-failure, budget halt as a recorded event, cost capture, run directory with log/checkpoint/record/summary.

**Independent Test**: stub-model workflow with mixed-outcome `each` items → per-item results, skip records, budget halt, complete run directory; fixtures 2, 4, 5, 6, 7 pass unskipped.

### Implementation for User Story 1

- [ ] T014 [P] [US1] `file_read`/`file_write` executors in `src/pipyer/runner/components/file_io.py`: formats per config, dry-run-gated idempotent writes (danvas conventions, FR-007), relative write paths resolve under the run's `outputs/`
- [ ] T015 [P] [US1] `shell` executor in `src/pipyer/runner/components/shell.py`: `subprocess.run` with `timeout_s` → `ErrorCategory.timeout`; nonzero exit → `nonzero_exit` with `attempt == 1`, never retried (R19, fixture 5)
- [ ] T016 [P] [US1] `python` executor in `src/pipyer/runner/components/python_step.py`: subprocess isolation (`sys.executable`, script file, JSON over stdin/stdout), same timeout mapping (R19)
- [ ] T017 [P] [US1] `assertions` executor in `src/pipyer/runner/components/assertions.py`: evaluate `Check` list, failures → `assertion_failed` with per-check detail
- [ ] T018 [US1] `llm`/`llm_judge` executor in `src/pipyer/runner/components/llm.py` - the ONLY module importing `pydantic_ai`: alias-driven output mode (tool/native/prompted), bounded validation retries counted as `usage.validation_attempts` (initial+retries, fixture 6 expects 3), error mapping per FR-010 (429→`rate_limited`, HTTP→`provider_error`, non-HTTP→`transport_error`, behavior/incomplete-tool-call→`output_validation_error`, content-filter→`provider_error` with detail), call-time secret resolution with `provider_error`/`secret_resolution_failed` double-fault detail (R15), wall-clock `timeout_s` → `timeout`, usage→cost fields per FR-006, `model_overrides` and `force_invalid_llm_output` hooks (R23)
- [ ] T019 [US1] Component registry in `src/pipyer/runner/components/__init__.py`: component name → executor dispatch; verify `tests/conformance/test_import_boundary.py` still green unmodified (FR-017)
- [ ] T020 [US1] Engine in `src/pipyer/runner/engine.py`: sequential step loop, `each` expansion with positional alignment and `each_expanded` event (emitted at `item_count == 0`, fixture 7), skip-on-upstream-failure with `upstream_failure` skip records keyed by index (fixture 4), budget tracker tripping `max_failures`/`max_failure_rate` into a `run_halted` event with attempted/failed/not_attempted accounting (fixture 2), `ThreadPoolExecutor(settings.concurrency)` item scheduling funneling to the single appender, no automatic in-run retries - transient failures (`rate_limited`, `transport_error`) are recorded and proceed per skip/budget policy, recovery is `--resume --retry-failed` (R25), `interrupt_after_items` hook, terminal `run_finished` + `run.json` + `summary.md` write
- [ ] T021 [US1] Public `run_workflow` in `src/pipyer/runner/__init__.py` per `contracts/runner-api.md`: validate first (same implementation as CLI validate), secrets preflight before run-directory creation raising `SecretResolutionError` (R15), lock acquisition, `run_started` with full config snapshot (test hooks recorded, R23), returns `Run` per data-model.md
- [ ] T022 [US1] Initial `derive_summary` in `src/pipyer/runner/summary.py`: header, totals, cost table, per-step table, failures-and-skips (no silent omissions), declared outputs, `summary_*` output-name convention sections (R21); engine writes `summary.md` from it at terminal status
- [ ] T023 [US1] `pipyer run` command in `src/pipyer/cli.py` per `contracts/run-cli.md`: `--input` YAML-scalar parsing against declared inputs, `--dry-run` delegating to the existing `validate_file()` (one implementation), `--results-dir`, `--json` RunRecord output, exit codes 0/1/2/130 with the R22 status↔exit mapping (completed-with-failures exits 1), SIGINT graceful interruption
- [ ] T024 [P] [US1] CLI conformance tests in `tests/conformance/test_run_cli.py`: dry-run parity with `validate`, exit codes per contract, unknown `--input` key exits 2 pre-run, `--retry-failed` without `--resume` exits 2, no secret values in any output
- [ ] T025 [US1] Remove `@pytest.mark.skip` from fixtures 2, 4, 5, 6, 7 in `tests/conformance/execution/test_execution_fixtures.py` (marker lines only - bodies untouched) and make them pass; any API mismatch is recorded as a review finding, not adapted around (FR-016)

**Checkpoint**: MVP - workflows run end to end on the stub with full evidence; 5 of 8 fixtures green

---

## Phase 4: User Story 2 - Interrupt and resume without recomputation (Priority: P1)

**Goal**: Content-hash resume: completed work skipped on hash match, diff reported, failed items retried only with `--retry-failed`, corrupt trailing line recovered, checkpoint reconstructable.

**Independent Test**: kill a stub batch mid-`each`, resume, verify zero recomputation and the diff report; fixtures 1 and 3 pass unskipped.

### Implementation for User Story 2

- [ ] T026 [US2] Resume in `src/pipyer/runner/resume.py`: locate prior run (`run-id` or lexically-last per R17, `NoPriorRunError` otherwise), replay `events.jsonl` as authority with checkpoint as cross-check (mismatch is a loud error, contract run-directory.md), compute resume diff {skipped, recompute-with-reason inputs|config|workflow, failed_not_retried, failed_retried, lock_reclaimed} (R20), corrupt-trailing-line recovery via `parse_event_log`
- [ ] T027 [US2] Wire resume into `run_workflow` and the engine: `resume=True|run_id` and `retry_failed` kwargs, `run_resumed` event with diff payload, skip hash-matched units, `recomputed_step_count` on `Run`, `file_write` reruns only on hash change (R5, FR-007); CLI `--resume <run-id>|last` and `--retry-failed` flags wired in `src/pipyer/cli.py`
- [ ] T028 [P] [US2] Unit tests in `tests/unit/test_resume.py`: config-only change recomputes only the finalization tail (the brief's v1→v2 pattern), failed items stay failed without the flag and rerun with it, stale-lock reclaim noted in diff, checkpoint/log mismatch raises
- [ ] T029 [US2] Remove skip markers from fixtures 1 and 3 in `tests/conformance/execution/test_execution_fixtures.py` and make them pass (interrupt→resume with `recomputed_step_count == 0`; checkpoint deletion → `reconstruct_checkpoint` equality)

**Checkpoint**: 7 of 8 fixtures green; interrupt/resume contract demonstrated on the stub

---

## Phase 5: User Story 3 - Audit a run from its record (Priority: P2)

**Goal**: The summary is fully derivable from the log alone and byte-stable on regeneration; every unit of work is accounted for.

**Independent Test**: delete `summary.md` from a finished run, regenerate from `events.jsonl`, diff is empty; fixture 8 passes unskipped.

### Implementation for User Story 3

- [ ] T030 [US3] Complete `derive_summary` in `src/pipyer/runner/summary.py`: resume section from `run_resumed` events, recomputed-vs-skipped accounting, byte-stable output (no generation timestamps), every failure/skip listed with category and detail (US3 scenario 2)
- [ ] T031 [P] [US3] Unit tests in `tests/unit/test_summary.py`: regeneration byte-equality against a saved log, `summary_*` convention renders the declared object and ignores non-object values, halted and interrupted runs render their reason
- [ ] T032 [US3] Remove the skip marker from fixture 8 in `tests/conformance/execution/test_execution_fixtures.py` and make it pass (summary from log alone, run id + `## ` headers)

**Checkpoint**: All 8 fixtures green unskipped (SC-001); engine feature-complete

---

## Phase 6: User Story 4 - The acceptance run: re-grade T2 (Priority: P1, feature exit)

**Goal**: The evidence-producing benchmark: express T2 grading as a workflow, run live with interrupt/resume, produce the layered comparison record for cross-session review.

**Independent Test**: SC-002/003/004/007 verified from the run record; SC-008 review arbitrated by the user, never self-graded.

### Implementation for User Story 4

- [ ] T033 [P] [US4] Author `workflows/gradebot-t2/workflow.yaml` and `workflows/gradebot-t2/prompts/` (adapt the Feature 001 GradeBot fixture, R24): declared inputs for corpus dir, point weights and deduction parameters from `t2-config.json` values (data, not code - FR-020), baseline file paths, PII-free annotations file path; alias pinned to the archived v2 model with explicit `output_mode` (FR-023); collect → per-problem `shell` harness (`each`) → rubric `llm` grading (`each`) → compare → `file_write` feedback and comparison record; corpus arithmetic verified at analyze review (finding U2): the corpus contains exactly the 47 graded students - the 3 absent students have no submissions directory and no rows in the baseline's 188, so they enter only via roster annotations; the empty-submission path is exercised by present students who skipped problems (9 students submitted fewer than 4 per the filesystem; filesystem shows 179 student×problem pairs with code vs the notes' 177 - the baseline grading CSV's own per-row accounting is truth, pin the exact no-submission row set from it when authoring the collect step)
- [ ] T034 [P] [US4] Write `workflows/gradebot-t2/compare.py` (FR-021/FR-022): per-entry exact-match vs raw-v2 and published baselines separately, quantized-delta implied-cause lookup (0.12 = rubric item flip, 0.20 = execution penalty), known-patched tags, academic-integrity override compared against graded score and annotated (never reconciled), three-category classification, statistics object declared as workflow output `summary_agreement` (R21) including the unexplained-above-floor figure
- [ ] T035 [US4] Stub-model rehearsal: `pipyer validate workflows/gradebot-t2/workflow.yaml` clean; full pipeline smoke on a synthetic 3-student corpus fixture in `tests/fixtures/gradebot_t2_smoke/` (no PII) exercising compare.py end to end via `model_overrides`
- [ ] T036 [US4] Execute the acceptance run per `quickstart.md` scenario 6: live run against the archived corpus (absolute path inputs, external gitignored results dir), inject mid-batch interruption, resume to completion, verify zero recomputation and 188-entry accounting incl. 3 explicit empty-submission records (SC-002/003/007); record evidence (run ids, totals, agreement statistics, deviations) in `specs/002-workflow-runner/acceptance-evidence.md`
- [ ] T037 [US4] Submit the comparison record to cross-session review (SC-008): user arbitrates "does the runner grade credibly"; record the verdict and any findings in `specs/002-workflow-runner/acceptance-evidence.md` - this task is done only when the user has ruled

**Checkpoint**: Feature exit evidence exists and has passed (or recorded findings from) the named gate

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: Quality gates and closure

- [ ] T038 [P] Quality gates (SC-006): `uv run ruff format --check src tests`, `uv run ruff check src tests`, `uv run ty check`, full `uv run pytest` green; fix fallout
- [ ] T039 [P] Run quickstart.md scenarios 1-5 end to end as written; correct the doc where reality diverged
- [ ] T040 Verify frozen-contract discipline for the change set: `git diff` shows fixture bodies untouched (skip-marker lines only), `test_import_boundary.py` unmodified, schema diffs limited to R16's two fields + version bump; write `specs/002-workflow-runner/exit-notes.md` with carried items for Feature 003 (stability measurement evidence, the 1.7%/17.5% numbers, review-and-patch tail candidacy)

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 → Phase 2 → user stories. US1 (Phase 3) blocks US2 (needs engine + events). US2 blocks the resume half of US4. US3 needs US1's summary skeleton (T022) only. US4 needs US1+US2+US3 complete (the live demonstration exercises all of them).
- Phase 7 last; T040 depends on everything.

### Key task-level dependencies

- T006/T007 are one change set (constitution VI); T008 follows T006.
- T009→T020 (appender before engine); T011→T013/T020 (keys/hashes before checkpoint and engine); T018 needs T004 (secrets) and T006 (output_mode).
- T021 needs T004, T009, T011, T020. T023 needs T021. T025 needs T014-T023.
- T026/T027 need T013, T020, T021. T029 needs T026-T027.
- T030 extends T022. T036 needs T033-T035 plus all 8 fixtures green.

### Parallel Opportunities

- Phase 2: T004+T005 ∥ T006-T008 ∥ (after T002) T009/T011 scaffolds; T010, T012 alongside their modules.
- Phase 3: T014, T015, T016, T017 all [P] (separate component files); T018 parallel to them once T004/T006 land; T024 parallel to T023 review.
- Phase 6: T033 ∥ T034.

## Parallel Example: User Story 1

```text
# After Phase 2 completes, launch the deterministic component executors together:
T014 file_io.py | T015 shell.py | T016 python_step.py | T017 assertions.py
# T018 llm.py in parallel once secrets (T004) and schema (T006) are in.
```

## Implementation Strategy

MVP is Phase 1-3 (US1): workflows run end to end on the stub with five fixtures green - already a usable `pipyer run`. Then US2 (resume) and US3 (audit) complete the engine and the fixture suite. US4 is deliberately last and gated: rehearse on the PII-free smoke corpus (T035) before spending live tokens (T036), and the feature does not exit on self-assessment - T037 ends with the user's ruling at cross-session review.
