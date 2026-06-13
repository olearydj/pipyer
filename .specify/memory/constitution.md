<!-- Sync Impact Report
- Version change: 2.1.0 → 2.2.0
- Amendment (2026-06-12): Governance gains the contracts-versus-implementation sweep as a standing feature-exit review item. Evidence: two post-acceptance external review rounds on Feature 002 found their findings exclusively in contract/implementation seams that design-level review does not reach. MINOR bump: materially expanded guidance.
- Prior entry: 2.0.0 → 2.1.0
- Amendment (2026-06-11, owner toolchain and secrets directives):
  - Operational Constraints, stack: added uv_build backend, typer for CLIs, ruff for format/lint, ty for type checking (owner standards; rationale and reference implementations recorded in feature-001 research R13).
  - Operational Constraints, secrets: environment-only replaced by the household 1Password pattern (op read with env fallback, provider chain auto/1password/env), shipped twice in twc-bridge and danvas (research R14). Load-bearing rule unchanged: never in workflow files or run records; provenance (which provider) recordable, value never. MINOR bump: materially expanded guidance, no principle changed.
- Prior entry: 1.1.0 → 2.0.0
- Amendment (2026-06-10, post-feature-001-spec review): removed specification-level detail now owned by docs/sprint-01/SPEC.md sections 5-7 and specs/001-pydanticai-spike-contracts/spec.md:
  - Principle II: per-item mechanism enumeration (FR-013 guarantees uniformity by construction)
  - Principle III: record formats and cost-field list (FR-015, FR-016)
  - Principle V: restated execution-semantics list (SPEC section 6 bound by reference; FR-017)
  - Principle VII: append-friendliness and entity-ID clauses (FR-016, US3)
  - Development Workflow: falsification clause (FR-019), item-failure and resume rules (US3, SC-006, SPEC section 6), stale-workflow elaboration (US2, FR-010) MAJOR bump: backward-incompatible removal of normative text. Rationale: the constitution holds only what survives a runner rebuild; mechanism lives in the contracts and feature specs. Triplicated normative text is the documented drift failure mode.
- Prior entry: 1.0.0 → 1.1.0 (Principle II determinism fix; uniformity guarantee added)
- Amendment (2026-06-10, post-ratification review):
  - Principle II: replaced the determinism clause, which as written forbade `each` fan-out (item count is necessarily a function of input data, e.g. how many students submitted). New wording separates the three guarantees: step graph from workflow alone; fan-out from workflow plus input data; nothing from model output. Also added the uniformity-across-items guarantee (consistency is a first-class driver per SPEC section 2; the HW1 fan-out episode is the motivating evidence). MINOR bump: materially expanded guidance.
- Prior entry: (template) → 1.0.0 (initial ratification)
- Modified principles: all template placeholders replaced (initial adoption)
  - I. Directing, Not Delegating
  - II. Deterministic Topology, Probabilistic Components
  - III. Three Paradigms Plus Measurement
  - IV. Workflows Are Data, Not a Language
  - V. Boring Infrastructure
  - VI. Contracts Are the Product
  - VII. Build by Extraction for Real Consumers
- Added sections: Operational Constraints; Development Workflow & Quality Gates
- Removed sections: none
- Templates:
  - ✅ .specify/templates/plan-template.md (Constitution Check gates synced to v2.2.0)
  - ✅ .specify/templates/tasks-template.md (conformance-test mandate and exit sweep noted)
  - ✅ .specify/templates/spec-template.md (no changes required; already aligned)
  - ✅ CLAUDE.md (pointer to constitution added)
  - N/A .specify/templates/commands/ (directory not present)
- Deferred TODOs: none -->

# Pipyer Constitution

Pipyer is a deterministic orchestration tool: the workflow controls what happens; the model works inside the steps. This constitution binds all features, plans, and implementations. Source material: `docs/sprint-01/SPEC.md` (consolidated 2026-06-10), `docs/sprint-01/BACKLOG.md`, `docs/sprint-01/SPIKE.md`.

## Core Principles

### I. Directing, Not Delegating

Pipyer executes human-authored workflows; it MUST NOT decide what happens next. No autonomous control flow, no agent-selected steps, no workflow rewriting at runtime (ADR-001). Agents remain the discovery and authoring environment and MAY be invoked inside steps (for example `claude -p` as a shell component), but the topology is fixed by the workflow. Any feature that would move control-flow decisions from the workflow author to the runner or to a model MUST be rejected: Pipyer resists every feature that would turn it into a meta-agent.

Rationale: interactive agents are excellent at figuring out how to do a task and unreliable at doing it the same way twice. Separating discovery (agent) from replay (runner) is the product.

### II. Deterministic Topology, Probabilistic Components

Same steps, same order, same references every run; component outputs MAY vary. Reproducibility means documented, traceable variation, not identical output.

The step graph and reference resolution MUST be functions of the workflow file alone. Item-level fan-out (`each`) is a function of the workflow plus its input data. Neither MUST ever be a function of model output: no LLM result may determine which steps run, in what order, or over which items.

Within a batch, every item MUST be processed identically, with per-item evidence. Uniformity across items is a first-class guarantee, not a side effect.

### III. Three Paradigms Plus Measurement

Three layers with fixed responsibilities, plus an evidence layer around all of them (ADR-002):

- Declarative data defines the shape: steps, order, parameters.
- Imperative code (Python, shell) does deterministic work.
- LLMs supply judgment inside steps: reading, scoring, matching, drafting.
- Evidence layer: every run records inputs, outputs, failures, timing, and cost so processes can be trusted, compared, resumed, and improved.

Every run MUST leave machine-readable and human-readable evidence, with usage and cost recorded by default. Record formats and fields are owned by the contracts (SPEC sections 5-6), not this document. The boundaries exist so each layer stays independently replaceable; features that blur them MUST be rejected.

### IV. Workflows Are Data, Not a Language

Workflows are schema-validated data, never a language (ADR-004). The canonical form is a Pydantic-defined schema with two equal authoring surfaces: YAML (`safe_load` then `model_validate`, nothing more) and direct Python construction. Non-negotiable rules:

- No templating, expressions, conditionals, or loops in workflow files.
- References are dotted paths in mapping positions only (`inputs: {test_output: steps.run_tests.stdout}`).
- Prompts live in prompt files with named placeholders bound by explicit input maps.
- Transformations are Python steps.

Breach signal: wanting an expression or filter in a workflow file. The answer is a Python step. Workflows MUST remain human-first (a person can read and author one directly) and agent-friendly (schema validation gives agents a tight authoring loop).

### V. Boring Infrastructure

The runner does six things: parse, validate, execute, persist, resume, report. Intelligence lives in the user, the workflow design, and the components. Cleverness in the runner (implicit behavior, magic defaults, hidden state) MUST be rejected in favor of explicit, recorded behavior. The execution semantics in SPEC section 6 are binding; this document does not restate them.

### VI. Contracts Are the Product

The durable intellectual property is the workflow schema, the run-record schema, and their conformance tests. The runner is deliberately disposable and rebuildable from the contracts as models and tooling improve. Therefore:

- Schema changes MUST land with conformance-test changes in the same change set.
- Conformance tests (SPEC section 7) MUST be written before or alongside the runner, never after.
- The durability hierarchy governs design care: results and evidence > intent (playbooks, rubrics) > workflow files > runner.

### VII. Build by Extraction for Real Consumers

A feature enters scope only when a named consumer needs it (ADR-005). V1 consumers: the DEMA-LLM experiment runner, GradeBot batch grading, and twc-bridge discovery passes; Pipyer inherits their deadlines. Generality is earned, not speculated. When infrastructure work crowds out consumer-serving runs, stop and ship a consumer. Campaign semantics are deferred (ADR-006).

## Operational Constraints

- Stack: Python 3.12+, Pydantic v2, PydanticAI current stable. Dependencies are managed with `uv` exclusively; `pip` and `uv pip` MUST NOT be used. Build backend is `uv_build`. CLIs are built with typer; formatting and linting are `ruff format` / `ruff check`; type checking is `ty`.
- PydanticAI is the LLM substrate candidate (ADR-003); the narrowed capability spike in `docs/sprint-01/SPIKE.md` is the entry gate for implementation. Pipyer owns artifact and evidence semantics only; PydanticAI owns model-call mechanics. Pipyer MUST NOT become a PydanticAI agent-spec wrapper.
- Secrets (provider API keys) are resolved at call time via the household 1Password pattern - `op read` with environment-variable fallback (provider chain `auto`/`1password`/`env`). Workflow files and run records MUST NOT contain credentials; run records MAY record which provider supplied a credential, never its value.
- Local-first: no hosted services are required to run.
- Out of scope (absent amendment): campaign state machines, review queues, status workflows, template or expression languages, autonomous control flow, UI/dashboard, scheduler, hosted anything. HTTP and human-checkpoint components are deferred. Pipyer MAY integrate with tools in these categories; it does not become them.

## Development Workflow & Quality Gates

- Feature order is binding per `docs/sprint-01/BACKLOG.md`; each feature gates the next (001 spike and contracts → 002 GradeBot slice → 003 DEMA runner → 004 twc-bridge pass).
- Every feature plan MUST pass the Constitution Check gates in the plan template before Phase 0 research and again after Phase 1 design. Violations require a Complexity Tracking entry justifying why no simpler alternative suffices.
- Nothing executes unvalidated: workflows MUST validate fully before execution, in every feature, forever.

## Governance

This constitution supersedes all other practices for Pipyer. The full design record (six ADRs) lives in the Obsidian vault project `projects/pipyer/`; the binding digest is SPEC section 4.

- Amendment procedure: any change to principles or constraints requires a documented rationale, an updated or new ADR when a settled decision changes, a version bump per the policy below, and propagation to `.specify/templates/` and dependent specs and plans in the same change.
- Versioning policy: MAJOR for backward-incompatible removals or redefinitions of principles; MINOR for new principles or materially expanded guidance; PATCH for clarifications, wording, and non-semantic refinements.
- Compliance review: every PR and every plan's Constitution Check MUST verify conformance with Principles I-VII. The named breach signals (language creep, wrapper drift, platform trap, silent omission of failures) are standing review checklist items.
- Contracts-versus-implementation sweep: feature exit review includes a mechanical pass over every promise in the feature's contract documents - each field, validation, bound, and output line checked against observed code behavior, never assumed from the design record. Rationale: both post-acceptance review rounds of Feature 002 found their defects exclusively in these seams (promised event fields left empty, a promised validation not performed, a promised timeout not enforced, promised totals fields absent). Design-level review catches decision drift; only a promise-by-promise sweep catches implementation drift.
- Runtime development guidance lives in `CLAUDE.md` at the repository root.

**Version**: 2.2.0 | **Ratified**: 2026-06-10 | **Last Amended**: 2026-06-12
