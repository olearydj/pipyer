# Implementation Plan: Workflow Runner (GradeBot Vertical Slice)

**Branch**: `002-workflow-runner` | **Date**: 2026-06-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-workflow-runner/spec.md`, brief at `docs/sprint-02/BRIEF.md`, carried planning notes at [planning-notes.md](planning-notes.md)

## Summary

Build `pipyer.runner`: a synchronous execution engine that runs validated single-cell workflows end to end - sequential steps, `each` expansion with positional alignment, failure budgets, content-hash resume against the frozen canonical serialization, append-only JSONL event log with derived markdown summary, and default cost capture on LLM steps. `pipyer run` joins `pipyer validate` in the CLI. The `llm`/`llm_judge` components gain their real PydanticAI implementation (confined behind the import boundary), the spike secrets resolver graduates to `src/pipyer/secrets.py`, and the feature exits by re-grading the archived INSY 3010 T2 corpus and producing a layered comparison record reviewed at the cross-session gate.

The runner API is already pinned by the 8 skip-marked fixtures in `tests/conformance/execution/test_execution_fixtures.py`: `run_workflow(workflow_path, results_dir, **opts) -> Run`, `reconstruct_checkpoint(event_log_path) -> CheckpointSnapshot`, `derive_summary(event_log_path) -> str`. Those fixtures are unskipped, never rewritten; API mismatches are findings for review.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Pydantic v2 (existing), PyYAML, typer (existing CLI), PydanticAI current stable (moves from the `spike` dependency group to runtime deps; imported only inside the `llm` component package)

**Storage**: Filesystem only - run directories under `settings.results_dir` (`<results_dir>/<run_id>/`): append-only JSONL event log, atomic checkpoint JSON, run record, markdown summary, declared outputs. No database, no services (local-first).

**Testing**: pytest; conformance suite in `tests/conformance/` including the 8 pre-authored execution fixtures (unskipped by this feature) and the unmodified `test_import_boundary.py`; deterministic stub model (`TestModel`) for all conformance work; live model spend only in the acceptance run.

**Target Platform**: macOS/Linux developer machine (Darwin primary); air-gap-capable via Ollama aliases (DEMA path constraint carried from Feature 001).

**Project Type**: Single Python package (`src/pipyer`) with a typer CLI; `uv` exclusively, `uv_build` backend.

**Performance Goals**: Correctness over throughput. The acceptance batch is 188 LLM calls; item-level parallelism within an `each` step is bounded by `settings.concurrency` (default 1). No latency targets; the runner must merely not add meaningful overhead to model-call wall time.

**Constraints**: Frozen Feature 001 contracts (schema changes only with conformance tests in the same change set, constitution VI); event log single-writer and authoritative (R6); atomic checkpoint writes; PydanticAI confined to the `llm` component (R10 guard); secrets never in workflow files or run records (R14); student PII never enters the repo; `ruff format` / `ruff check` / `ty check` clean.

**Scale/Scope**: One runner module tree, two component implementations gaining substance (`llm`, `llm_judge`) plus four deterministic components (`file_read`, `file_write`, `shell`, `python`, `assertions`), one new CLI command, one acceptance workflow (GradeBot T2, 47 students × 4 problems).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates derived from `.specify/memory/constitution.md` v2.1.0:

- [x] Directing, not delegating (I): the runner executes the fixed topology; no step selection, no runtime rewriting. The only control flow the runner owns is the decided semantics: skip-on-upstream-failure, budget halt, resume skip - all recorded, none model-driven.
- [x] Deterministic topology (II): step graph from the workflow file alone; `each` fan-out from workflow plus input data; model output never influences which steps run. Items processed uniformly with per-item `StepResult` evidence (the empty-each and duplicate-item fixtures pin this).
- [x] Three paradigms plus measurement (III): components keep the data/code/LLM split; every run leaves the JSONL log and the derived markdown summary; usage and cost recorded by default (FR-006). Record formats stay owned by the Feature 001 contracts.
- [x] Workflows are data (IV): the runner adds no templating, expressions, or conditionals; reference resolution stays the existing dotted-path grammar (`refs.classify`). The comparison record is a `python` step in the GradeBot workflow, not runner machinery (FR-021).
- [x] Boring infrastructure (V): parse, validate, execute, persist, resume, report - nothing else. No magic defaults: budgets, concurrency, timeouts, and resume behavior are explicit settings/flags with recorded outcomes. SPEC section 6 semantics implemented as written.
- [x] Contracts are the product (VI): the two additive schema changes this feature needs (`timeout_s` on LLM configs, `output_mode` on `ModelAlias` - see research R16) land with conformance-test changes in the same change set, and carry the workflow `schema_version` bump to `"2"` per R7's hash-continuity rule (defaults are materialized in canonical bytes, so the additions change every existing hash; the version boundary makes that visible rather than silent). The 8 execution fixtures are the runner's conformance tests, written before the runner (they predate it by a feature).
- [x] Build by extraction (VII): named consumer is GradeBot (consumer one, ADR-005); the acceptance run is a real assignment re-grade, not a demo. Matrix (DEMA) and external-CLI composition (twc-bridge) stay out of scope.
- [x] Operational constraints: Python 3.12+, Pydantic v2, PydanticAI as substrate confined to the `llm` component; `uv` only; secrets via the R14 1Password chain (`src/pipyer/secrets.py`, graduated from spike); local-first - stub model for conformance, Ollama path preserved via alias-configurable output mode.

*Post-Phase-1 re-check (2026-06-11)*: design artifacts introduce no violations. The runner-internal test hooks (`interrupt_after_items`, `force_invalid_llm_output`) are explicit keyword arguments recorded in the run record when used - no hidden state (V). Single-writer lock and preflight secrets check are explicit, recorded behaviors. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/002-workflow-runner/
├── spec.md              # Feature specification (clarified)
├── planning-notes.md    # Carried notes from spec review (secret-failure preflight)
├── plan.md              # This file
├── research.md          # Phase 0 output (decisions R15-R24)
├── data-model.md        # Phase 1 output (runner entities, run directory)
├── quickstart.md        # Phase 1 output (validation scenarios)
├── contracts/           # Phase 1 output
│   ├── runner-api.md    # pipyer.runner public surface (pinned by fixtures)
│   ├── run-cli.md       # pipyer run command contract
│   └── run-directory.md # Run directory layout and file contracts
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/pipyer/
├── schema/              # FROZEN contracts (additive-for-validation changes only, with
│                        #   conformance tests; hash-breaking per R7 → schema_version "2", R16)
│   ├── workflow.py      # + ModelAlias.output_mode (R16)
│   ├── components.py    # + LlmConfig.timeout_s, LlmJudgeConfig.timeout_s (R16)
│   └── refs.py          # unchanged
├── records/             # FROZEN contracts
│   ├── step_result.py   # unchanged (taxonomy stays closed, R15)
│   └── run.py           # unchanged (events, checkpoint, parse_event_log already exist)
├── canonical.py         # unchanged - single definition of workflow identity
├── validation.py        # unchanged - pipyer run --dry-run calls it as-is
├── prompts.py           # unchanged
├── secrets.py           # NEW - graduated from spike/_common.py (R14 chain)
├── runner/              # NEW - the feature
│   ├── __init__.py      # public API: run_workflow, reconstruct_checkpoint, derive_summary
│   ├── engine.py        # execution loop, step scheduling, budget tracking, interruption
│   ├── context.py       # RunContext: resolved inputs, alias table, ref resolution, hashes
│   ├── events.py        # single-writer event log appender + lock (R18)
│   ├── checkpoint.py    # atomic checkpoint write, replay/reconstruction (R6)
│   ├── resume.py        # content-hash matching, diff report, retry-failed policy
│   ├── summary.py       # derive_summary: markdown from event log alone
│   └── components/      # step executors, dispatch by component type
│       ├── __init__.py  # registry: component name -> executor
│       ├── file_io.py   # file_read, file_write (dry-run-gated, idempotent)
│       ├── shell.py     # subprocess, timeout, nonzero-exit mapping
│       ├── python_step.py # subprocess isolation, timeout (R19)
│       ├── assertions.py  # checks evaluation
│       └── llm.py       # ONLY module importing pydantic_ai: llm + llm_judge,
│                        #   output-mode handling, error mapping, usage→cost, stub injection
└── cli.py               # + run command (FR-011); --dry-run delegates to validate

tests/
├── conformance/
│   ├── execution/       # 8 fixtures: skip markers removed, bodies untouched
│   ├── test_import_boundary.py  # unchanged, must stay green
│   ├── test_secrets.py  # NEW - R14 chain conformance (env-only paths; op mocked)
│   ├── test_run_cli.py  # NEW - pipyer run contract
│   └── test_schema_additions.py # NEW - output_mode + timeout_s conformance (VI)
├── unit/                # NEW - runner internals (lock, hashing, summary sections)
└── fixtures/            # existing workflow fixtures + runner-specific additions

workflows/gradebot-t2/   # NEW - acceptance workflow (no PII: corpus by absolute path input)
├── workflow.yaml
├── prompts/             # rubric prompt files
└── compare.py           # python-step script: layered comparison record (FR-021/FR-022)
```

**Structure Decision**: single package; the runner is a subpackage to keep `engine.py` from becoming a monolith, with components isolated so the import boundary stays auditable (exactly one module imports `pydantic_ai`). Contract modules receive only the two new fields - additive for validation, hash-breaking per R7, carried by the `schema_version` bump to `"2"` (R16) - each shipped with conformance tests in the same change set.

## Complexity Tracking

No constitution violations; table omitted.
