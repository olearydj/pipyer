---

description: "Task list for Feature 001: PydanticAI Spike and Contracts"
---

# Tasks: PydanticAI Spike and Contracts

**Input**: Design documents from `/specs/001-pydanticai-spike-contracts/`

**Prerequisites**: plan.md, spec.md, research.md (R1-R11 + watch item), data-model.md,
contracts/ (workflow-schema, run-record-schema, validate-cli), quickstart.md

**Tests**: Conformance tests are core deliverables of this feature (FR-017; constitution
Principle VI: schema changes land with conformance tests in the same change set, written
before or alongside - never after). Test-authoring tasks precede implementation tasks within
each contracts story and are expected to fail (red) until the implementation lands.

**Organization**: Tasks grouped by user story. Backlog order is binding: US1 (the spike) is
the entry gate and MUST conclude before US2-US4 begin (001a before 001b). US2 and US3 may
then proceed in parallel; US4 needs US2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 (spike evidence), US2 (workflow schema), US3 (run records), US4 (GradeBot
  fixture + falsification)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: uv project, package skeleton, test scaffolding

- [x] T001 Initialize the uv project: `pyproject.toml` with package `pipyer`
  (`requires-python >= 3.12`), build backend `uv_build` (R13, not hatchling), runtime deps
  `pydantic` + `pyyaml` + `typer` (R13), dev group `pytest` + `ruff` + `ty`, dependency group
  `spike` containing `pydantic-ai` (R10), CLI entry point `pipyer = "pipyer.cli:main"`, src
  layout, `[tool.ruff]` config (format + check); run `uv sync` and `uv sync --group spike` to
  produce `uv.lock`
- [x] T002 [P] Create the package skeleton per plan.md: `src/pipyer/__init__.py`,
  `src/pipyer/schema/__init__.py`, `src/pipyer/records/__init__.py`, and empty stubs
  `src/pipyer/canonical.py`, `src/pipyer/validation.py`, `src/pipyer/prompts.py`,
  `src/pipyer/cli.py`
- [x] T003 [P] Create test scaffolding: `tests/conformance/__init__.py`,
  `tests/conformance/execution/__init__.py`, `tests/conftest.py` (fixture-loading helpers for
  `tests/fixtures/`), and directories `tests/fixtures/valid/`, `tests/fixtures/invalid/`,
  `tests/fixtures/gradebot/prompts/`, `spike/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the permanent guard that every later phase must keep green

**⚠️ CRITICAL**: complete before any user story work

- [x] T004 Write the import-boundary conformance test in
  `tests/conformance/test_import_boundary.py`: assert via AST/import inspection that the
  contract modules - `pipyer.schema`, `pipyer.records`, `pipyer.canonical`,
  `pipyer.validation` - import no substrate (`pydantic_ai`). Scoped to contract modules so
  Feature 002's `llm` component never weakens it (R10). Passes trivially now; guards forever.

**Checkpoint**: guard in place - user story phases can begin

---

## Phase 3: User Story 1 - Substrate Capability Evidence (Priority: P1) 🎯 MVP

**Goal**: executed-code evidence answering the four spike areas, concluding one of four
boundary outcomes; the entry gate for all contract work (ADR-003, backlog 001a)

**Independent Test**: the evidence report stands alone - every spike question answered with
observed behavior from executed code, exact substrate version cited; skeleton survives
interrupt/resume (SC-001, SC-007)

⚠️ All spike code is disposable evidence, not product (imports `pydantic_ai` freely; lives
outside `src/`). Provider coverage per clarification: one hosted (env key), one local
(Ollama), deterministic stub elsewhere (R9).

- [x] T005 [US1] Write shared spike helpers in `spike/_common.py`: JSONL event writer
  emitting StepResult-shaped dicts (fields per data-model.md), the vendored household secrets
  resolver per R14 (provider chain `auto`/`1password`/`env`, `op read` with `shutil.which`
  check, `PIPYER_<KEY>_OP_REFERENCE` then conventional env var, returning
  `(secret, provider_name)` - stolen from twc-bridge `secrets.py` / danvas `auth.py`),
  hosted-provider key resolution via that chain, Ollama availability check, deterministic
  stub model factory
- [x] T006 [P] [US1] Write and run `spike/01_usage_capture.py`: structured calls through the
  substrate against hosted + local + stub; capture per-call token counts and cost inputs into
  StepResult-shaped records, including on validation-retry paths; persist observed raw usage
  objects for the report (FR-001)
- [x] T007 [P] [US1] Write and run `spike/02_retry_accounting.py`: strict output schema
  forcing validation retries; demonstrate internal attempts are bounded, countable, visible;
  layer a simulated runner-level retry outside the call and demonstrate the multiplication
  bound (substrate × runner attempts known, capped, recorded as `validation_attempts` and
  `attempt`) (FR-002)
- [x] T008 [P] [US1] Write and run `spike/03_error_shapes.py`: drive retry exhaustion,
  transport failure (unreachable endpoint), and rate limiting (burst, or the documented error
  type if not reproducible on demand); record observed exception/result shapes and map each
  to the R8 taxonomy, flagging any shape the taxonomy cannot represent honestly (FR-003)
- [x] T009 [P] [US1] Write and run `spike/04_gradebot_skeleton.py`: 3 fake submissions, one
  shell-simulated test execution, one structured feedback call per item, per-item JSONL
  records, one forced item failure recorded as failure-status; `--interrupt-after N` and
  `--resume` flags proving resume recomputes zero completed items (FR-005, SC-007); note
  whether the substrate helped with anything outside the per-item call
- [x] T010 [P] [US1] Write and run `spike/05_evals_review.py`: the 2 cases × 2 prompts × 2
  model aliases scenario in the substrate's evals tooling with a judge step and usage
  collection; map concepts to matrix semantics; conclude native / integrate / defer (FR-006)
- [x] T011 [P] [US1] Write and run `spike/06_graph_review.py`: fixed two-step workflow in the
  substrate's graph primitives; inspect state representation; check node-output → StepResult
  mapping and whether durable execution gives deterministic item-level resume; assess threat
  to the workflows-are-data surface; conclude use / ignore for v1 / revisit (FR-007)
- [x] T012 [US1] Write the spike report at
  `specs/001-pydanticai-spike-contracts/spike-report.md`: all four areas answered with
  observed evidence and code snippets, exact substrate version probed, interface
  recommendation for a workflow-configured component (FR-004), error-shape → taxonomy table
  with proposed taxonomy amendments for 001b, and exactly one boundary outcome - standalone
  runner / thin layer / conventions / abandon - with the confirmed or revised LLM-component
  boundary (FR-008, SC-001)
- [x] T013 [US1] Entry-gate decision - cross-session review, never self-graded: when T012
  lands, the implementing session STOPS and brings the spike report to a fresh reviewer (a
  separate session or a context-free reviewer agent given the report and docs/SPIKE.md's
  decision criteria - not the context that produced the evidence), with the user arbitrating.
  Only after that review concurs does this task record GO for 001b in `spike-report.md`. If
  the outcome does not confirm the standalone-runner hypothesis, or the reviewer dissents,
  HALT and escalate the ADR-003 revision before any Phase 4+ work (spec edge case;
  constitution Operational Constraints). Same don't-self-grade reasoning as the census
  (T035), applied to the feature's most consequential decision.

**Checkpoint**: spike report exists, boundary decided - the 001b gate is open (or escalated)

---

## Phase 4: User Story 2 - Author and Validate Workflows as Data (Priority: P2)

**Goal**: the workflow schema with validation as the dry-run, canonical serialization with
one definition for equality/hash/resume, and the `pipyer validate` CLI

**Independent Test**: valid and invalid fixtures through library and CLI - accepted/rejected
with location-named errors; both authoring surfaces byte-identical (SC-003, SC-004)

### Tests for User Story 2 (write first - red until implementation lands)

- [x] T014 [P] [US2] Author workflow fixtures: minimal valid workflows in
  `tests/fixtures/valid/` and one file per invalid area in `tests/fixtures/invalid/` -
  unknown field, dangling step ref, forward ref, self ref, `item` outside `each`, unknown
  model alias, unbound prompt placeholder, unused prompt binding, duplicate step names,
  unsupported `schema_version`, matrix non-list value, empty matrix dimension (R12),
  root-prefixed string failing full grammar match (contracts/workflow-schema.md fixture
  table)
- [x] T015 [P] [US2] Write `tests/conformance/test_workflow_schema.py`: every valid fixture
  accepted; every invalid fixture rejected with the expected location path and error code
  (SC-004); plus the FR-013 tripwire - assert `Step` and the component config models expose
  no per-item override fields (uniformity by construction; guards against future field
  additions eroding it silently)
- [x] T016 [P] [US2] Write `tests/conformance/test_references.py`: full-match Ref grammar
  (data-model.md): reserved roots, backward-only step refs, `item`/`index` scoping,
  root-prefixed non-grammar strings error with the declare-an-input escape-hatch message -
  never silent literals
- [x] T017 [P] [US2] Write `tests/conformance/test_canonical.py`: canonical bytes stable
  across repeated serialization; omitted-vs-explicit defaults produce identical bytes
  (materialization, R7); SHA-256 hash stability; `schema_version` participates in bytes
- [x] T018 [P] [US2] Write `tests/conformance/test_validate_cli.py` per
  contracts/validate-cli.md: exit codes 0/1/2, human and `--json` outputs (`loc`, `code`
  fields), deterministic document-order errors, library parity (CLI reports exactly the
  validation API's errors), and zero execution side effects

### Implementation for User Story 2

- [x] T019 [P] [US2] Implement `src/pipyer/schema/refs.py`: Ref type, reserved-root grammar,
  full-match classification (Ref / literal / root-prefixed error), parse to segments
- [x] T020 [P] [US2] Implement `src/pipyer/schema/components.py`: discriminated component
  config models - `file_read`, `file_write`, `shell` (static argv list, stdin/env input
  delivery), `python` (R11), `llm`, `llm_judge` (default verdict schema), `assertions` with
  `Check` (closed op enum) - all `extra="forbid"`, field rules per data-model.md
- [x] T021 [US2] Implement `src/pipyer/schema/workflow.py`: `Workflow`, `InputDecl`,
  `ModelAlias` (R1: alias targets may be Refs to inputs/matrix), `Settings` (R2: no per-step
  skip override exists), `Step` (`each` binding), matrix dimensions; `schema_version`
  required; `extra="forbid"` (depends on T019, T020)
- [x] T022 [US2] Implement `src/pipyer/canonical.py`: deterministic canonical JSON (UTF-8,
  sorted keys, compact separators, defaults materialized, schema_version included) and
  SHA-256 workflow hash over exactly those bytes - the single definition (R7) (depends on
  T021)
- [x] T023 [P] [US2] Implement `src/pipyer/prompts.py`: prompt file loading and named
  placeholder extraction (for binding checks)
- [x] T024 [US2] Implement `src/pipyer/validation.py`: dry-run cross-checks 1-10 from
  data-model.md (ref resolution incl. backward-only and `each` scoping, root-prefix errors,
  alias existence and target resolution, placeholder coverage in both directions with prompt
  paths resolved relative to the workflow file / explicit base dir, non-empty matrix
  dimensions (R12), outputs resolution, supported `schema_version`), producing
  location-pathed, coded, document-ordered errors (depends on T021, T022, T023)
- [x] T025 [US2] Implement `src/pipyer/cli.py` as a typer app (R13, annotated-options style
  per the danvas reference): `pipyer validate <file> [--json]` per the CLI contract - exit 0
  with name/schema-version/hash line, exit 1 with error list via `typer.Exit(1)`, exit 2 for
  I/O and YAML-safety failures (typer's native usage-error code); `yaml.safe_load` then
  `model_validate`, nothing more (depends on T024)

**Checkpoint**: T015-T018 all green; US2 independently demonstrable via quickstart
Scenarios 2-3 (minus the GradeBot fixture, which is US4)

---

## Phase 5: User Story 3 - Run Evidence Contract (Priority: P3)

**Goal**: the run-record schema - StepResult, run-level records, JSONL framing, checkpoint
snapshot - with every conformance scenario representable

**Independent Test**: record instances for every scenario in the contract table validate; no
runner involved (SC-006)

**Note**: may run in parallel with Phase 4 after the Phase 3 gate (different modules); the R8
taxonomy must first absorb any amendments from the spike report (T012).

### Tests for User Story 3 (write first - red until implementation lands)

- [x] T026 [P] [US3] Write `tests/conformance/test_run_records.py` per
  contracts/run-record-schema.md: StepResult for every status × component; a failure record
  per taxonomy category (closed enum - unknown rejected); skip with `upstream_failure`
  reason; LLM result without usage rejected; `counts_source: estimated` without cost table
  valid (local-model case); matrix params attached and aggregation totals - computed inline
  in the test, no product aggregation function exists in this feature - matching
  hand-computed values; duplicate item values with distinct `item_index`; a
  `CheckpointSnapshot` instance validates (derived-state schema only; reconstruction is
  Feature 002); run-level record with and without `git_commit`; corrupt trailing JSONL line
  detectable; `estimated_cost` serializes as a string-form decimal, never a float
  (penny-drift guard for cost aggregation)
- [x] T027 [P] [US3] Author execution-behavior fixtures in
  `tests/conformance/execution/test_execution_fixtures.py`, each marked xfail/skip with
  reason "Feature 002 runner": resume-after-interruption without recompute, failure-budget
  halt event, checkpoint reconstruction from event log, downstream skip on upstream item
  failure, shell nonzero exit without retry, LLM validation failure after bounded attempts,
  empty `each` collection yielding zero per-item records recorded explicitly (R12), markdown
  run summary derived from a fixture event log alone (FR-016) (FR-017 - present and counted,
  not silently absent)

### Implementation for User Story 3

- [x] T028 [P] [US3] Implement `src/pipyer/records/step_result.py`: `StepResult`,
  `UsageCost` (`counts_source`, `validation_attempts`), `StepError` with the closed R8
  taxonomy enum, amended per the spike report's error-shape findings (T012)
- [x] T029 [US3] Implement `src/pipyer/records/run.py`: `RunRecord` (config snapshot, never
  secrets), `CheckpointSnapshot` (derived, log-authoritative, R6), JSONL event models
  (`run_started`, `step_result`, `run_halted`, `run_finished`) with line
  serialization/framing and corrupt-trailing-line detection (depends on T028)

**Checkpoint**: T026 green, T027 fixtures authored; US3 independently demonstrable

---

## Phase 6: User Story 4 - GradeBot Fixture and the Falsification Test (Priority: P4)

**Goal**: the GradeBot workflow expressed freshly under ADR-004 rules in both surfaces as the
first conformance fixture, plus the two-census falsification verdict

**Independent Test**: both surfaces validate byte-identically; censuses (author +
context-free reviewer) agree no code step exists only because the schema forbids expressions
(SC-003, SC-008)

**Depends on**: US2 complete (schema + validation + canonical). Watch item on file
(research.md): the test-runner step needing the submission path in argv is the predicted
census stress point - if it trips, the compliant relaxation is a Ref as an argv list element,
not an ADR-004 failure.

- [x] T030 [P] [US4] Write the rubric prompt file
  `tests/fixtures/gradebot/prompts/grade_submission.md` with named placeholders only (e.g.
  rubric, test_output, submission) - every placeholder to be bound by the explicit input map
- [x] T031 [US4] Express the GradeBot workflow in
  `tests/fixtures/gradebot/workflow.yaml` - fresh from the SPEC section 9 logical
  description, not ported: collect submissions (`python`), run tests per submission
  (`shell` + `each`), grade each against the rubric (`llm` with model alias and output
  schema), validate grades (`assertions`), write per-student feedback (`file_write` + `each`),
  summary report (`python` then `file_write`); `models` block per R1, failure budgets in
  `settings`; zero forbidden constructs (depends on T030)
- [x] T032 [US4] Express the same workflow via direct construction in
  `tests/fixtures/gradebot/construct.py` (the second authoring surface) (depends on T031)
- [x] T033 [US4] Write `tests/conformance/test_gradebot_fixture.py`: both surfaces validate;
  byte-identical canonical serialization and equal workflow hash; mechanical sweep confirms
  zero templating/expression/conditional/loop constructs (SC-003) (depends on T031, T032)
- [x] T034 [US4] Author census: enumerate every code step (`python`/`shell`) in the fixture
  and answer the counterfactual per step - would this step exist if the schema had a template
  language? - recording verdicts and reasoning in
  `specs/001-pydanticai-spike-contracts/exit-notes.md` (FR-019) (depends on T033)
- [x] T035 [US4] Independent census: hand the validated fixture to a context-free reviewer (a
  fresh agent with only the fixture and the single adversarial question "which of these code
  steps exist only because the schema forbids expressions?"); reconcile against the author
  census in `exit-notes.md`. Agreement with zero failing steps → falsification PASS
  (SC-008). Any failing step or disagreement → HALT and escalate ADR-004 - reading an
  argv-position trip per the watch item (narrow compliant relaxation) rather than as ADR-004
  failing (depends on T034)

**Checkpoint**: falsification verdict recorded; all four stories independently demonstrated

---

## Phase 7: Polish & Feature Exit

- [x] T036 Run every quickstart.md scenario end to end (conformance suite, GradeBot
  validation, invalid-fixture rejection with `--json`, spike scripts, R-count, census
  presence) plus the toolchain gates (`ruff format --check`, `ruff check`, `ty check` - R13);
  fix any drift between artifacts and reality
- [x] T037 Finalize `specs/001-pydanticai-spike-contracts/exit-notes.md`: backlog exit
  criteria checked (spike report written; both schemas with passing conformance tests;
  GradeBot fixture validates; ADR-004 confirmed or escalated), a reference to the existing
  vault annotation of the ADR-002 knock-on supersession (annotated 2026-06-11 after the plan
  review - reference it, do not re-flag it as owed; R11), taxonomy amendments from the spike
  folded into R8/records or explicitly deferred

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Setup (P1) → Foundational (P2) → US1 spike (P3, GATE)
                                      │
                          ┌───────────┴───────────┐
                          ▼                       ▼
                    US2 workflow schema      US3 run records
                          │                       │
                          ▼                       │
                    US4 GradeBot + census ◄───────┘ (exit notes reference both)
                          │
                          ▼
                    Polish & Feature Exit
```

- US1 is a hard gate (backlog: 001a before 001b; T013 enforces it)
- US2 ∥ US3 after the gate (disjoint modules; US3's taxonomy waits only on T012's findings)
- US4 requires US2 (validation, canonical) - it does not require US3
- Polish requires all stories

### Within Each Story

- Test/fixture tasks before implementation tasks (red → green)
- `refs.py` and `components.py` before `workflow.py`; `workflow.py` before `canonical.py`
  and `validation.py`; `validation.py` before `cli.py`
- `step_result.py` before `run.py`
- Fixture YAML before construct.py before equality test before censuses

## Parallel Opportunities

```text
Phase 1:  T002 ∥ T003 (after T001)
Phase 3:  T006 ∥ T007 ∥ T008 ∥ T009 ∥ T010 ∥ T011 (after T005)
Phase 4:  T014 ∥ T015 ∥ T016 ∥ T017 ∥ T018, then T019 ∥ T020 ∥ T023
Phase 4∥5: all of Phase 5 may interleave with Phase 4 (different modules)
Phase 5:  T026 ∥ T027 ∥ T028
Phase 6:  T030 may start while US2 finishes; T031-T035 are sequential by design
          (the census chain must not be parallelized away - independence is the point)
```

## Implementation Strategy

MVP first: Phases 1-3 alone deliver the feature's decision value - the spike report and the
boundary verdict (SC-001). The implementing session stops when T012 lands; T013's GO comes
from a cross-session review (fresh reviewer, user arbitrating), never from the session that
produced the evidence. The gate is the entry gate, not a formality - and it is not
self-graded.

Incremental delivery after the gate: US2 yields a usable authoring loop (`pipyer validate`)
on its own; US3 completes the contract pair; US4 is the falsification proof. Each checkpoint
is independently demonstrable via its quickstart scenario. The exit-notes task (T037) closes
the backlog's exit criteria explicitly.

Token of discipline from the constitution: if at any point contract work starts crowding out
the spike's consumer-evidence purpose (platform trap), stop and ship the report.
