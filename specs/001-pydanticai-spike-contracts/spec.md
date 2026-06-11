# Feature Specification: PydanticAI Spike and Contracts

**Feature Branch**: `001-pydanticai-spike-contracts`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "based on the materials in @docs/" - Feature 001 from `docs/BACKLOG.md`, fed by `docs/SPEC.md` (sections 5, 6, 7, 9, 12) and `docs/SPIKE.md`.

This feature is the entry gate for everything else. It has two deliverables, in order: a capability spike producing evidence for the LLM substrate decision (001a), and the two durable contracts as code with their conformance tests and first fixture (001b). No runner is built in this feature; the runner arrives in Feature 002 and is deliberately rebuildable from the contracts produced here.

## Clarifications

### Session 2026-06-10

- Q: Should the workflow and run-record schemas carry explicit schema-version fields from v1? → A: Both schemas, from day one: workflow files declare the workflow-schema version they conform to, and run records declare the run-record schema version they were written under.
- Q: How do workflow authors invoke validation in this feature, before the runner exists? → A: 001 ships a minimal command-line validation entry point (full dry-run, legible errors, failure exit status) alongside the library API; it executes nothing.
- Q: Which providers must the spike exercise for usage and error evidence? → A: One hosted provider, one local model, and the deterministic stub.
- Q: What does "identical canonical form" mean across the two authoring surfaces? → A: Byte-identical output under one defined canonical serialization of the validated model, in the machine layer (JSON per ADR-002), never over either authoring file format. The workflow hash is computed over those same bytes, so one definition serves surface equality, hashing, and resume matching. Key ordering and default materialization are pinned explicitly; the hash-continuity consequence of the default-materialization choice is documented as intended.
- Q: What is the operational test for "expressed cleanly" in the falsification clause? → A: Mechanical validation plus a recorded counterfactual census of every code step ("would this step exist if the schema had a template language?"), performed independently by the fixture's author and a context-free reviewer; verdict and per-step reasoning land in the feature exit notes, and a passing census is retained as the operational definition of the language-creep breach signal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Substrate Capability Evidence (Priority: P1)

As the project architect, I need executed-code evidence of how the candidate LLM substrate behaves on usage capture, retry accounting, and failure handling, plus answers to the four boundary questions, so the LLM component boundary can be confirmed or revised before any contract or runner code is written.

The spike is narrowed: raw calls and structured output are already proven in two production-adjacent codebases and are not re-proven here.

**Why this priority**: The backlog names this the entry gate. The contracts (this feature's second half) and the runner (Feature 002) both depend on knowing where the substrate's responsibilities end and Pipyer's begin.

**Independent Test**: The evidence report can be reviewed standalone: every spike question has an answer backed by observed behavior from executed code, and the minimal grading skeleton runs end to end. No other deliverable is needed to judge it.

**Acceptance Scenarios**:

1. **Given** a structured LLM call that succeeds, **When** it completes, **Then** token counts and cost inputs for that call are captured in a form that maps to the per-step run record, including on validation-retry paths.
2. **Given** a structured call whose output fails validation and triggers internal retries, **When** it succeeds late or exhausts attempts, **Then** the internal attempts are shown to be bounded, countable, and visible, with usage accounted across all attempts.
3. **Given** a runner-level retry policy layered over the component's internal validation retries, **When** both are active, **Then** evidence shows total attempts cannot silently multiply.
4. **Given** retry exhaustion, transport failure, and rate limiting, **When** each occurs, **Then** the observed failure shape is documented and mapped to the run-record error taxonomy.
5. **Given** the four boundary questions (component interface choice, batch orchestration help beyond the LLM call, eval-tooling fit for matrix runs, graph/durable-execution fit), **When** the spike concludes, **Then** the report records a recommendation for each and an overall outcome: standalone runner, thin layer, conventions package, or abandon.
6. **Given** the minimal grading skeleton (3 simulated submissions, simulated test execution, one structured feedback call per submission, one forced item failure), **When** it is run, interrupted, and resumed, **Then** per-item records exist for every item including the failure, the resume does not recompute completed items, and the report states the recommended ownership boundary.

---

### User Story 2 - Author and Validate Workflows as Data (Priority: P2)

As a workflow author (a person writing directly, or an agent drafting from a prose playbook), I can express a batch workflow as plain, readable data in either of two equal authoring surfaces, and have it fully validated before any execution, so a malformed or stale workflow fails loudly and legibly up front rather than midway through a batch.

**Why this priority**: The workflow schema is the first half of the durable contracts - the product's stated intellectual property. Every later feature consumes it.

**Independent Test**: A set of valid and invalid workflow fixtures can be run through the dry-run validation alone (no runner exists yet), through both the library call and the command-line entry point: valid fixtures are accepted, invalid ones are rejected with errors naming the offending element, and both authoring surfaces yield byte-identical canonical serializations.

**Acceptance Scenarios**:

1. **Given** a valid workflow in the data-file surface, **When** it is validated, **Then** it is accepted and a canonical form is produced.
2. **Given** the same workflow built through direct construction in code, **When** it is validated, **Then** its canonical form is identical to the data-file version's.
3. **Given** a workflow whose input map references a missing step or field by dotted path, **When** it is validated, **Then** it is rejected with an error naming the exact reference and where it appears.
4. **Given** a workflow attempting templating, expressions, conditionals, or loops, **When** it is validated, **Then** it is rejected; the schema provides no way to express them.
5. **Given** a prompt file with a named placeholder not bound by the step's explicit input map, **When** the workflow is validated, **Then** it is rejected with an error naming the unbound placeholder.
6. **Given** a workflow file and the command-line validation entry point, **When** it is invoked, **Then** a valid workflow exits with success, an invalid one exits with failure and the same legible errors as the library call, and nothing is executed either way.

---

### User Story 3 - Run Evidence Contract (Priority: P3)

As a consumer of batch results (an instructor auditing grades, a researcher comparing experiment runs), I need every step execution representable as a uniform per-step record and every run as a run-level record, so results are auditable item by item, comparable across runs, cost-annotated, and resumable.

**Why this priority**: The run-record schema is the second half of the contracts. Its shape is informed by the spike's usage and error evidence (User Story 1), so it follows P1 and sits alongside P2.

**Independent Test**: Record instances can be created for every conformance scenario and validated against the schema, with no runner involved: every outcome, including failures, has a representation.

**Acceptance Scenarios**:

1. **Given** any step execution outcome (success, item failure, assertion failure, retry exhaustion, downstream skip with reason), **When** it is recorded, **Then** it is an explicit status-bearing record - never a silent omission.
2. **Given** an LLM step record, **When** it is inspected, **Then** it carries provider, model, token counts, estimated cost, cost-table version, and whether counts are provider-reported or estimated.
3. **Given** a record from a matrix cell, **When** records are aggregated, **Then** the matrix parameters are attached to every relevant per-step record and cost totals can be aggregated by matrix dimension.
4. **Given** a run-level record, **When** it is inspected, **Then** it carries the workflow hash, configuration snapshot, source-control commit when available, and run totals.
5. **Given** per-item records from a batch containing duplicate item values, **When** items are identified, **Then** identity is positional (item index, plus optional durable entity ID), and duplicate values cause no ambiguity.

---

### User Story 4 - GradeBot Fixture and the Falsification Test (Priority: P4)

As the project owner, I need the GradeBot grading process (collect submissions, run tests per submission, grade each against a rubric prompt with structured output, validate, write per-student feedback and a summary report) expressed freshly under the workflows-are-data rules, in both authoring surfaces, validating as the first conformance fixture - because this is the deliberate falsification test: if a real workflow cannot be expressed cleanly without expressions, the workflows-are-data decision must be revisited before more code is written.

**Why this priority**: It is an exit criterion for the feature and the proving ground for the schema, but it depends on the schema (User Story 2) existing first.

**Independent Test**: The fixture validates from both surfaces with byte-identical canonical serializations, remains readable end to end, and the falsification census (the author's and a context-free reviewer's, independently) confirms no code step exists only because the schema forbids expressions.

**Acceptance Scenarios**:

1. **Given** the logical grading description, **When** it is expressed in the data-file surface under the binding rules (no expressions; dotted-path references in mapping positions only; prompts in prompt files bound by explicit input maps; transformations as code steps), **Then** it validates.
2. **Given** the same workflow through direct construction, **When** validated, **Then** the canonical form is identical to the data-file version's.
3. **Given** the validated fixture, **When** a person reads it, **Then** every step, reference, and prompt binding is legible without running anything.
4. **Given** the validated fixture, **When** every code step is censused with the counterfactual question - would this step exist if the schema had a template language? - by the fixture's author and independently by a context-free reviewer, **Then** both censuses agree that no step exists only to emulate a forbidden construct; any step failing the question, or any disagreement between the censuses, halts the feature and escalates the workflows-are-data decision before further implementation, rather than working around it.

---

### Edge Cases

- Duplicate values in an `each` collection: aligned access is by index, never by item value, so records and downstream references stay unambiguous (this is a required conformance fixture).
- Empty `each` collection: emptiness is runtime input data, invisible at dry-run, so the workflow validates and a run records zero per-item results explicitly rather than silently (execution fixture, exercised with the Feature 002 runner). Empty matrix dimension: visible in the workflow file itself and rejected at dry-run - a workflow that can execute zero cells is an authoring error that must fail loudly.
- A failure shape not in the error taxonomy (a provider failing in a novel way): the taxonomy carries an explicit unclassified category so nothing is silently coerced into a wrong category.
- Corrupt trailing record in the append-only machine log: the record contract makes detection possible (this feature defines the contract and fixture; recovery behavior is exercised with the runner in Feature 002).
- The spike recommends against the current hypothesis (outcome is thin layer, conventions package, or abandon): the substrate decision is escalated and revised before the contracts half of this feature proceeds on assumptions the evidence contradicts.
- A workflow author places a credential in a workflow parameter: the schema offers no credential fields and documentation directs secrets to the environment; content inspection of arbitrary parameters is not attempted.

## Requirements *(mandatory)*

### Functional Requirements

Spike (001a):

- **FR-001**: The spike MUST demonstrate per-call capture of token counts and cost inputs into the per-step record shape, including on validation-retry paths, across one hosted provider, one local model, and a deterministic stub.
- **FR-002**: The spike MUST demonstrate that the substrate's internal validation retries are bounded, counted, and visible, and that they cannot silently multiply with runner-level retries.
- **FR-003**: The spike MUST document observed failure shapes after retry exhaustion, transport failure, and rate limiting, and map each to the run-record error taxonomy. Provider coverage matches FR-001: one hosted provider, one local model, and the deterministic stub.
- **FR-004**: The spike MUST record an interface recommendation for an LLM component that stays workflow-configured (model selection resolved from workflow data, not from code).
- **FR-005**: The spike MUST include a minimal runnable grading skeleton (3 simulated submissions, simulated test execution, one structured feedback call per item, per-item records, one forced item failure, one resume after simulated interruption) and state a boundary recommendation: what the substrate owns versus what Pipyer owns.
- **FR-006**: The spike MUST evaluate the substrate's eval tooling against the model-eval workflow (2 cases, 2 prompts, 2 model aliases, judge step, usage collection) and recommend: native matrix execution, integrate, or defer.
- **FR-007**: The spike MUST evaluate the substrate's graph and durable-execution primitives against a fixed two-step workflow and recommend use, ignore for v1, or revisit later, including whether node outputs map cleanly to the per-step record and whether durable execution supports deterministic item-level resume.
- **FR-008**: The spike MUST conclude with a short evidence report stating one of four outcomes - standalone runner, thin layer, conventions package, or abandon - and a confirmed or revised LLM-component boundary.

Contracts (001b):

- **FR-009**: The workflow schema MUST cover workflow metadata, declared inputs, ordered steps, per-step component configuration and input maps, `each` bindings, matrix dimensions, settings (concurrency, failure budgets, checkpoint location), output declarations, and an explicit declaration of the workflow-schema version the file conforms to.
- **FR-010**: Validation of the workflow schema MUST constitute the dry-run: a workflow that validates is executable in principle; one that does not is rejected before any execution, with errors naming the offending element and its location.
- **FR-011**: The schema MUST support two equal authoring surfaces - a plain data file (loaded safely, then validated, nothing more) and direct construction in code - producing byte-identical output under a single defined canonical serialization of the validated model. The canonical serialization is defined in the machine layer, never over either authoring surface's file format; it pins key ordering and default materialization explicitly; and it is the same byte stream over which the workflow hash (FR-016) is computed, so one definition serves surface equality, hashing, and resume matching.
- **FR-012**: The schema MUST NOT be able to express templating, expressions, conditionals, or loops. References MUST be dotted paths in mapping positions only. Prompts MUST live in prompt files with named placeholders bound by explicit input maps. Transformations are code steps.
- **FR-013**: The schema MUST provide no mechanism to vary steps, prompts, or configuration per item within a batch: uniformity across items is guaranteed by construction.
- **FR-014**: The run-record schema MUST define a per-step record carrying run ID, step name, component type, status, output, error, timing, token usage and cost when applicable, matrix parameters when applicable, item index and optional durable entity ID when applicable, input references and hashes (provenance), and component version.
- **FR-015**: Cost fields MUST include provider, model, token counts, estimated cost, cost-table version, and whether counts are provider-reported or estimated.
- **FR-016**: Run-level records MUST carry the workflow hash, configuration snapshot, source-control commit when available, totals, and the run-record schema version the records were written under. Records MUST be representable as append-only machine-readable lines from which a human-readable run summary is derivable, and MUST be append-friendly to external stores.
- **FR-017**: A conformance test suite MUST cover the fixture areas in SPEC section 7. Schema-level areas (valid and invalid workflows, dangling dotted-path references, duplicate `each` item representation, failure-status records, cost and matrix attachment) MUST pass in this feature; execution-behavior areas (resume, budget halts, corrupt-record recovery) MUST be authored as fixtures with expected outcomes, to be exercised against the runner in Feature 002.
- **FR-018**: The GradeBot workflow MUST be expressed freshly from its logical description in both authoring surfaces as the first conformance fixture, and MUST validate.
- **FR-019**: If the GradeBot fixture cannot be expressed cleanly without expression constructs, work MUST halt and the workflows-are-data decision MUST be escalated before further implementation (falsification clause). "Expressed cleanly" is tested operationally, not by validation alone (which FR-012 makes vacuous): every code step in the fixture is censused against the counterfactual question - would this step exist if the schema had a template language? A step that disappears under that hypothetical is expression-emulation and fails the test; genuine domain work survives it and passes. The census MUST be performed independently by the fixture's author and by a context-free reviewer; verdict, census, and per-step reasoning are recorded in the feature exit notes. Any failing step, or disagreement between the two censuses, triggers the halt. A passing census is retained as the operational definition of the language-creep breach signal for all future workflow reviews.
- **FR-020**: The six open decisions from SPEC section 12 MUST be resolved and recorded with rationale during this feature's planning: model-alias declaration and resolution; whether skip-on-upstream-failure is step-local or global policy; whether collection-producing non-`each` steps expose an aligned items view; whether assertion failures count against failure budgets; whether final write and summary steps rerun by default on resume; and the checkpoint format.
- **FR-021**: The feature MUST ship a minimal command-line validation entry point: given a workflow file, it performs the full dry-run validation, reports errors naming the offending element and its location, exits with success for a valid workflow and failure otherwise, and executes nothing. It is the authoring loop for people and agents until the runner arrives in Feature 002.

### Key Entities

- **Workflow**: the human-authored recipe - metadata, declared inputs, ordered steps, settings, output declarations, and the workflow-schema version it conforms to. Exists as data, never as a program.
- **Step**: one unit of work - name, component type, component configuration, input map of dotted-path references, optional `each` binding over a collection.
- **Matrix dimension**: a named parameter axis (models, prompts, thresholds, datasets) whose combinations expand into run cells; never expands topology.
- **Settings**: concurrency, failure budgets (max failures, max failure rate), checkpoint location.
- **Prompt file**: externally stored prompt with named placeholders, bound per step by an explicit input map.
- **Per-step record (StepResult)**: the uniform evidence unit for one step execution; fields per FR-014 and FR-015.
- **Run record**: run-level evidence - workflow hash, configuration snapshot, source commit, totals, and the run-record schema version it was written under; the append-only machine log plus the human summary.
- **Conformance fixture**: a workflow or record instance paired with its expected validation or execution outcome; the GradeBot workflow is the first.
- **Spike evidence report**: questions, observed behavior, per-question recommendations, and the overall boundary outcome.
- **Falsification census**: the per-step record of the counterfactual test from User Story 4 - each code step in the fixture, whether it would exist if the schema had a template language, and the reasoning - produced independently by the author and a context-free reviewer, and retained as the operational definition of the language-creep breach signal.
- **Open decision**: one of the six carried design questions, with its recorded resolution and rationale.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The spike report answers all four spike areas (usage capture, retry accounting and error shapes, eval-tooling fit, graph/durable-execution fit) with evidence from executed code, and states exactly one of the four boundary outcomes with a confirmed or revised LLM-component boundary.
- **SC-002**: 100% of the schema-level conformance areas from SPEC section 7 have tests, and all of them pass; 100% of the execution-behavior areas have authored fixtures with expected outcomes ready for Feature 002.
- **SC-003**: The GradeBot fixture validates from both authoring surfaces with byte-identical canonical serialization and contains zero templating, expression, conditional, or loop constructs.
- **SC-004**: 100% of invalid-workflow fixtures are rejected at validation with an error that names the offending step, field, or reference - none fail silently or with an unlocatable error - whether validation is invoked through the library or the command-line entry point.
- **SC-005**: All six open decisions are resolved and recorded with rationale; none remain open at feature exit.
- **SC-006**: Every scenario in the SPEC section 7 fixture list is representable in the run-record schema, demonstrated by a validating record instance - including every failure scenario as an explicit failure-status record.
- **SC-007**: The spike's grading skeleton, when interrupted and resumed, completes with per-item evidence for all 3 items (including the forced failure) and recomputes zero completed items.
- **SC-008**: The falsification census exists in the feature exit notes with two independent passes (author and context-free reviewer) covering 100% of the fixture's code steps, and either zero steps fail the counterfactual question or the escalation path was taken.

## Out of Scope

- The runner itself: execution, checkpointing, resume behavior, failure-budget enforcement at runtime (Feature 002).
- Matrix execution and run comparison (Feature 003); external CLI orchestration (Feature 004).
- Campaign semantics, review queues, status workflows; template or expression languages; autonomous control flow; UI or dashboard; scheduler; hosted services (constitution, Operational Constraints).
- HTTP and human-checkpoint components (deferred).
- Re-proving raw or structured LLM calls across providers (already proven; explicitly excluded by the spike's narrowing).

## Assumptions

- The spike's conclusions default to the current hypothesis (a standalone runner using the substrate internally for LLM steps) unless the evidence contradicts it; the report must say so explicitly either way.
- Spike artifacts are evidence, not product code; they may be discarded after the report is accepted. The contracts and conformance tests are product code.
- The error taxonomy referenced by FR-003 is defined as part of the run-record contract in this feature; the spike's observed failure shapes are mapped into it as it is defined.
- "Passing conformance tests" at feature exit applies to schema-level tests; execution-behavior fixtures are authored and reviewed but necessarily await the Feature 002 runner to execute.
- The GradeBot fixture is a fresh expression from the logical description in SPEC section 9, not a port of existing GradeBot code.
- Live provider access for the spike is available through environment-variable credentials, with small request volumes. Coverage is one hosted provider and one local model, with the deterministic stub used wherever live calls are not essential to the question being answered.
- The canonical serialization's default-materialization policy is pinned during planning, and its consequence is documented as intended: if defaults are materialized, a future schema version that adds a defaulted field changes canonical bytes and therefore workflow hashes, ending resume continuity at the schema-version boundary - which composes with the explicit schema-version fields rather than surprising anyone later.
- The six open decisions are resolved during this feature's planning phase (per the backlog), so the schemas encode their resolutions rather than leaving variation points open.
