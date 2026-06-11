# Phase 0 Research: PydanticAI Spike and Contracts

All NEEDS CLARIFICATION items are resolved here. R1-R6 are the six open decisions carried from SPEC section 12 and mandated by FR-020. R7-R8 close the two design points raised in the clarification session. R9-R10 set the spike's probe map and the packaging boundary.

## R1: Model alias declaration and resolution

**Decision**: Model aliases are declared in a top-level `models` block of the workflow file itself, mapping alias name → model identifier plus optional model settings. LLM steps reference aliases only (`model: grader`); they never name providers or models directly. Alias existence is checked at dry-run; an alias's target MAY be a dotted-path reference to a declared workflow input or matrix parameter (a mapping-position reference, consistent with ADR-004), which is how DEMA varies models across matrix cells. The resolved alias table is part of the run-level configuration snapshot.

**Rationale**: Configuration fragmentation (config files + CLI flags + env vars) is a documented failure mode from the four prior builds; the workflow file is the single artifact. The spike's interface question (FR-004) requires the LLM component to stay workflow-configured - aliases resolved from workflow data, not code. Matrix expansion gets a stable handle (`grader`) whose binding varies per cell while topology stays fixed.

**Alternatives considered**: A separate models config file (rejected: re-introduces fragmentation; workflow no longer self-contained). A code-level alias registry (rejected: violates workflow-configured requirement; invisible in the artifact). CLI flags at run time (rejected: fragmentation; run-record config snapshot would capture it, but the workflow file would lie about what ran).

## R2: `skip_if_failed` - step-local or global policy

**Decision**: Global policy, fixed default, no per-step override in v1. Downstream steps skip items whose upstream failed, each skip producing a skip-status `StepResult` with a recorded skip-reason naming the upstream failure. No schema field exists for per-step override.

**Rationale**: One failure model (Principle V). SPEC section 6 already names this default. None of the three consumers needs an override: GradeBot must not grade a submission whose test step failed; DEMA must not adjudicate a cell whose extraction failed; twc-bridge must not export what didn't extract. Build by extraction says the override field gets added when a consumer demands it, not before.

**Alternatives considered**: Per-step `skip_if_failed: false` (deferred: speculative schema surface; also poses the unanswerable question of what value a failed upstream reference resolves to). Run-anyway-with-failure-marker semantics (rejected for v1: complicates input resolution for zero consumer benefit).

## R3: Aligned `items` view for collection-producing non-`each` steps

**Decision**: No separate aligned view in v1. Any step output that is a JSON array can be the source of an `each` binding. Positional alignment (`item`, `index`) exists only inside `each` steps; sibling `each` steps over the same source collection align by index, per SPEC section 6.

**Rationale**: The consumer pattern is collect-then-iterate (GradeBot: `collect_submissions` produces an array; `run_tests` and `grade` iterate it). That works with arrays plus `each` alone. An extra view mechanism is schema surface with no consumer behind it.

**Alternatives considered**: An implicit `.items` accessor on any array output (rejected: magic accessor, Principle V). Requiring collections to originate only from `each` steps (rejected: kills the core collect-then-iterate pattern).

## R4: Assertion failures versus failure budgets

**Decision**: Yes, they count. An assertion step failing for an item marks that item failed - a failure-status `StepResult` with error category `assertion_failed` - and counts toward `max_failures` / `max_failure_rate` exactly like any other item failure. An assertion failure outside an `each` context fails the workflow, recorded as a halt event.

**Rationale**: Assertions are the mechanical reviewer; the design history's confidence collapse came from unreviewed per-item work. A bad output detected by an assertion is an item failure in every sense the budget exists to count. Two parallel failure-accounting systems would be cleverness (Principle V).

**Alternatives considered**: Assertions as recorded warnings only (rejected: silent quality decay; breaks the uniformity guarantee's value). A separate assertion budget (rejected: second knob, no consumer asked for it).

## R5: Do final `file_write` / summary steps rerun by default on resume?

**Decision**: Yes - as a consequence of content-hash semantics, not as a special case. A completed step is skipped on resume only when its workflow, input, and configuration hashes match the prior record. A summary or final-write step's inputs aggregate per-item results, so a resume that completes previously missing items changes the aggregate input hash and the step reruns naturally. When the hashes match, skipping is correct: the output already reflects exactly these inputs. `file_write` reruns are safe because final writes follow the dry-run-gated, idempotent conventions (SPEC section 6).

**Rationale**: Zero special-casing; the desired behavior falls out of semantics that must exist anyway. An `always_run` flag would be redundant schema surface and a second code path through resume logic (Principle V).

**Alternatives considered**: `always_run: true` step flag (rejected: redundant given hash semantics). Unconditionally rerunning all `file_write` steps (rejected: violates resume-without-recompute for per-item writes).

## R6: Checkpoint format

**Decision**: Both, with a strict hierarchy: the JSONL event log is the single source of truth; the checkpoint is a derived JSON snapshot written atomically (temp file, flush, fsync, rename) for O(1) resume startup. The snapshot carries run ID, run-record schema version, workflow hash, configuration snapshot hash, and the completed-work index (step/item → input-hash and result reference). A missing or corrupt snapshot is never fatal: resume reconstructs state from the event log - which is already a mandated conformance area (SPEC section 7: "checkpoint reconstruction from the event log").

**Rationale**: The log must exist regardless (it is the evidence layer), so deriving resume state from it keeps the durability hierarchy intact: evidence outranks checkpoint. The snapshot is pure optimization, discardable and rebuildable - the same disposability stance the project takes toward the runner itself.

**Alternatives considered**: Snapshot-only (rejected: makes the checkpoint authoritative over evidence, inverting the durability hierarchy; corrupt snapshot would mean lost state). Log-only (workable, but every resume re-parses the full log; the snapshot is cheap insurance and the reconstruction path keeps it honest).

## R7: Canonical serialization and default materialization

**Decision**: The canonical form of a validated workflow is deterministic JSON: UTF-8, keys sorted, compact separators, defaults materialized explicitly, schema-version field included. The workflow hash is SHA-256 over exactly those bytes. SC-003's dual-surface equality test is byte equality of this serialization. Consequence, documented as intended: a future schema version that adds a defaulted field changes canonical bytes and therefore workflow hashes, ending resume hash continuity at the schema-version boundary - a version bump is supposed to end hash continuity, and the explicit schema-version field (FR-009) makes the boundary visible.

**Rationale**: One definition with three jobs (surface equality, workflow hash, resume matching), per the clarification session: two definitions that can drift is the project's documented failure mode. Defaults must be materialized because the two authoring surfaces differ in how defaults arise (YAML omits them, Python construction materializes them); omitting defaults would make canonical bytes depend on which surface authored the file. Materialized defaults also make a months-old record self-describing - the decay-between-semesters guard.

**Alternatives considered**: Exclude-unset serialization (rejected: surface-dependent bytes, breaks SC-003). Semantic model equality (rejected in clarification: leaves hash normalization as a second, driftable definition; fails illegibly through model `__eq__` subtleties). Canonical YAML (rejected: YAML is an input surface only per ADR-002; round-tripping canonical form through YAML imports the formatting ambiguity the canonical form exists to eliminate).

## R8: Error taxonomy (first edition, owned by the run-record contract)

**Decision**: `StepResult.error.category` is a closed enum, first edition:

| Category | Meaning |
|----------|---------|
| `output_validation_error` | Structured output failed validation after bounded internal retries |
| `transport_error` | Connection/network failure reaching a provider or tool |
| `rate_limited` | Provider rate limiting, surfaced after runner retry policy is exhausted |
| `provider_error` | Provider-side error response (server errors, model errors) |
| `timeout` | Step exceeded its configured time budget |
| `nonzero_exit` | Shell component exited nonzero (not retried by default) |
| `assertion_failed` | Assertion component found a failed expectation |
| `upstream_failure` | Skip-reason category: a required upstream item result is a failure |
| `interrupted` | Run interrupted mid-step |
| `unclassified` | Explicit catch-all; nothing is silently coerced into a wrong category |

The spike's observed failure shapes (FR-003) are mapped into these categories; if observation shows a shape this edition cannot represent honestly, the taxonomy is amended in 001b while it is still cheap to change.

**Rationale**: The spec's edge case requires an explicit unclassified category. The taxonomy must exist before the spike report can "map each failure shape to the taxonomy", so the first edition is defined here and pressure-tested by the spike - taxonomy and evidence converge in the same feature.

**Alternatives considered**: Free-text error kinds (rejected: not aggregatable, not comparable across runs). Adopting the substrate's exception hierarchy as the taxonomy (rejected: wrapper drift - the contract would inherit a dependency's churn).

## R9: Spike probe map

**Decision**: Provider coverage per the clarification session: one hosted provider (whichever of the household API keys is present; Anthropic assumed), one local model (Ollama), and a deterministic stub for everything not requiring live calls. The four spikes probe, in order:

1. Usage capture (FR-001): run structured calls through the substrate's agent interface and its usage-reporting surface; confirm per-call token counts and enough cost inputs to compute estimated cost, on both first-attempt success and validation-retry paths; confirm local-model calls report what they report (expected: token counts without prices - the provider-reported versus estimated flag in FR-015 exists for this).
2. Retry accounting (FR-002): configure the substrate's bounded validation-retry mechanism, force validation failures with a strict output schema, count attempts via the substrate's visibility hooks, then layer a simulated runner-level retry outside it and demonstrate the multiplication bound (substrate attempts × runner attempts is known, capped, and recorded).
3. Error shapes (FR-003): drive retry exhaustion, transport failure (unreachable endpoint), and rate limiting (concurrent burst against the hosted provider, or its documented error type if not reproducible on demand); record the exception/result types observed and map each to the R8 taxonomy.
4. Boundary reviews (FR-005 to FR-007): the GradeBot skeleton with the substrate used only inside the per-item call (does anything outside the call get easier with the substrate?); the evals review against the 2×2×2 scenario; the graph review modeling a fixed two-step workflow, checking node-output → StepResult mapping and whether durable execution offers deterministic item-level resume without owning topology.

API surface names above are hypotheses from training knowledge, deliberately unverified: confirming or correcting them against the current stable release is the spike's job (the entry-gate purpose per ADR-003), and the report must cite the exact version probed.

**Rationale**: The spike is narrowed to exactly the unproven questions; everything already proven in DEMA-LLM and twc-bridge (raw/structured calls across providers) stays out. The hosted-plus-local pair covers the cost-fields axis (provider-reported versus estimated or absent counts) that the run-record contract must represent.

**Alternatives considered**: Pre-resolving API details from documentation during planning (declined - and the docs lookup was explicitly skipped this session: the spike exists to produce executed evidence, not paraphrased docs). All four proven providers (rejected in clarification: re-confirms known ground, slower, costlier).

## R10: Packaging and the wrapper-drift import boundary

**Decision**: One uv-managed project, package `pipyer`. Runtime dependencies of the product code: `pydantic` and `pyyaml` only. PydanticAI is installed via a `spike` dependency group and may be imported only under `spike/` in this feature. A conformance test asserts that the contract modules - `src/pipyer/schema/`, `src/pipyer/records/`, `canonical.py`, `validation.py` - import no substrate. The guard is scoped to the contract modules deliberately, not to all of `src/pipyer/`: Feature 002's `llm` component will live under `src/pipyer/` and legitimately import PydanticAI, so a package-wide assertion would have to be weakened one feature later, and a loosened guard reads as drift even when planned. Scoped this way the guard is permanent - 002 strengthens the suite rather than weakening it. (In this feature the package happens to be substrate-free everywhere; the module-scoped guarantee is what the conformance test pins.) The CLI entry point `pipyer` (subcommand `validate`) is declared in `pyproject.toml`.

**Rationale**: "Pipyer owns artifact and evidence semantics only; PydanticAI owns model-call mechanics" (constitution, Operational Constraints) becomes mechanically checkable: the contracts must survive a substrate swap, so they must not import it. The dependency group keeps the spike runnable (`uv run --group spike ...`) without making the substrate a product dependency one feature early.

**Alternatives considered**: Separate spike project (rejected: friction for a disposable artifact; the dependency group achieves the same isolation). Making pydantic-ai a runtime dependency now (rejected: Feature 002 is where the `llm` component earns it; until then it would be an unused import surface). Package-wide import guard (rejected: see decision - guards that must be weakened on schedule teach reviewers to ignore guards).

## R11: `python` component versus `shell` with `uv run`

**Decision**: Keep `python` as a distinct component type. This deliberately supersedes the ADR-002 knock-on note (vault) that a separate code component is unnecessary for v1; the supersession is recorded here, and the vault ADR was annotated accordingly on 2026-06-11 after the plan review - exit notes reference that existing annotation rather than flagging it as owed. The I/O mechanics are identical to `shell` (static script path, JSON stdin → JSON stdout) and that is acknowledged: the type exists for classification, not mechanics.

**Rationale**: The falsification census (FR-019, SC-008) and every future language-creep review must enumerate and judge code steps. A distinct component type makes transformation steps visible and countable in the artifact itself - `component: python` declares "this is a transformation" to a reader, a reviewer, and a census filter - rather than camouflaged among external-tool invocations, where the census degrades into a manual intent-audit of every `shell` step. ADR-004's human-first reading requirement is served by the label. (Note: the earlier justification - "ADR-004 names Python steps" - supported Python steps existing, not a distinct component type; this rationale is the one that actually carries the decision.)

**Alternatives considered**: `shell` with `uv run python ...` per the ADR-002 knock-on (rejected: erases the transformation/tool distinction the census depends on; every shell step becomes census workload forever). A `python` alias that serializes as `shell` (rejected: two names for one canonical form would make the census filter lie about the artifact).

## R12: Empty collections - matrix dimensions versus `each`

**Decision**: The two halves of the spec's empty-collection edge case resolve differently because their emptiness is visible at different times. An empty matrix dimension (`matrix: {dim: []}`) is present in the workflow file at dry-run and is rejected at validation: zero executable cells is an authoring error, and the decay guard demands it fail loudly before execution rather than produce an empty run. An empty `each` collection is runtime input data (how many students submitted), invisible at dry-run: the workflow validates, and the run records zero per-item results explicitly - an execution-behavior fixture authored in this feature and exercised against the Feature 002 runner.

**Rationale**: Dry-run can only judge what the artifact contains (Principle II: fan-out is a function of workflow plus input data). Where the artifact itself encodes zero work, reject loudly; where the data does, record the zero explicitly - never silently.

**Alternatives considered**: Validating empty matrix dimensions with a warning (rejected: warnings rot, and nothing consumes a zero-cell run). Rejecting empty `each` collections at runtime (rejected: an empty submission set is a legitimate state of the world, not an error - the evidence layer records it).

## R13: Toolchain - CLI library, lint/format, type checking, build backend

**Decision**: `typer` for the CLI (annotated-options style per the danvas reference implementation), `ruff` for both formatting (`ruff format`) and linting (`ruff check`), `ty` for type checking, and uv's native build backend (`uv_build`) instead of hatchling. All configured in `pyproject.toml`; ruff and ty live in the dev dependency group; typer is a runtime dependency (the CLI is product).

**Rationale**: Owner-stated standards, with a working reference: danvas (`/Volumes/Casa/dev/danvas`, the most recently updated of the household CLIs) is a typer application whose annotated-option pattern `pipyer validate` follows. A single Astral toolchain (uv, ruff, ty) minimizes configuration surface - Principle V applied to tooling. The CLI contract is unchanged: typer's usage-error exit code is 2, which matches the contract's exit-code table as already written.

**Alternatives considered**: argparse (rejected: owner preference; typer also gives flag handling and help text with less code). hatchling (rejected: `uv_build` is the native backend for a uv-managed src-layout pure-Python package; one fewer third-party build dependency). mypy/pyright (not chosen: `ty` is the owner's standard and keeps the toolchain single-vendor; if ty cannot yet handle a Pydantic v2 construct, the fallback is a targeted ignore with a comment, not a checker switch).

## R14: Secrets - the household 1Password pattern

**Decision**: Adopt the owner's established credentials pattern, taken from its two newest implementations: twc-bridge's `secrets.py` (the cleanest module - provider classes for `1password` and `env`, an `auto` chain, a process-local cache, typed errors, and a `(secret, provider_name)` return so provenance is reportable without logging the secret) and danvas's `auth.py` plus CLI wiring (the newest - `op read <op://reference>` via subprocess with a `shutil.which("op")` availability check, provider/reference/env-var configurable per invocation with env-var fallbacks). Pipyer naming: `PIPYER_SECRET_PROVIDER` (`auto` default), `PIPYER_<KEY>_OP_REFERENCE` (e.g. `PIPYER_ANTHROPIC_API_KEY_OP_REFERENCE`), falling back to the conventional provider env var (e.g. `ANTHROPIC_API_KEY`).

In this feature only the spike consumes secrets: the resolver is vendored into `spike/_common.py` (disposable, like the rest of the spike). Product adoption happens in Feature 002 when the `llm` component earns it, as `src/pipyer/secrets.py` - outside the contract modules, so the import-boundary guard is unaffected. The load-bearing guarantee is unchanged: workflow files and run records never contain credentials (the schema has no credential fields; the config snapshot excludes secrets).

**Rationale**: Build by extraction applies to infrastructure conventions too: this exact provider chain has shipped twice (twc-bridge May 2026, danvas June 2026) and is the owner's working standard. The `(secret, provider_name)` tuple matches the evidence-layer instinct - record where the credential came from, never what it was. The constitution's secrets constraint was amended (v2.1.0) from environment-only to resolved-at-call-time via op or env.

**Alternatives considered**: Environment variables only, as originally written (superseded: actual practice is op-first with env fallback; env-only makes every real invocation start with manual `op read` exports - the friction the household tooling exists to eliminate). `op run --env-file` wrapper invocation (compatible - it populates the env leg - but not sufficient alone: the in-process chain gives legible failures naming what was tried). A secrets file on disk (rejected: the constitution forbids stored credentials).

## Watch item (recorded, not built): static argv and the census

The GradeBot fixture will stress the static-argv rule in exactly one place: a per-item value needed in an argument position (the test runner needs the submission path in argv). Under the current design that forces a wrapper script whose sole job is moving an env var into argv - precisely the shape the census flags. If the census trips there, the principled relaxation already exists inside ADR-004's rules: allow a Ref as an element of the argv list. That is a reference in a data position, not interpolation into a string - it does not breach the no-templating line. This is recorded so a census verdict at that spot is read as "apply the narrower compliant relaxation," not as ADR-004 failing. Nothing is pre-built.
