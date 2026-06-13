# Implementation Plan: PydanticAI Spike and Contracts

**Branch**: `001-pydanticai-spike-contracts` (no git branch created; spec directory is the feature identifier) | **Date**: 2026-06-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-pydanticai-spike-contracts/spec.md`

## Summary

Two deliverables, strictly in order. First (001a), a narrowed capability spike producing executed-code evidence on the PydanticAI boundary: usage capture into the per-step record shape, validation-retry accounting, error shapes mapped to the taxonomy, and the three boundary reviews (batch orchestration, evals, graph/durable execution), concluding with one of four outcomes. Second (001b), the two durable contracts as code: the workflow schema and run-record schema as Pydantic models with validation as the dry-run, a deterministic canonical serialization that single-sources surface equality, workflow hashing, and resume matching, a conformance suite over SPEC section 7, a minimal `pipyer validate` command, and the GradeBot workflow as the first fixture with the ADR-004 falsification census.

Technical approach in one line: the contract modules (`schema/`, `records/`, `canonical.py`, `validation.py`) never import the substrate - a permanent, conformance-tested guard. In this feature PydanticAI appears only in disposable spike code; from Feature 002 on it additionally lives inside the `llm` component, which sits outside the guarded modules by design (R10).

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Pydantic v2, PyYAML (`safe_load` only), and typer (CLI, R13) for the product code; PydanticAI current stable confined to a `spike` dependency group in this feature. Managed with `uv` exclusively; build backend `uv_build`; lint/format with ruff, type checking with ty (dev group, R13).

**Storage**: Files only - YAML workflow files, markdown prompt files, JSONL event logs, JSON checkpoint snapshots, markdown run summaries. No databases, no services.

**Testing**: pytest (conformance suite under `tests/conformance/`); execution-behavior fixtures authored with expected outcomes and marked for Feature 002.

**Target Platform**: Local macOS/Linux, library plus minimal CLI entry point.

**Project Type**: Single project (library + CLI).

**Performance Goals**: Dry-run validation of a typical workflow (tens of steps) completes perceptibly instantly (<1s). No other performance targets; nothing in this feature executes batches.

**Constraints**: Local-first; secrets resolved at call time via the household 1Password pattern - `op read` with environment fallback (R14) - and never stored in workflow files or run records; spike provider spend small (one hosted provider, one local model, deterministic stub elsewhere); contracts package must not import the substrate.

**Scale/Scope**: Workflows of tens of steps; batches of tens to low hundreds of items (a class of submissions, a DEMA matrix); two schemas, ~12 conformance areas, one CLI command, six spike artifacts plus a report.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates derived from `.specify/memory/constitution.md` v2.2.0:

- [x] Directing, not delegating (I): no autonomous control flow, agent-selected steps, or runtime workflow rewriting introduced. The schema cannot express any of them; the spike's graph review (FR-007) explicitly evaluates whether graph primitives would compromise this.
- [x] Deterministic topology (II): step graph and reference resolution are functions of the workflow file alone; `each` fan-out of workflow plus input data; nothing of model output. Uniformity across items is guaranteed by construction (FR-013: no per-item variation mechanism exists in the schema).
- [x] Three paradigms plus measurement (III): contracts define machine-readable plus human-readable evidence with usage and cost recorded by default (FR-014 to FR-016); record formats are owned by these contracts, as the constitution requires.
- [x] Workflows are data (IV): no templating, expressions, conditionals, or loops are representable (FR-012); dotted-path references in mapping positions only; prompts in prompt files with explicit input maps; the GradeBot fixture plus falsification census (FR-018, FR-019) is this gate's proof obligation.
- [x] Boring infrastructure (V): no implicit behavior, magic defaults, or hidden state; SPEC section 6 semantics are encoded in the schemas and conformance fixtures, not reinterpreted. Resolution R5 (resume reruns emerge from hash semantics, no special-case flag) is this principle applied.
- [x] Contracts are the product (VI): the schemas land with their conformance tests in the same change set (FR-017); execution-behavior fixtures are authored before the runner exists.
- [x] Build by extraction (VII): every deliverable traces to the three named consumers; the GradeBot fixture is consumer one's workflow verbatim; the six open decisions are resolved against consumer needs, not speculation (research.md R1-R6).
- [x] Operational constraints: Python 3.12+, Pydantic v2, `uv` only; secrets via the R14 1Password chain with env fallback; local-first; the ADR-003 spike is sequenced as the entry gate (001a before 001b); wrapper drift guarded by a permanent import boundary on the contract modules (substrate confined to `spike/` in this feature; the contract modules are substrate-free forever, R10).
- [x] Contracts-versus-implementation sweep: contract promises are mechanically checked against implementation behavior before feature exit; drift is fixed in code or corrected in the contract.

**Post-design re-check (after Phase 1)**: PASS. The data model introduces no per-item variation surface, no expression types, no substrate imports in contract entities; the CLI contract validates and never executes; the checkpoint decision (R6) keeps the event log authoritative, preserving the durability hierarchy.

## Project Structure

### Documentation (this feature)

```text
specs/001-pydanticai-spike-contracts/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: R1-R10 decisions
├── data-model.md        # Phase 1 output: entities, fields, validation rules
├── quickstart.md        # Phase 1 output: validation scenarios
├── contracts/           # Phase 1 output
│   ├── workflow-schema.md
│   ├── run-record-schema.md
│   └── validate-cli.md
├── spike-report.md      # 001a deliverable (written during implementation, not by /speckit-plan)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
pyproject.toml               # uv-managed; deps: pydantic, pyyaml; group spike: pydantic-ai
src/pipyer/
├── __init__.py
├── schema/
│   ├── __init__.py
│   ├── workflow.py          # Workflow, Step, Settings, MatrixDimension, ModelAlias
│   ├── components.py        # per-component config models (file_read, file_write, shell,
│   │                        #   python, llm, llm_judge, assertions)
│   └── refs.py              # dotted-path reference type and parsing
├── records/
│   ├── __init__.py
│   ├── step_result.py       # StepResult, UsageCost, StepError + error taxonomy
│   └── run.py               # RunRecord, CheckpointSnapshot, JSONL event framing
├── canonical.py             # canonical JSON serialization + workflow hash (one definition)
├── validation.py            # dry-run: model_validate + cross-checks (refs, prompts, aliases)
├── prompts.py               # prompt file loading, placeholder extraction
└── cli.py                   # `pipyer validate` entry point

tests/
├── conformance/
│   ├── test_workflow_schema.py     # valid/invalid schema areas
│   ├── test_references.py          # dangling dotted paths, unbound placeholders
│   ├── test_canonical.py           # dual-surface byte equality, hash stability
│   ├── test_run_records.py         # StepResult/RunRecord representability areas
│   └── execution/                  # authored fixtures + expected outcomes, marked
│       └── test_execution_fixtures.py    #   xfail/skip until Feature 002's runner
└── fixtures/
    ├── valid/                      # minimal valid workflows
    ├── invalid/                    # one file per invalid-workflow conformance area
    └── gradebot/
        ├── workflow.yaml           # YAML surface
        ├── construct.py            # direct Python construction surface
        └── prompts/
            └── grade_submission.md

spike/                       # 001a evidence code - disposable by design
├── 01_usage_capture.py
├── 02_retry_accounting.py
├── 03_error_shapes.py
├── 04_gradebot_skeleton.py
├── 05_evals_review.py
└── 06_graph_review.py
```

**Structure Decision**: Single project. `src/pipyer/schema/` and `src/pipyer/records/` are the product (the two contracts); `canonical.py` is deliberately one module because the canonical serialization is one definition with three jobs (equality, hash, resume matching). `spike/` sits outside `src/` and outside the package: it is evidence, not product, and is the only place PydanticAI may be imported in this feature. The spike report lands in the feature directory, not in `spike/`, because the report is a durable deliverable while the code is not.

## Complexity Tracking

No constitution gate is violated; the table is intentionally empty.
