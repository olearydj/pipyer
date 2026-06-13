# Phase 0 Research: Workflow Runner

Decisions continue Feature 001's numbering (R1-R14 live in `specs/001-pydanticai-spike-contracts/research.md`). Binding inputs (SPEC section 6, exit notes, the 8 fixtures) are not re-decided here; this file resolves only the new ground the brief delegated to planning.

## R15. Secret-resolution failure: eager preflight, no taxonomy change

**Decision**: `pipyer run` performs a secrets preflight after validation and before the run directory is created: for every model alias referenced by an `llm`/`llm_judge` step, resolve the credential through the R14 chain, record the provider name, discard the value. Any failure aborts with a CLI error (exit code 2, same class as validation failure) naming the alias, the key, and the providers tried. Because preflight failure precedes run start, no run record exists and no error-taxonomy category is needed - the taxonomy stays closed. At call time the component resolves again (constitution: secrets resolved at call time); a mid-run resolution failure after a passing preflight is a double-fault mapped to `provider_error` with detail `secret_resolution_failed` - reachable only if the environment changed mid-run, and recorded loudly rather than modeled as a first-class category.

**Rationale**: the workflow declares its aliases, so the runner knows before step one whether every needed credential resolves; failing lazily mid-batch wastes real spend. Matches the loud-stale-failure principle and resolves the carried note in `planning-notes.md`. Local aliases (no credential) skip preflight by construction.

**Alternatives considered**: lazy resolution at first LLM call (rejected: mid-batch failure after spend); new `config_error` taxonomy category (rejected: the taxonomy is a closed conformance surface and preflight failures never produce a `StepResult`; a category without a producible record is dead schema).

## R16. Two additive schema changes, conformance-tested in the same change set

**Decision**:

- `ModelAlias.output_mode: Literal["tool", "native", "prompted"] | None = None` - structured-output mode per alias (exit-note obligation). `None` means provider default for hosted aliases; local aliases (Ollama base URLs) MUST set it explicitly - validation gains a rule rejecting local aliases without `output_mode` (the "never auto-picked" guarantee enforced at validation, not at call time).
- `LlmConfig.timeout_s: int | None = None` and `LlmJudgeConfig.timeout_s: int | None = None` (ge=1), completing the timeout surface that `shell`/`python` already have.

Hash-continuity consequence, corrected at plan review: the canonical serialization materializes defaults (`canonical.py`: `model_dump`, "never exclude_unset" - R7 as decided and implemented), so these additions appear as `null` in the canonical bytes of every existing workflow and change every existing hash. R7 anticipated exactly this and defined the rule: adding a defaulted field ends hash continuity at a schema-version boundary, and the version bump is what makes the boundary visible. Therefore the workflow `schema_version` bumps to `"2"`: all in-repo workflow files and fixtures update their version string, the supported-version set becomes `{"2"}`, and a conformance test asserts version-`"1"` files are rejected with the legible unsupported-version error. Cross-version resume ends by design (a v1-era checkpoint never hash-matches v2 work) - true, intended, and visible rather than a silent discontinuity under an unchanged version string. The cost is trivial now (every existing workflow lives in this repo); the alternative - silent hash drift - would make resume diffs lie about why work recomputed. Under R7, hash identity is semantics; "additive" describes validation compatibility, not hash compatibility. Both fields join the FR-013 field-tripwire census, and conformance tests for both ship in the same change set.

**Rationale**: the exit notes make output-mode configurability a verbatim obligation; the DEMA air-gap path depends on NativeOutput for local models. Timeout taxonomy category exists; the schema lacked the knob only for LLM steps.

**Alternatives considered**: output mode on `LlmConfig` per step (rejected: it is a property of how a model endpoint behaves, not of a step's intent; alias-level is the exit-note wording); enforcing local-alias explicitness at call time (rejected: validation-time is earlier and `pipyer validate` parity demands it).

## R17. Run identity and directory layout

**Decision**: `run_id = <UTC yyyymmdd-HHMMSS>-<6-hex workflow_hash prefix>` (e.g., `20260611-143012-a3f2c1`). Layout under `<results_dir>/<run_id>/`:

```text
<results_dir>/<run_id>/
├── events.jsonl      # append-only event log (authoritative)
├── events.jsonl.lock # single-writer lock (R18), removed on clean exit
├── checkpoint.json   # atomic snapshot (temp+fsync+rename), subordinate to log
├── run.json          # RunRecord, written at terminal status
├── summary.md        # derived markdown summary (regenerable)
└── outputs/          # declared workflow outputs (file_write targets resolve here
                      #   when relative; absolute paths honored for external dirs)
```

`--resume last` resolves to the lexically greatest run-id directory in `results_dir` containing an `events.jsonl` (timestamp prefix makes lexical = chronological); empty/missing results dir is a clear error per the spec edge case.

Collision rule (same workflow started twice within one second produces the same candidate id, which rapid test runs will hit): run-directory creation uses an existence check, and on collision appends `-2`, `-3`, ... to the run id. Lexical ordering is preserved; the id remains boring and self-describing.

**Rationale**: timestamp prefix gives sortable, human-scannable ids; the hash suffix ties a directory to its workflow identity at a glance and breaks collisions within one second. Names are boring and self-describing.

**Alternatives considered**: UUIDs (opaque, unsortable); bare timestamps (collision-prone across rapid test runs); nesting by workflow name (the run record already carries it; extra hierarchy complicates `--resume last`).

## R18. Single-writer enforcement: exclusive lock file

**Decision**: the event-log appender acquires `events.jsonl.lock` via `O_CREAT|O_EXCL`, writing `{pid, started_at}`. A second writer fails immediately with a clear error. Staleness: if the lock's pid is not alive (`os.kill(pid, 0)` → `ProcessLookupError`), the lock is broken with a recorded `lock_reclaimed` note in the resume diff; otherwise resume refuses to start. The appender is the only code path that writes events; within the process, item-level worker threads hand results to the single appender (queue), so the file has exactly one writing thread.

**Rationale**: O_EXCL is atomic on local filesystems, dependency-free, and auditable. The in-process queue keeps `concurrency > 1` from violating single-writer.

**Alternatives considered**: `fcntl.flock` (advisory locks have surprising semantics on some network mounts - results_dir may live on external volumes per the PII discipline); no enforcement (the spec edge case demands rejection).

## R19. Step execution and timeout enforcement

**Decision**:

- `shell`: `subprocess.run(command, timeout=timeout_s)`; `TimeoutExpired` → `ErrorCategory.timeout`; nonzero exit → `nonzero_exit`, `attempt == 1` (no retry, fixture-pinned).
- `python`: executed as a subprocess (`sys.executable`, script file, JSON over stdin/stdout) with the same timeout mechanism. Subprocess isolation is what makes the timeout enforceable and keeps user code out of the runner process.
- `llm`/`llm_judge`: wall-clock timeout around the agent call (`asyncio.wait_for` on the underlying async call, or thread+join for the sync path); timeout → `ErrorCategory.timeout`. PydanticAI internal validation retries stay bounded by `max_validation_retries` and counted in `usage.validation_attempts` (fixture expects initial+2=3); the runner adds no multiplying retry layer (R5 ownership split).
- Item scheduling: `ThreadPoolExecutor(max_workers=settings.concurrency)` within an `each` step; sequential between steps. Threads suffice because step work is I/O-bound (subprocess waits, network calls); results funnel to the single event appender (R18).

**Rationale**: subprocesses are the only reliable kill boundary in Python; threads are the simplest bounded-parallelism primitive that preserves a single event writer.

**Alternatives considered**: in-process `exec` for python steps (rejected: no enforceable timeout, shared-state hazards); asyncio-everywhere engine (rejected: shell/python are subprocess waits anyway; an async core complicates the deterministic loop for no consumer need at concurrency=1 default).

## R20. Resume matching and checkpoint keying

**Decision**: the existing `CheckpointSnapshot.completed: dict[str, CompletedEntry]` is keyed `"<step_name>"` for scalar steps and `"<step_name>[<index>]"` for `each` items - a key convention, not a schema change. `CompletedEntry.input_hash` is the SHA-256 of the canonical JSON of the step's fully resolved inputs plus its config plus the workflow hash; on resume, a unit is skipped iff its key exists and the recomputed input hash matches. Failed items are recorded in the log but never enter `completed`; `--retry-failed` controls whether they re-execute (without it they remain failed in the resumed run's accounting). The resume report is split deliberately: `run_resumed` records boundary-knowable facts (prior successes eligible for hash-match skip, failed-not-retried, failed-retried, stale-lock reclaim), and `run_finished.totals` records realized `resume_skipped` and `recomputed` keys after each unit's hash is evaluated.

**Rationale**: positional keys match the positional-alignment contract (R2/FR-002 - duplicate item values must not break lookup, so keys must be index-based, never value-based). Hashing resolved inputs makes the v1→v2 config-iteration pattern (brief section 6) fall out for free.

**Alternatives considered**: per-item child dicts (schema change to a frozen contract for zero expressive gain); hashing raw (unresolved) references (would miss upstream-output changes flowing through dotted paths).

## R21. Markdown summary: sections derived from the log alone

**Decision**: `derive_summary(event_log_path) -> str` renders, strictly from parsed events: (1) header - run id, workflow name/hash, status, timestamps, resumed-from if any; (2) totals - steps, items, succeeded/failed/skipped, recomputed vs skipped-on-resume; (3) cost table - per LLM step: model, calls, tokens, estimated cost, counts source; aggregate total; (4) per-step table - status counts, duration; (5) failures and skips - every failure-status and skip-status `StepResult` with category and detail (no silent omissions, US3); (6) declared outputs listing; (7) workflow-reported statistics, by naming convention rather than schema: any declared workflow output whose name starts with `summary_` and whose resolved value is a JSON object is rendered as a section - this is how the GradeBot comparison step's agreement statistics reach the summary (the workflow declares `summary_agreement: steps.compare.output`) without the runner knowing what "agreement" means and without any schema change (corrected at plan review: the earlier `summary: true` flag was an undeclared third schema touch; the convention achieves the same data-flows-up effect with zero schema surface). Regeneration is byte-stable for a given log (no timestamps of generation embedded).

**Rationale**: the run-record contract requires derivability from the log alone (FR-013/SC-005); the `summary_*` output-name convention keeps the runner generic while satisfying "agreement statistics in the run summary" (FR-021) - data flows up, semantics stay in the workflow, and the frozen schema is untouched.

**Alternatives considered**: a `summary: true` flag on outputs or steps (rejected at plan review: an undeclared schema change contradicting R16's two-touch claim, compounding the hash-continuity question for zero gain over a convention); hard-coding a comparison section (runner learns GradeBot semantics - Feature 003 scope creep and a Principle V violation); writing summary incrementally during the run (a second derivation path that can drift from the log; regeneration is the only path).

## R22. CLI surface

**Decision**: `pipyer run <workflow.yaml> [--input k=v]... [--resume <run-id>|last] [--retry-failed] [--dry-run] [--results-dir PATH] [--json]`. Semantics: `--input` values parse as YAML scalars (so `k=3` is an int) and must correspond to declared `InputDecl`s; `--dry-run` invokes exactly `validate_file()` and exits with its codes (one implementation, FR-011); `--retry-failed` requires `--resume`; `--results-dir` overrides `settings.results_dir`. Exit codes: 0 completed; 1 halted (budget) or finished-with-failures; 2 validation/preflight/usage error; 130 interrupted (SIGINT convention). `--json` emits the `RunRecord` to stdout for scripting parity with `validate --json`.

Status/exit-code mapping, made explicit: `RunRecord.status` is `completed | halted | interrupted` and `completed` includes runs with within-budget item failures - the status describes the run's lifecycle, the exit code describes whether anything needs attention. Exit 0 requires status `completed` with zero failed units; status `completed` with failed items exits 1, as does `halted`; `interrupted` exits 130.

**Rationale**: matches the spec's approximate shape exactly where it is prescriptive and fills the rest with typer/POSIX conventions already used by `pipyer validate`.

**Alternatives considered**: `pipyer resume` as a separate command (two entry points to one engine invites drift; a flag keeps one code path); `--set` for inputs (the spec names `--input`).

## R23. Deterministic stub and test injection hooks

**Decision**: the runner accepts explicit, recorded test hooks as keyword arguments - the fixtures already pin them: `interrupt_after_items: int | None` (raise a controlled interruption after N item completions), `force_invalid_llm_output: bool` (route LLM steps to a stub that fails output validation), `settings: dict | None` (override workflow settings), `inputs: dict | None`. Stub routing: `run_workflow(..., model_overrides={"alias": TestModel(...)})` lets conformance tests inject PydanticAI's `TestModel` without network; hook usage is recorded in `RunRecord.config_snapshot` so no run lies about how it was produced. Hooks live in the public `run_workflow` signature (the fixtures call them positionally as kwargs) but are documented as test surface.

**Rationale**: the 8 fixtures are unrewritable acceptance tests; their kwargs are therefore API. Recording hook use keeps Principle V honest (no hidden state).

**Alternatives considered**: monkeypatching internals from tests (fixtures don't - they call the public API; adapting them is forbidden); environment-variable switches (hidden state, V violation).

## R24. Acceptance workflow shape and comparison step

**Decision**: `workflows/gradebot-t2/` holds `workflow.yaml`, rubric prompt files, and `compare.py`. Corpus paths, `t2-config.json`-derived point weights and deduction parameters, and baseline file paths enter as declared workflow inputs (data, not code - FR-020); nothing under `workflows/` contains PII. Pipeline: collect submissions (`file_read`/`python` over `inputs/submissions`) → per-problem test harness (`shell`, `each` over students) → rubric grading (`llm`, `each`, pinned alias = archived v2 model per FR-023) → comparison (`python` running `compare.py`: per-entry exact-match vs both baselines, quantized-delta cause lookup, known-patched and override annotations, three-category classification per FR-022; emits the statistics object, declared as the workflow output `summary_agreement` per R21's naming convention) → `file_write` for feedback files and the comparison record into the run's `outputs/` (external results dir at acceptance time). The 3 absent students flow through as items with empty submissions producing explicit `StepResult`s; the academic-integrity override is an annotation row in `compare.py`'s output keyed from a small, PII-free annotations input file.

**Rationale**: implements clarifications Q1-Q3 directly; keeps every judgment the spec called data as data; the workflow is itself the demonstration that the schema needs no new machinery for real grading.

**Alternatives considered**: keeping the workflow outside the repo next to the corpus (rejected: the workflow has no PII and is the feature's primary exhibit; only inputs and outputs stay external).

## R25. Runner retry policy: the slot exists, the default is off (added at analyze review, finding C1)

**Decision**: Feature 002 implements no automatic in-run retries at the runner level. "The runner owns transport-level and run-level retries" (FR-005) means the policy slot lives in the runner - and in this feature the policy is: every failure, including transient categories (`rate_limited`, `transport_error`), is recorded with its taxonomy category and the unit proceeds per skip/budget policy. The recovery path for transients is `--resume --retry-failed`, which re-executes failed units and increments `StepResult.attempt` - the frozen contract's `attempt` field counts exactly these resume-cycle re-executions in this feature. Nothing auto-retries in-run: uniform with the side-effecting-steps rule, so the whole runner has one retry story.

**Rationale**: Principle V - an improvised mid-implementation backoff policy is precisely the hidden behavior the constitution forbids, and no current consumer needs in-run retries (the acceptance run can take a failed unit through one explicit resume sweep; spend and audit both prefer the recorded two-pass shape). The spike's non-multiplication evidence (runner attempts × bounded component validation retries, observed 2 × 3 = 6) becomes the bound proof when a consumer does pull in-run retries - the likely puller is DEMA's large matrix runs (Feature 003), where a thousand-cell run cannot reasonably resume per transient. That feature adds a `retry:` settings block (explicit, recorded, bounded) rather than a hardcoded default.

**Alternatives considered**: bounded in-run retry for transient categories now (rejected: machinery - backoff timing, jitter, per-category budgets - with no consumer demanding it; ADR-005); retrying only `rate_limited` (rejected: a special case inside a policy that otherwise doesn't exist; worse than none).
