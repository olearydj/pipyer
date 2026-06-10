# Pipyer Backlog

Feature sequence for spec-kit. Each feature becomes a branch via `/speckit.specify`, fed from this document and `SPEC.md`. Order is binding: each feature gates the next.

## Feature 001: PydanticAI Spike and Contracts

The entry gate for everything else. Two deliverables, in order.

### 001a: Capability Spike

Per `docs/SPIKE.md`. Narrowed scope (raw calls and structured output are already proven in DEMA-LLM and twc-bridge): usage metadata capture into a `StepResult` shape, validation-retry accounting (internal attempts bounded, counted, visible, and non-multiplying with runner retries), error shapes after retry exhaustion, and the boundary questions (does PydanticAI help beyond the LLM call; do its graph/durable-execution primitives reduce or add runtime complexity; does Pydantic Evals fit the model-eval workflow). Output: a short evidence report and a confirmed or revised LLM-component boundary.

### 001b: Contracts as Code

- Workflow schema and run-record schema as Pydantic models, with validation as the dry-run.
- Conformance test suite per SPEC section 7, written before or alongside the runner.
- The GradeBot workflow expressed in the schema (YAML surface and Python construction, both) as the first conformance fixture. This is deliberately a fresh expression from the logical description in SPEC section 9 under the ADR-004 rules (no templating; dotted-path references; prompt files with explicit input maps). It is also the falsification test: if the workflow cannot be expressed cleanly without expressions, ADR-004 must be revisited before more code is written.
- Resolve the open decisions in SPEC section 12 as part of the feature plan.

Exit criteria: spike report written; both schemas exist with passing conformance tests; the GradeBot fixture validates; ADR-004 confirmed or escalated.

## Feature 002: GradeBot Vertical Slice

The minimal runner: sequential steps, `each` with positional alignment and failure budgets, `shell` / `llm` / `assertions` / `file_read` / `file_write` components, JSONL event log plus markdown run summary, content-hash resume, cost capture. Exit: a real (or realistic synthetic) assignment grades end to end, survives an injected mid-batch interruption, resumes without recomputing completed items, and produces per-item evidence an instructor can audit.

## Feature 003: DEMA Experiment Runner

Matrix expansion over parameters, run manifests (config snapshot, hashes, git commit), cost aggregation by matrix dimension, run comparison output. Exit: a DEMA-LLM experiment runs from one workflow file and two runs are comparable on quality, cost, and latency. (DEMA-LLM lives at `/Volumes/Casa/dev/dema-llm`; its TDD Epic 0.3 specifies this runner's requirements.)

## Feature 004: twc-bridge Discovery Pass

External CLI orchestration as components: a workflow drives `twc-bridge` subcommands (discover, fetch, clean, extract, score, export) for one discovery pass with a complete pass record. Exercises the dry-run-gate and idempotent-write conventions. Exit: one real pass runs as a workflow. (twc-bridge lives at `/Volumes/Casa/dev/twc-bridge`.)

## Deferred (Post-V1)

Campaign semantics (ADR-006). DocETL, Inspect, DSPy integrations. promptfoo adapter. HTTP and human-checkpoint components. Anything not demanded by a named consumer.
