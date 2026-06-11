# Spike Report: PydanticAI Capability Spike (001a)

**Date**: 2026-06-11 **Versions probed**: pydantic-ai 1.106.0, pydantic 2.13.4, genai-prices 0.0.65 (bundled), Python 3.14 (project venv, `requires-python >= 3.12`) **Evidence**: `spike/results/*.json` (raw observations), `spike/0*.py` (the probes; disposable) **Status**: AWAITING CROSS-SESSION REVIEW (T013) - the GO/HALT line at the bottom is deliberately unfilled by this session.

Three legs could not run inside this session's sandbox and are listed under Pending Live Confirmations with exact rerun commands. The boundary recommendation does not depend on them; the field-level evidence they would add is identified inline.

## Q1: Usage capture into the StepResult shape (FR-001)

Confirmed on the deterministic stub leg; hosted and local legs pending.

- `result.usage` (a property in 1.106.0; the method form is deprecated - observed via deprecation warning) returns `RunUsage` with `input_tokens`, `output_tokens`, cache and audio token fields, `details`, `requests`, `tool_calls`. These mapped losslessly into the FR-015 cost-field shape; see `01_usage_capture.json` for complete StepResult-shaped records.
- Validation-retry path: usage aggregates across attempts within one run - the validator-rejected first attempt run showed `requests: 2` with token counts covering both attempts (121 input / 21 output vs 54 / 7 on the clean path). Per-call capture on retry paths is therefore native, not reconstructed. (FR-001 satisfied.)
- Cost inputs: `RunUsage` carries counts, never prices. genai-prices ships with pydantic-ai and `calc_price(usage, model_ref=...)` returns input/output/total prices from its bundled price tables. For the stub it correctly raises `LookupError` (no such model) - evidence that `estimated_cost` must be nullable and `counts_source`/`cost_table_version` must be recorded, exactly as FR-015 specifies. Recommendation: runner computes `estimated_cost` at record-write time via genai-prices; `cost_table_version` records the genai-prices version; local models get `counts_source: estimated` (or absent prices) - the run-record contract already represents all of this.

## Q2: Retry accounting (FR-002)

Confirmed entirely on the stub (the mechanics are model-independent). From `02_retry_accounting.json`:

- Bounded: `retries=2` produced exactly 3 attempts at exhaustion, then raised - the bound is honored, never exceeded.
- Countable and visible, three independent ways: `usage.requests` (2 on a one-retry success), `RetryPromptPart` count in the `capture_run_messages` transcript (1), and the output-validator call count (2). `validation_attempts` in the run record can be populated from `usage.requests` without instrumentation.
- Non-multiplying: 2 runner-level attempts over an always-failing agent with `retries=2` produced exactly 2 × 3 = 6 model calls. Both bounds are explicit; nothing hidden. The substrate performs no transport-level retries by default - HTTP retry is opt-in via the `pydantic_ai.retries` tenacity transports - so the SPEC section 6 rule (runner owns transport retries and run-level policy; component validation retries bounded and counted) maps onto the substrate with no overlap. (FR-002 satisfied.)

## Q3: Error shapes → taxonomy (FR-003)

From `03_error_shapes.json`:

| Observed | Shape | Taxonomy (R8) |
|----------|-------|---------------|
| Validation-retry exhaustion | `UnexpectedModelBehavior` ("Exceeded maximum output retries (N)"), MRO via `AgentRunError` → `RuntimeError` | `output_validation_error` |
| HTTP 429 | `ModelHTTPError` with `status_code`, `model_name`, `body` attrs; subclass of `ModelAPIError` | `rate_limited` |
| HTTP 5xx / provider errors | same `ModelHTTPError` shape, discriminated by `status_code` | `provider_error` |
| Connection failure | `ModelAPIError` family expected; pending live confirmation (sandbox blocked the provider SDK import) | `transport_error` |

Load-bearing observation: the simulated 429 propagated immediately despite `retries=2` - Agent retries cover output validation only, confirming the retry-ownership boundary from Q2.

Mapping rule for 001b: catch `AgentRunError`; discriminate `ModelHTTPError` by status code (429 → `rate_limited`, else `provider_error`), non-HTTP `ModelAPIError` → `transport_error`, `UnexpectedModelBehavior` → `output_validation_error`.

Proposed taxonomy amendments (for 001b, T028):
- `ContentFilterError` (provider refused content): map to `provider_error` with the type preserved in `error.detail` - no new category until a consumer observes one live (build by extraction).
- `IncompleteToolCall` (truncated structured output): map to `output_validation_error` with detail.
- `FallbackExceptionGroup`: only arises with multi-provider fallback models - out of v1 scope; `unclassified` would catch it honestly if ever seen.
- Net: no enum changes required; two documented mappings into existing categories.

## Q4: Interface recommendation (FR-004)

Per-step `Agent` construction from workflow data, with `StructuredDict` for output schemas:

- `Agent(model, output_type=StructuredDict(json_schema), retries=cfg.max_validation_retries)` where `model` is the alias-resolved string (e.g. `anthropic:claude-haiku-4-5`) built at call time. Confirmed working: `StructuredDict` accepts a plain JSON Schema dict (data, not code) and returns a validated JSON-compatible dict - exactly the shape the workflow file declares under ADR-004 and exactly what a `StepResult.output` stores. No Python-class generation, no code in the workflow.
- Model selection stays workflow-configured: Agent accepts the model string per construction; alias settings pass as `model_settings`. The `direct` API offers nothing extra for this component; the Agent layer is where output validation and retry bounding live.

## Boundary test: GradeBot skeleton (FR-005, SC-007)

From `04_gradebot_skeleton.json`: 3 submissions, interrupt after item 0 (exit 3), resume completed the batch with `computed_this_run: 3` (bob's test run + skip + carol's two steps) and zero recomputation of alice's completed steps (input-hash match). 6 events: 4 success, 1 failure (`nonzero_exit`, the forced syntax error), 1 skip (`upstream_failure`) - every item evidenced, no silent omissions.

Boundary answer: the substrate was used strictly inside the per-item grade call. Iteration, checkpointing (atomic-rename), JSONL evidence, skip policy, and content-hash resume were ~60 lines of plain code for which the substrate offered nothing. PydanticAI does not help with batch orchestration beyond the LLM call.

## Pydantic Evals review (FR-006)

From `05_evals_review.json`: `Dataset.evaluate_sync` binds exactly one task; the 2×2×2 scenario required an outer loop constructing task closures per (prompt, alias) combination - the loop Pipyer's matrix expansion would own, with no cell-parameter attachment on report cases (caller bookkeeping) and no usage surfaced per case (`has_usage_on_case: false`). Evals is case-level scoring orthogonal to matrix execution.

Recommendation: defer. Revisit post-v1 as an optional judge/eval engine invoked inside steps (composition, not reimplementation).

## Graph and durable execution review (FR-007)

From `06_graph_review.json`:

- The `BaseNode`-based `Graph` runner and its persistence machinery are deprecated for removal/repurposing in pydantic-graph v2 (import-time warnings captured; `GraphBuilder` is the announced replacement). Building Pipyer's core on it would chain the runner to an API scheduled to vanish.
- Snapshots are node-centric `(node, whole-state, status, timestamps)` - state checkpoints, not per-step results: no per-node output, error, usage, or cost. Mapping to `StepResult` would mean reconstructing outputs from state diffs.
- Item-level resume would require one node per item - node count derived from input data, i.e. dynamic graph construction, colliding with workflows-are-data (ADR-004) and deterministic topology (Principle II). Topology lives in code (return-type annotations): a pydantic-graph graph IS a program, the artifact shape ADR-004 rejects.

Recommendation: ignore for v1. Revisit only if GraphBuilder v2 someday offers item-level durable semantics worth wrapping.

## Boundary outcome

**Standalone runner - current hypothesis CONFIRMED** (one of the four SPIKE.md outcomes; not thin layer, not conventions package, not abandon).

The boundary, as evidenced:

- PydanticAI owns: model-call mechanics - providers, structured output (`StructuredDict`), bounded output-validation retries, usage counts, error shapes. Confirmed excellent at exactly this.
- Pipyer owns: the workflow artifact, `each` and matrix expansion, `StepResult` and JSONL evidence, content-hash resume and checkpointing, skip policy, failure budgets, transport/run-level retry policy, cost computation at record-write time, CLI UX. Confirmed that the substrate offers nothing for any of these (skeleton, evals, graph reviews all point the same direction).

Wrapper-drift note: every substrate surface this spike touched stays inside the future `llm` component; nothing leaks into the contract modules (the R10 guard enforces this).

## Pending live confirmations

Sandbox limits this session: outbound network is allowlisted (no provider APIs, no localhost Ollama), and the read policy denies paths matching `*secret*`/`*credentials*`, which blocks importing the `openai` and `anthropic` SDK packages entirely (each contains such a file). None of this affects the boundary outcome; it leaves three field-level confirmations to a normal shell:

```bash
uv run --group spike python spike/01_usage_capture.py   # hosted + local usage fields, genai-prices on a real model
uv run --group spike python spike/03_error_shapes.py    # real transport shape (dead-port), live 429 if it occurs
uv run --group spike python spike/04_gradebot_skeleton.py --reset --interrupt-after 1 && \
uv run --group spike python spike/04_gradebot_skeleton.py --resume   # optional: skeleton on a live model
```

What they would add: provider-reported usage field values (incl. cache tokens and `details`), a real `calc_price` result, and the concrete connection-failure exception type. What they would not change: any recommendation above.

## Addendum: live confirmations and cross-session review (2026-06-11, review session)

Two of the three pending legs were closed live during the T013 review (unsandboxed session, Ollama 0.21.2 local):

- Local usage leg, with a finding: the spike's tool-calling output mode (`output_type=Feedback`) failed structured output on every local model tried (llava-phi3 auto-pick: no tool support; qwen2.5-coder 14B and mistral-small 24B: retry exhaustion). Switching to `NativeOutput(Feedback)` succeeded immediately on qwen2.5-coder (requests=1, 47 in / 34 out, provider-reported counts). Feature 002 implication, recorded for the `llm` component design: output mode (tool vs native vs prompted) must be alias-configurable, and local aliases should not be auto-picked - the DEMA air-gap deployment path depends on the native/constrained mode.
- Retry aggregation on a real model (resolves the independent reviewer's dissent, below): an output validator rejecting the first attempt on live qwen2.5-coder produced requests=2, 142 in / 49 out versus the 47/34 clean baseline, validator called twice - usage genuinely aggregates across attempts; the stub result was not a doubling artifact.
- Transport shape, live: a real connection failure raised `ModelAPIError`, completing the Q3 table's pending row as predicted (`transport_error`).

- Hosted leg, closed after the user supplied the op reference (`op://Dev/Anthropic/credential` via `PIPYER_ANTHROPIC_API_KEY_OP_REFERENCE` - the R14 chain worked end to end: `op read` → env → SDK, key value never surfaced). Evidence in `01_usage_capture.json`: provider-reported counts with cache-token fields in `details`, `counts_source: provider_reported`, retry-path aggregation on the live hosted model, and a real genai-prices result (`total_price: "0.002572"` for claude-haiku-4-5, string-form decimals - natively matching the run-record contract's string-serialized decimal rule). The stub's `LookupError` and the hosted success together confirm `estimated_cost` nullability and `cost_table_version` recording exactly as FR-015 specifies.

No pending confirmations remain. Every spike leg has executed evidence.

Cross-session review trail (T013):

1. Independent context-free reviewer (report + evidence + SPIKE.md criteria only): DISSENT, on one specific point - the FR-001 retry-aggregation claim rested solely on the deterministic stub, which cannot distinguish aggregation from doubled counting. All other checks passed: no unsupported claims found beyond that one, all SPIKE.md questions answered from executed code, boundary recommendation independent of pending legs, and the steelmanned thin-layer alternative judged weaker than the standalone case.
2. Resolution: the live retry-aggregation probe above closes the identified gap with executed evidence on a real model. The dissent's condition ("proceed to live confirmation before closing FR-001") is satisfied.
3. Standing reviewer verdict: CONCUR with GO - boundary outcome standalone runner, FR-001/FR-002/FR-003 now evidenced on stub and live-local legs, FR-004 interface confirmed, Evals defer and graph ignore-for-v1 both well-supported (the deprecation evidence for pydantic-graph's runner is decisive on its own).

## Gate (T013)

GO/HALT: **GO** - recorded 2026-06-11.

Boundary outcome: standalone runner, hypothesis confirmed. Review trail: independent context-free reviewer (initial dissent on FR-001 stub-only evidence, resolved by live retry-aggregation probe), standing cross-session reviewer (CONCUR), user arbitration (GO). All spike legs closed with executed evidence; no pending confirmations. ADR-003's entry-gate qualification is satisfied; Phases 4-7 (001b contracts, run records, GradeBot fixture, falsification census) are cleared.

Reviewer inputs: this report, `spike/results/*.json`, `docs/sprint-01/SPIKE.md` decision criteria, the addendum above.
