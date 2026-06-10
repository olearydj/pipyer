# Pipyer Base Specification

This is the base specification for Pipyer, consolidated 2026-06-10 from an 18-month design history. It is the source document for spec-kit: use it to generate the project constitution (`/speckit.constitution`) and the feature specs (`/speckit.specify`), transcribing decided content rather than re-exploring it. Design history and evidence live in the Obsidian vault project `projects/pipyer/` (not required reading; this document is self-contained).

## 1. One-Liner

Pipyer is a deterministic orchestration tool that combines the strengths of LLMs as a natural-language interface and reasoning tool with conventional software discipline: the workflow controls what happens; the model works inside the steps.

Plain-English framing: figure out a process once with AI assistance, then replay it with the responsibilities separated. The AI designs and improves the recipes and supplies judgment within steps; Pipyer runs the recipe exactly as written and records everything.

## 2. The Need

Interactive agents are excellent at figuring out how to do a task and unreliable at doing it the same way twice. Once a process works - grading a class, running an experiment matrix, a discovery pass - re-running it through conversation is slow, costly, and inconsistent, and leaves no record that can be audited or trusted.

Observed evidence (forensics across four prior builds by the same author):

- The same execution layer was hand-built four times (GradeBot, DEMA-LLM, twc-bridge, and the CLIDE spec), each time incidentally, under deadline, and without tests. The operational bugs lived in that plumbing: silently diverging duplicate scoring paths, a timeout broken for six months, all-or-nothing caches.
- Experiment tracking by filename suffix (`decisions.openai.tuned.jsonl`, `metrics.A.sqlite`); configuration fragmented across config files, CLI flags, and env vars; no mid-batch resume; no cost roll-up even where cost-per-decision is a primary research metric.
- Agent fan-out over a batch destroyed confidence in results. Verbatim, after grading 14 students with parallel subagents: "The three we did together I'm confident about because you reviewed and refined them. The 11 from agents I'm less confident about." Uniform execution with per-item evidence is the cure.

Two drivers of equal rank:

- Reproducibility: replay, resume, compare.
- Consistency: every item handled identically, with per-item evidence. For batch work over people (grading especially), consistency is the product.

## 3. Philosophy

These principles are constitution material.

1. Directing, not delegating. Pipyer executes human-authored workflows; it never decides what happens next. Agents remain the discovery and authoring environment and may be invoked inside steps, but the topology is fixed by the workflow. Pipyer must resist every feature that would turn it into a meta-agent.
2. Deterministic topology, probabilistic components. Same steps, same order, same references every run; component outputs may vary. Reproducibility means documented, traceable variation, not identical output.
3. Three paradigms plus measurement. Declarative data defines the shape (steps, order, parameters); imperative code (Python, shell) does deterministic work; LLMs supply judgment inside steps (reading, scoring, matching, drafting). Around all three: an evidence layer recording every run (inputs, outputs, failures, cost) so processes can be trusted, compared, resumed, and improved. The boundaries exist so each layer stays independently replaceable.
4. Boring infrastructure. Parse, validate, execute, persist, resume, report. Intelligence lives in the user, the workflow design, and the components.
5. Contracts are the product. The durable intellectual property is the workflow schema, the run-record schema, and their conformance tests. The runner is deliberately disposable and rebuildable from the contracts as models and tooling improve.
6. Build by extraction for real consumers. A feature enters scope only when a named consumer needs it. Generality is earned, not speculated.

## 4. Decision Record (Digest)

Six ADRs are settled. Full text in the vault; binding content here.

- ADR-001 Directing, not delegating. No autonomous control flow, no agent-selected steps, no workflow rewriting at runtime.
- ADR-002 (amended) Three paradigms plus measurement. YAML/data orchestrates, Python and external tools execute, JSON connects, JSONL plus a markdown summary is the evidence trail.
- ADR-003 (amended) PydanticAI is the LLM substrate candidate. Confirmed in production-adjacent use twice (DEMA-LLM adjudicators, twc-bridge extraction). A narrowed capability spike remains the entry gate: usage metadata capture, retry accounting, error shapes after retry exhaustion. Pipyer must not become a PydanticAI agent-spec wrapper.
- ADR-004 Workflows are schema-validated data, not a language. Canonical form is a Pydantic-defined schema. Two equal authoring surfaces: YAML (`safe_load` then `model_validate`, nothing more) and direct Python construction. No templating, expressions, conditionals, or loops in workflow files. References are dotted paths in mapping positions only (`inputs: {test_output: steps.run_tests.stdout}`). Prompts live in prompt files with named placeholders bound by explicit input maps. Transformations are Python steps. Workflows are human-first (a person can read and author one directly) and agent-friendly (schema validation gives agents a tight authoring loop; in practice agents draft most workflows from prose playbooks).
- ADR-005 Build by extraction, bound to calendar consumers. V1 is defined by three consumers: the DEMA-LLM experiment runner, GradeBot batch grading, and twc-bridge discovery passes. Pipyer inherits their deadlines.
- ADR-006 Batch replay in scope, campaigns deferred. V1 targets run-a-recipe-over-a-collection workflows. Campaign semantics (long-lived stores, status workflows, review queues) are out of scope, but run records must be append-friendly to external stores and items may carry durable entity IDs.

## 5. Contracts

Three artifacts, designed for a future where the runner is rebuilt:

1. Workflow schema: Pydantic models defining workflow metadata, inputs, ordered steps, per-step component config and input maps, `each`, matrix dimensions, settings (concurrency, failure budgets, checkpoint location), and output declarations. Validation of this schema is the dry-run.
2. Run-record schema: a canonical `StepResult` per step execution: run ID, step name, component type, status, output (JSON-compatible), error, timing, token usage and cost when applicable, matrix parameters when applicable, item index and optional durable entity ID when applicable, input references and hashes (provenance), component version. Run-level records carry workflow hash, config snapshot, git commit when available, and totals.
3. Conformance tests over both schemas plus execution behavior (list in section 7).

Run records are written as append-only JSONL (machine) plus a markdown run summary (human). Durability hierarchy governing design care: results and evidence > intent (playbooks, rubrics) > workflow files > runner.

## 6. Execution Semantics (Binding)

- Execution model: load workflow, validate schema, resolve inputs and settings, expand matrix into cells, execute steps sequentially within a cell, expand `each` steps over collections, emit a `StepResult` per execution, append events to the JSONL log, write checkpoint state for resume.
- `each`: positional alignment. `item` is the current value, `index` the position; downstream aligned access is by index, never by item value; duplicate item values must not break lookup. Item failures produce failure-status `StepResult` records, never silent omissions. Downstream steps skip failed items by policy (default: skip with recorded skip-reason).
- Failure budgets: `max_failures` and `max_failure_rate` settings decide when accumulated item failures halt the workflow; the halt itself is a recorded event.
- Matrix: expansion over parameters (models, prompts, thresholds, datasets), never over topology. Matrix parameters attach to every relevant `StepResult`. Cost totals are aggregatable by matrix dimension.
- Resume: content-hash based. Completed work is skipped when workflow, input, and configuration hashes match; failed items are retried only with an explicit flag; diffs against the prior run are reported. Checkpoint writes are atomic (temp file, flush, fsync, rename); the log is single-writer; corrupt trailing JSONL records are detected and handled on replay.
- Retry ownership: the runner owns transport-level retries and run-level retry policy. LLM-internal validation retries are bounded, counted, and reported in the `StepResult`; they must not multiply with runner retries. Side-effecting steps (shell, file writes) are not retried by default. Final writes follow dry-run-gated, idempotent conventions.
- Cost: provider, model, token counts, estimated cost, cost-table version, and whether counts are provider-reported or estimated are recorded by default on every LLM step.

## 7. Conformance Test Areas

Fixtures required for: valid and invalid workflow schemas; dotted-path references to missing steps or fields; duplicate `each` item values; upstream item failure with downstream skip; assertion failure recording; shell nonzero exit without retry; LLM validation failure after bounded internal attempts; resume after interruption without recomputing completed work; corrupt trailing JSONL record handling; checkpoint reconstruction from the event log; failure-budget halt; matrix parameter attachment and cost aggregation by dimension.

## 8. Components

Core v1 components: `file_read`, `file_write`, `shell`, `llm` (PydanticAI), `llm_judge`, `assertions`.

Everything else is composition, not reimplementation: existing CLIs run as `shell` components (the proven pattern: markdown-with-frontmatter payloads, dry-run gates on writes, idempotent posts); agent harnesses may be invoked inside a step (for example `claude -p`) without owning topology; DocETL, Inspect, and DSPy remain post-v1 integration candidates invoked as engines.

### Practicalities

Python 3.12+, Pydantic v2, PydanticAI current stable; managed with `uv` exclusively. Secrets (provider API keys) come from environment variables only; workflow files never contain credentials. Local-first: no hosted services required to run.

## 9. V1 Definition and Success Criteria

V1 is defined by three consumers; a feature enters v1 only when one needs it:

1. DEMA-LLM experiment runner: matrix runs from a single workflow file, run manifests, cost aggregation, run comparison. (DEMA-LLM is a tiered LLM pipeline for semantic data-element reconciliation; its roadmap already specifies this runner as scheduled work.)
2. GradeBot batch grading: `each` over student submissions, shell test execution per item, uniform structured LLM grading with validation, failure budgets, resume, JSONL plus markdown evidence. Logical workflow: collect submissions, run tests per submission, grade each against a rubric prompt with structured output, validate, write per-student feedback and a summary report.
3. twc-bridge discovery pass: orchestration of an external CLI (`twc-bridge` subcommands) as workflow components with a complete pass record; twc-bridge's own database remains the long-lived store.

Success criteria:

- a real DEMA experiment runs end to end from one workflow file producing comparable, cost-annotated run records
- a real GradeBot assignment grades with resume after interruption and per-item evidence
- a twc-bridge discovery pass runs as a workflow
- workflows validate fully before execution; batch runs continue through item failures within budget; interrupted runs resume without recomputing completed work; YAML surface remains a serialization, never a language

## 10. Out of Scope

Campaign state machines, review queues, status workflows. Template or expression languages. Autonomous control flow. UI/dashboard. Scheduler. Hosted anything. HTTP component and human-checkpoint component (deferred). Pipyer may integrate with tools in these categories; it does not become them.

## 11. Risks and Guards

- Platform trap: when infrastructure work crowds out consumer-serving runs, stop and ship a consumer.
- Language creep: wanting an expression or filter in a workflow file is the breach signal; the answer is a Python step.
- Wrapper drift: Pipyer owns artifact and evidence semantics only; PydanticAI owns model-call mechanics.
- Decay between semesters: workflows are replayed months later; dry-run validation and conformance tests must make a stale workflow fail loudly and legibly.

## 12. Open Decisions for Feature 001

Carried from the design history, to be resolved in the first feature's plan:

- where model aliases (for example `models.grader`) are declared and resolved
- whether `skip_if_failed` is step-local or global policy
- whether collection-producing non-`each` steps expose an aligned `items` view
- whether assertion failures count against item and workflow failure budgets
- whether final `file_write` and summary steps rerun by default on resume
- checkpoint format (single JSON snapshot vs reconstruction from the event log, or both)
