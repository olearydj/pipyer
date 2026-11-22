# Sprint 04 Improvement Candidates

Date: 2026-06-14

This note collects possible and suggested Sprint 04 improvements after Sprint
03 matrix execution and run comparison. It is grounded in the original Pipyer
vault notes under `/Volumes/Casa/obsidian/vault/projects/pipyer/`, especially
the V1 design spec, the empirical-grounding note, ADRs 002/003/005/006, and the
current code-repo sprint docs.

## Product Compass

Pipyer is the execution-evidence layer for repeatable LLM workflows. The core
boundary still holds:

- YAML/data declares the workflow shape.
- Python, shell, and external tools do deterministic work.
- LLMs provide judgment inside fixed steps.
- JSON/JSONL records make the run replayable, auditable, resumable, and
  comparable.

The runner should keep deterministic topology and recorded variation as its
main promise. It should not become an autonomous agent, a campaign/status
platform, a dashboard, or a general YAML programming language.

The original V1 consumers remain useful, but maturity now matters more than
backlog order:

1. GradeBot batch grading: mature and now Pipyer-native enough to serve as a
   stable hardening fixture.
2. DEMA experiment runner: mature enough to serve as a matrix/eval fixture,
   though still partly shell-bridged through `dema-llm`.
3. twc-bridge discovery pass: still a valid V1 consumer, but probably too
   immature to make the default next porting target.
4. Agentic wargaming: a useful future design pressure, but still only an idea.

## Current State

Sprint 03 delivered the matrix and comparison layer:

- Matrix unit keys use `cell[N]/step` and `cell[N]/step[index]`.
- `StepResult` records include `cell_index` and `matrix`.
- Existing failure budgets are cell-local for matrix runs.
- `cell_halted` exists for per-cell budget breaches.
- `pipyer compare` supports run-vs-run and cell-vs-cell comparison, writes
  markdown and JSON artifacts, and reconstructs from event logs.
- Scoped resource digests participate in `input_hash` for files Pipyer directly
  opens or executes.
- GradeBot and DEMA both have reproducible local run harnesses under `runs/`.

The work also exposed several limits:

- DEMA is still a shell bridge. Pipyer validates the orchestration shape, but
  DEMA owns provider calls, provider repair behavior, and some cost accounting.
- Reproducibility is strong but not hermetic. Provider backend state can drift,
  OpenAI model ids may be weaker evidence when they are not documented fixed
  snapshots, and provider-resolved versions are not always available.
- Archive manifests are useful but not yet a first-class Pipyer product
  surface. Current scripts repeat some archive logic per workflow.
- `pipyer compare` is sufficient for Sprint 03 evidence, but large-diff
  browsing, error taxonomies, and domain-specific summaries can be clearer.
- Pipyer has enough evidence now to ask how external eval, optimization, and
  observability tools should fit without letting them replace Pipyer's run
  record contract.

## Recommended Sprint 04

Sprint 04 should be an evidence-hardening and external-tool-boundary sprint
using GradeBot and DEMA as stable fixtures.

Suggested title:

> Evidence Hardening, Eval Rigor, and Prompt/Context Optimization

This avoids forcing twc-bridge before its own workflow shape has matured. The
immediate product question is:

> How should Pipyer compare models fairly when some models need different
> prompts, examples, or context strategies to perform well, while still keeping
> Pipyer's JSONL run record as the evidence of record?

### Suggested Goals

1. Harden model, prompt, schema, resource, and archive provenance for existing
   GradeBot and DEMA workflows.
2. Use Hamel Husain and Shreya Shankar's eval methodology as the audit rubric:
   error analysis first, human labels where needed, binary criteria where
   possible, and validated judges instead of uncalibrated automated scores.
3. Treat prompt/context optimization as part of fair model comparison. A
   fixed-prompt matrix answers only how models perform on that prompt; Sprint
   04 should also test a DSPy-style optimization loop where each candidate
   model gets a locked, model-specific optimized prompt/context artifact before
   held-out evaluation.
4. Test external tools against Pipyer's boundary, prioritizing eval and
   optimization: Inspect AI and DSPy first; promptfoo, DocETL,
   Logfire/OpenTelemetry, and optionally Phoenix/Braintrust/LangSmith as
   secondary candidates.
5. Improve `pipyer compare` only where the audit shows it needs better
   decision support: failure taxonomies, top changed units, stability summaries,
   or archive-stable artifact links.
6. Produce a decision record that says what to integrate, what to keep as an
   export format, and what to avoid.

### Suggested Acceptance

- An eval audit over the retained GradeBot and DEMA evidence identifies concrete
  gaps, ranked by impact.
- At least one GradeBot or DEMA comparison is converted from raw diffs into a
  failure taxonomy suitable for human review.
- A small labeled set exists for one evaluator or judge task, with a validation
  report against human labels.
- A model-comparison fixture separates fixed-prompt baseline, calibration or
  optimization set, and held-out evaluation set.
- A DSPy-style optimization spike produces at least one locked prompt/context
  artifact per candidate model, or records why the approach is not yet viable.
- External-tool spikes produce artifacts Pipyer can archive and compare, or
  explicit "do not integrate yet" findings.
- Archive manifests gain clearer model/resource provenance where Pipyer or the
  harness already has the data.
- The full test suite remains green after any code changes.

## Candidate Improvements

### 1. Hamel/Shreya Eval Method as the Audit Rubric

Hamel Husain's `evals-skills` work and the Hamel/Shreya teaching material are
useful as process, not as a runtime dependency. They emphasize the practices
Pipyer needs next:

- audit the current eval pipeline before choosing tools;
- perform error analysis on actual traces and outputs;
- create task-specific failure taxonomies;
- prefer binary pass/fail labels where possible;
- build LLM judges iteratively against human labels;
- validate judges with true-positive/true-negative rates and bias correction;
- keep human review central instead of hiding uncertainty behind aggregate
  scores.

Suggested Sprint 04 experiment:

1. Run an eval-audit-style review over the GradeBot and DEMA Sprint 03 evidence.
2. Choose one comparison set with meaningful disagreements.
3. Categorize failures manually or semi-manually.
4. Define one binary evaluator from that taxonomy.
5. Validate the evaluator against human labels before trusting it.

This fits Pipyer's philosophy: the workflow records the evidence; humans and
validated evaluators interpret it.

### 2. Shreya Shankar's Evaluator-Validation Line

Shreya Shankar's work is especially relevant where Pipyer touches assertions,
LLM judges, semantic data processing, and review interfaces.

Relevant ideas:

- EvalGen: "validate the validators" by aligning LLM-generated prompts or code
  assertions with human judgments.
- Criteria drift: evaluation criteria often become clearer only after users
  inspect outputs. Pipyer should record that iteration rather than pretending
  criteria are fixed from the start.
- SPADE and PromptEvals: generated assertions and guardrails are useful, but
  they still need validation and versioning.
- DocETL and DocWrangler: strong candidates as external engines or interface
  inspiration for semantic data processing, not core Pipyer runtime features.

Suggested Sprint 04 experiment:

- Take one current `llm_judge` or comparison classification problem.
- Build a tiny human-labeled calibration set.
- Try a judge prompt and/or assertion.
- Record its confusion matrix and known blind spots.
- Treat the validated prompt/assertion as a versioned workflow input.

### 3. Prompt/Context Optimization for Fair Model Comparison

Sprint 03's GradeBot matrix answered a useful but narrow question: how the
candidate model performed under the existing prompt and context. That is the
right question for migration safety and regression checks, but it is not a fair
estimate of each model's best task performance.

Some models need more explicit schemas, some need examples, some respond better
to concise instructions, and some are more sensitive to long rubric context. A
fixed prompt can therefore score prompt transfer more than model capability.

Sprint 04 should make the methodological distinction explicit:

1. Fixed-prompt baseline: run the current prompt/context across all models.
2. Optimization phase: optimize prompt, examples, or context strategy per
   candidate model on a calibration set.
3. Artifact lock: save each optimized prompt/context/program as a versioned
   workflow input with hashes and provenance.
4. Held-out evaluation: run Pipyer over a held-out set using each model's locked
   optimized artifact.
5. Decision comparison: report quality, cost, latency, stability, and failure
   taxonomy for both fixed-prompt and optimized-prompt conditions where useful.

DSPy is the leading candidate because it treats prompts/programs as optimizable
artifacts against a metric. The boundary is strict: optimization happens between
runs; Pipyer runs the locked artifacts and records the evidence. DSPy should not
mutate a production workflow during a Pipyer run.

Open design questions:

- How should optimized artifacts be represented: prompt file, JSON program,
  examples file, or a small workflow-local package?
- Should the matrix dimensions become `model x prompt_variant x
  context_strategy`, or should each optimized model cell point at its own
  artifact bundle?
- What is the smallest calibration/held-out split that is useful for GradeBot or
  DEMA without overfitting?
- Which metrics are safe enough to optimize against: exact match, human labels,
  validated judge, domain score, or a composite?

Suggested Sprint 04 experiment:

- Use GradeBot or DEMA to create a tiny calibration split and held-out split.
- Run a fixed-prompt baseline.
- Run DSPy or equivalent optimization for two candidate models.
- Freeze the optimized artifacts.
- Run Pipyer held-out evaluation and compare fixed-prompt vs optimized-prompt
  results.

### 4. External Eval Engine Boundary

Several tools are plausible, but each should be tested against the same
boundary: Pipyer owns topology, `StepResult`, resume, compare, and archives;
external tools may own specialized eval execution, scoring, optimization,
annotation, or traces.

| Tool | Best Candidate Role | Boundary |
| --- | --- | --- |
| Inspect AI | Serious eval engine for tasks, datasets, solvers, scorers, model grading, logs, and analysis. | Priority eval-engine spike. Use as a component or export target; do not replace Pipyer's workflow runner or event log. |
| DSPy | Priority optimization candidate for prompt/context/example tuning against metrics. | Outputs become locked, versioned workflow inputs; it must not mutate a production workflow during a run. |
| promptfoo | Lightweight prompt/model matrix testing, red-team checks, and side-by-side prompt comparison UX. | Useful foil or adapter; overlaps with Pipyer matrix/compare, so avoid making it canonical evidence. |
| DocETL | Semantic document/data processing engine. | Orchestrate and archive it as an engine; do not absorb its query optimizer or document-processing model. |
| Logfire/OpenTelemetry | Debugging and observability for PydanticAI/provider behavior. | Optional trace layer; JSONL `StepResult` remains authoritative. |
| Phoenix/Braintrust/LangSmith | Trace stores, annotation workflows, review interfaces, experiment stores. | Potential export or annotation backend; avoid proprietary lock-in as the source of truth. |

Suggested near-term choice: build adapters only after an audit proves a concrete
need. Prioritize the eval and optimization boundary first; compare artifacts,
schemas, and ergonomics using scripts or workflow-local glue before adding core
Pipyer abstractions.

### 5. Archive Manifest Standardization

The GradeBot and DEMA run folders now have a useful pattern, but the pattern
lives mostly in scripts. Sprint 04 can extract the common shape without
overbuilding a hosted archive system.

Possible improvements:

- Define a documented archive manifest shape in `runs/README.md` or a small
  `docs/` note.
- Add shared helpers for git state, command logs, workflow snapshots, lockfile
  digests, and source-file digests.
- Add manifest-level summaries of resource digests that already affect
  `input_hash`.
- Keep raw run directories immutable under `artifacts/run/`.
- Keep generated archives gitignored.
- Consider a future `pipyer archive` command only if repeated workflow folders
  make script duplication painful.

Suggested near-term choice: standardize the convention and helper scripts
first; avoid adding a core CLI command until the shape stabilizes.

### 6. Reproducibility and Model Provenance

Sprint 03 showed that "same workflow" is not enough for durable model evidence.
Sprint 04 should improve what can be recorded without claiming provider
behavior is frozen.

Possible improvements:

- Record requested model id, provider, structured-output mode, decoding
  parameters, cost table version, and provider-reported usage on every native
  Pipyer LLM call.
- Record provider-resolved model version, system fingerprint, or equivalent when
  the provider exposes one.
- Add run-script or workflow-harness checks that reject `latest`, `preview`, and
  known alias-like model ids for benchmark evidence unless an explicit
  `ALLOW_MODEL_DRIFT=1`-style override is set.
- For open/local models, record model artifact digest, runtime/server version,
  quantization, sampler settings, and material hardware/runtime notes.
- For optimized prompt/context artifacts, record the optimizer, optimizer
  version, calibration set identity, metric, artifact hash, and any held-out set
  used for final evaluation.

Suggested near-term choice: add manifest-level summaries and checks in the
workflow harnesses first; promote to core validation only after the policy is
stable across GradeBot and DEMA.

### 7. Compare UX, Error Analysis, and Stability Evidence

`pipyer compare` is now a real product capability. The next improvements should
make it easier to use for decision records and error analysis.

Possible improvements:

- Better markdown sections for summary deltas, quality deltas, cost deltas, and
  latency deltas.
- Top changed units, grouped by status, magnitude, and failure taxonomy.
- A workflow-supported way to attach human labels or review annotations to
  comparison rows.
- More compact JSON schema for downstream analysis.
- Better path normalization for generated artifacts.
- Formal identical-rerun stability pair for GradeBot and/or DEMA.
- Side-by-side reporting for fixed-prompt vs optimized-prompt model comparisons.
- Optional comparison index pages inside archive folders.

Suggested near-term choice: improve compare only where a Sprint 04 audit or
validation experiment needs it. Avoid turning compare into a statistics
package.

### 8. DEMA Native Migration

The DEMA Sprint 03 workflow is explicitly a bridge harness. That was the right
acceptance strategy because it validated Pipyer against an existing experiment
surface.

Longer term, the cleaner design is:

- DEMA exposes domain functions for candidate-pair generation, prompt/context
  construction, gate application, clustering, and evaluation.
- Pipyer owns matrix expansion, provider calls, secrets, usage/cost capture,
  retry/failure semantics, resume, and comparison.
- A Pipyer-native DEMA workflow is compared against the locked bridge harness
  before the bridge is retired.

Suggested Sprint 04 choice: do not make full DEMA native migration the main
sprint unless DEMA has an immediate experiment that requires it. Use DEMA as a
fixture for eval/tool-boundary work first.

### 9. twc-bridge Future Consumer

twc-bridge remains a real V1 consumer, but it should probably mature further
before becoming the main Pipyer porting target. Porting it now would likely
blend two jobs:

- discovering the right twc-bridge pass shape; and
- testing Pipyer's external-CLI composition boundary.

That could teach useful lessons, but it is not the lowest-noise Sprint 04 path.

Suggested near-term choice: inspect twc-bridge when needed, but do not make a
full `workflows/twc-bridge-discovery/` port the default Sprint 04 exit.

### 10. Failure Budgets, Retries, and Run Circuit Breakers

Sprint 03 intentionally kept `settings.retry` out of the first pass and did not
add a run-wide matrix circuit breaker.

Possible improvements:

- Add a separate `max_run_failures` or similar whole-run cap if matrix runs need
  runaway protection across cells.
- Add explicit, bounded, default-off retry settings only for transient provider
  or transport categories.
- Record every retry attempt in the event log or `StepResult` detail.
- Prevent multiplication between runner retries and component/provider
  validation retries.

Suggested near-term choice: keep this deferred unless the external-tool spike or
a new DEMA run proves the need. Cell-local budgets and fail-closed component
behavior are enough for current evidence.

### 11. GradeBot Future Reproducibility

GradeBot is already the strongest native Pipyer proof. Future semester runs
would benefit from small reproducibility improvements:

- Manifest-level prompt, schema, workflow, script, and lockfile digests.
- PII-safe corpus manifest: file list, sizes, mtimes where useful, and hashes
  where policy allows.
- Provider-resolved model metadata when available.
- Explicit decoding parameters in the archive manifest.
- Model-pin checks in the run harness.
- Comparison records that surface human-review bands and known override paths
  more directly.
- Error taxonomies and validated judges for recurring disagreement classes.
- Fixed-prompt and optimized-prompt model comparison records when making future
  model upgrade decisions.

Suggested Sprint 04 choice: use GradeBot as one of the primary fixtures for the
hardening and eval-method work.

## Non-Goals

Sprint 04 should not add:

- YAML templating, expressions, conditionals, or loops.
- Autonomous control flow or model-selected next steps.
- Campaign state machines, review queues, or status workflows inside Pipyer.
- A hosted service, dashboard, scheduler, or database-backed run store.
- A full DEMA rewrite unless it is explicitly chosen over the eval-boundary
  sprint.
- A full twc-bridge port unless twc-bridge maturity becomes the explicit goal.
- A generic statistics or eval platform beyond comparison records and adapters
  needed by current evidence.
- Tool integrations whose artifacts cannot be exported into Pipyer's local
  archive discipline.

## Open Decisions

1. Is Sprint 04 formally a hardening and external-tool-boundary sprint?
   Recommendation: yes.
2. Which fixture should lead the audit: GradeBot, DEMA, or both?
   Recommendation: both, with GradeBot for native LLM evidence and DEMA for
   matrix/eval bridge evidence.
3. Which external tools get the first spikes?
   Recommendation: Inspect AI for eval-engine fit and DSPy for
   prompt/context optimization, with Hamel/Shreya methodology as the audit
   rubric.
4. Should model-pin checks be core validation or run-harness policy?
   Recommendation: run-harness policy first.
5. Should a formal identical-rerun stability benchmark be part of Sprint 04
   acceptance?
   Recommendation: yes if affordable, because it directly supports evaluator
   validation and compare UX.
6. What should count as a fair model comparison?
   Recommendation: report both fixed-prompt and optimized-prompt results when
   making model-upgrade decisions, and keep calibration sets separate from
   held-out evaluation sets.
7. Should review annotations become a core record type?
   Recommendation: not yet. Start with workflow outputs or comparison-side
   artifacts, then promote only if the shape recurs.

## Suggested Work Plan

1. Run an eval-audit-style review over GradeBot and DEMA Sprint 03 evidence.
2. Choose one comparison set and build a failure taxonomy.
3. Create a small human-labeled calibration set for one evaluator or judge.
4. Validate one judge/assertion against those labels and record its limits.
5. Create a calibration/held-out split for a small model-comparison fixture.
6. Run a fixed-prompt baseline across candidate models.
7. Spike DSPy or equivalent prompt/context optimization for at least two model
   cells.
8. Freeze optimized artifacts and run held-out Pipyer evaluation.
9. Spike Inspect AI against the same fixture as an external eval engine.
10. Spike one of promptfoo, DocETL, or Logfire only if the audit identifies a
   clear need.
11. Standardize archive/model/resource provenance helpers where duplication is
   already obvious.
12. Improve `pipyer compare` only where the audit requires better review or
   decision support.
13. Record the findings and decisions in `docs/`, keeping raw artifacts local and
   gitignored.

## References

- Hamel Husain, `evals-skills`:
  <https://github.com/hamelsmu/evals-skills>
- Hamel Husain, "LLM Evals: Everything You Need to Know":
  <https://hamel.dev/blog/posts/evals-faq/>
- Hamel Husain, "Selecting The Right AI Evals Tool":
  <https://hamel.dev/blog/posts/eval-tools/>
- Shreya Shankar:
  <https://www.sh-reya.com/>
- EvalGen paper:
  <https://arxiv.org/abs/2404.12272>
- Inspect AI:
  <https://inspect.aisi.org.uk/>
- promptfoo:
  <https://www.promptfoo.dev/docs/intro/>
- DSPy:
  <https://dspy.ai/>
- Pydantic Logfire PydanticAI integration:
  <https://pydantic.dev/docs/logfire/integrations/llms/pydanticai/>

## Confidence

High confidence on the revised direction: GradeBot and DEMA are better Sprint
04 fixtures than twc-bridge because they are mature enough to expose real
hardening and eval-boundary problems without also requiring domain-product
development.

Medium-high confidence that optimization must be part of fair model comparison.
A fixed-prompt matrix remains valuable for regression and migration safety, but
it does not answer which model performs best after reasonable task-specific
tuning.

Medium confidence on the first external-tool spikes. Inspect AI is the
strongest candidate for eval-engine integration, and DSPy is the strongest
candidate for prompt/context optimization, but the audit may reveal that a
smaller Hamel/Shreya-style evaluator-validation loop should happen before any
durable adapter.

Low confidence that a core archive command or first-class review annotation
schema is warranted yet. The pattern is real, but it should prove itself across
one more hardening pass before becoming product API.

## Credential handling consideration (September 5, 2026)

Consider replacing Secretpath with a Danvas-like approach: optional credential commands configured in trusted user configuration, invoked only when credentials are needed, with environment-variable input retained when no helper is configured. Keep secret storage and provider-specific authentication outside Pipyer. Assess run-scoped credential reuse across preflight and matrix steps, provider/endpoint binding, subprocess inheritance, and sanitized provenance. This is a backlog consideration, not a scheduled migration or implementation brief.
