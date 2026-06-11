# Feature 002 Exit Notes (implementation state: engine complete, acceptance run pending)

Status as of 2026-06-11: T001-T035 and T038-T040 complete. The two gated tasks remain open: T036 (the live acceptance run - real spend against the archived corpus) and T037 (cross-session review of the comparison record, user-arbitrated per SC-008). This file records the implementation findings now so the acceptance session inherits them; the acceptance evidence itself lands in `acceptance-evidence.md` when T036 runs.

## Conformance state

- All 8 Feature 001 execution fixtures pass unskipped. The only changes to `test_execution_fixtures.py`: removed `@F002` skip markers (with the now-unused marker definition and `pytest` import) and removed `# ty: ignore[unresolved-import]` comments that became dead once `pipyer.runner` existed. Zero assertion changes (FR-016/SC-001).
- `test_import_boundary.py` unmodified and green: `pydantic_ai` is imported in exactly one src module, `src/pipyer/runner/components/llm.py` (FR-017).
- Full suite 179 tests green; `ruff format --check`, `ruff check`, `ty check` clean (SC-006). `spike/` is excluded from `ty` (disposable evidence code; current pydantic-ai stubs flag the old spike scripts).

## Contract changes in this change set (constitution VI)

- `ModelAlias.output_mode` (tool/native/prompted, optional) + validation rule `local_alias_output_mode_required`; `LlmConfig.timeout_s` / `LlmJudgeConfig.timeout_s`. Workflow `schema_version` bumped to `"2"`; version `"1"` files rejected legibly; all in-repo fixtures migrated (R16 hash-continuity rule - hash identity is semantics).
- Two additive run-record event types the plan had missed but the fixtures and R20 require: `EachExpandedEvent` (zero-item expansions are recorded, fixture 7) and `RunResumedEvent` (the resume boundary carrying the diff payload). Conformance tests in `tests/conformance/test_schema_additions.py`. This is a recorded deviation from plan.md's "records/ unchanged" claim, surfaced rather than silently absorbed.
- Why the record `schema_version` stays `"1"` while the workflow version bumped to `"2"` (cross-session review, asymmetry made explicit): the workflow bump was forced by hash continuity - canonical bytes are identity, so any byte change is a semantic change. Run-record events have no hash-continuity equivalent: logs are write-once streams read by same-or-newer tooling, pre-002 logs contain none of the new event types and still parse, and adding vocabulary to a stream does not change the shape of any existing line. The version would bump if an existing event's fields changed meaning.

## Findings worth carrying

- *Substrate mutation hazard*: pydantic_ai's `StructuredDict` mutates the schema dict it receives (adds `title`). Before the deep-copy guard in `llm.py::_load_schema`, this leaked into the workflow config and silently shifted later units' input hashes - exactly the class of bug content-hash resume exists to catch. Any future executor handing workflow-owned data to the substrate must copy first.
- *Resolved config refs are part of unit identity*: hashing only resolved inputs + raw config missed `file_write` path changes (a ref string like `inputs.summary_file` is constant while its value moves). The unit hash now includes `path_resolved`; without it, the brief's v1→v2 config-iteration pattern silently fails to recompute the tail.
- *Failed units must not re-execute without `--retry-failed`*: the first implementation re-ran prior failures on resume because only completed units were consulted. Now a prior failure carries over into the resumed run's accounting (`failed_carryover`, no new event) unless the flag is passed.
- *StructuredDict does not enforce `required`*: output validation is real only because the llm executor registers its own schema validator (`_schema_issues`) as a pydantic_ai output validator; that is also what makes bounded-retry exhaustion (fixture 6's `validation_attempts == 3`) reachable.
- *R25 implemented as decided*: no automatic in-run retries anywhere; transient categories record and proceed per skip/budget policy; recovery is `--resume --retry-failed`, which increments `StepResult.attempt`.

## Acceptance run prerequisites (T036, for the next session)

- Workflow: `workflows/gradebot-t2/workflow.yaml` (validates clean, hash-pinned). Alias pinned to `anthropic:claude-sonnet-4-5-20250929` - the archived v2 model per `run_manifest.md` (FR-023). The smoke rehearsal (`tests/unit/test_gradebot_t2_smoke.py`) exercises the full pipeline including no-submission rows, patch tags, the override annotation, and the `summary_agreement` surfacing.
- Items come from the raw baseline CSV's own row set (188 rows), so alignment is by construction; the corpus arithmetic note in T033 is honored by `collect_items.py`.
- Needs at run time: `ANTHROPIC_API_KEY` via the R14 chain; an external gitignored results dir; an `annotations_file` (academic-integrity override for the documented student, absent-student list) authored next to the corpus, never in this repo.
- Estimated spend: 188 sonnet calls with ~2-4k input tokens each.

## Carried to Feature 003 (and beyond)

- Stability measurement: the archived 1.7% (T2) / 17.5% (T1 pre-hardening) nondeterminism numbers are run-comparison-over-identical-reruns evidence for Feature 003's comparison tooling spec.
- The review-and-patch tail (brief section 6) remains expressible in the existing schema (config-iteration reruns fall out of resume; `patches.yaml` apply-and-publish is a `python` + `file_write` tail with the stale-patch guard in the step). Post-002, no new feature machinery required.
- In-run retry policy (R25): the likely puller is DEMA's large matrix runs; when pulled, it arrives as an explicit `retry:` settings block, never a hardcoded default.
- Cost table: `llm.py::COST_TABLE` is deliberately minimal; models not listed record `estimated_cost: null` with the table version. DONE at cross-session review (2026-06-11): the acceptance model `claude-sonnet-4-5-20250929` added with pricing verified against genai-prices ($3/$15 per MTok). Carried trade-off for Feature 003: the spike recommended computing cost via bundled genai-prices (`calc_price`, with `cost_table_version` recording the package version); a hand-pinned table keeps conformance tests deterministic against genai-prices package updates, but means manual maintenance per model. When Feature 003's matrix runs make per-model cost first-class, decide deliberately: genai-prices at record-write time with pinned-package determinism, or the table with a freshness check against genai-prices in CI.
- Minor validation gap found at cross-session review: a `python` step whose script file does not exist fails at runtime as `unclassified` ("script not found"). Script-file existence is checkable at dry-run exactly like prompt files (validation rule 6). Candidate validation rule for the next contracts touch; not blocking T036 (the gradebot scripts exist and are smoke-tested).
