# Phase 1 Data Model: Workflow Runner

Feature 001 contracts (`Workflow`, `Settings`, `Step`, `StepResult`, `ErrorCategory`, `RunRecord`, `CheckpointSnapshot`, events, `parse_event_log`) are frozen and not restated; this file covers what Feature 002 adds or pins down. Schema additions are the two fields in research R16, conformance-tested in the same change set.

## Schema additions (frozen modules, additive for validation - hash-breaking per R7)

Both additions materialize as `null` in canonical bytes (R7: defaults materialized), changing every existing workflow hash; per R16 as corrected at plan review, the workflow `schema_version` bumps to `"2"`, all in-repo workflow files and fixtures update, the supported-version set becomes `{"2"}`, and a conformance test asserts version-`"1"` files are rejected with the legible unsupported-version error. Cross-version resume ends at the boundary by design.

### ModelAlias.output_mode

| Field | Type | Rules |
|-------|------|-------|
| `output_mode` | `Literal["tool", "native", "prompted"] \| None = None` | Optional for hosted aliases (provider default). Validation rule (new, in `validation.py`): a local alias (base URL points at a local endpoint) without explicit `output_mode` is a validation error - local aliases are never auto-picked. |

### LlmConfig.timeout_s / LlmJudgeConfig.timeout_s

| Field | Type | Rules |
|-------|------|-------|
| `timeout_s` | `int \| None = None`, `ge=1` | Wall-clock bound on the model call including internal validation retries. Timeout maps to `ErrorCategory.timeout`. |

## Runner entities (new, in `src/pipyer/runner/`, not contract modules)

### Run (returned by `run_workflow`)

The in-memory handle the fixtures exercise. Not serialized itself; its durable projection is `RunRecord` + the event log.

| Field | Type | Notes |
|-------|------|-------|
| `run_id` | `str` | `<utc-stamp>-<hash6>` (R17) |
| `status` | `str` | mirror of `RunRecord.status`: `completed` / `halted` / `interrupted` |
| `record` | `RunRecord` | includes `halt_reason` when halted |
| `events` | `list[dict]` | parsed events for this run (fixtures introspect) |
| `recomputed_step_count` | `int` | units executed this invocation that had prior results (0 on clean resume) |
| `event_log_path` | `Path` | `<run_dir>/events.jsonl` |
| `checkpoint_path` | `Path` | `<run_dir>/checkpoint.json` |
| `run_dir` | `Path` | `<results_dir>/<run_id>/` |

### RunContext (internal)

Carries resolved state through the engine: workflow, `workflow_hash`, resolved inputs (CLI `--input` merged over `InputDecl` defaults), alias table with secrets *provider names* (never values), settings (workflow settings overlaid by recorded test/CLI overrides), event appender handle, checkpoint state, budget counters, model overrides (R23).

### ExecutionUnit (internal)

The schedulable atom: `(step, index | None)`. Key convention `"<step>"` or `"<step>[<index>]"` (R20) - the identity used in checkpoint `completed`, skip bookkeeping, and the resume diff.

| Field | Type | Notes |
|-------|------|-------|
| `key` | `str` | positional, never value-based (duplicate `each` items safe) |
| `input_hash` | `str` | SHA-256 over canonical JSON of resolved inputs + step config + workflow hash |
| `state` | enum | `pending → running → succeeded / failed / skipped(upstream) / not_attempted(halt)` |

State transitions append events; no state lives only in memory past an event boundary (log authoritative, R6).

### Budget tracker (internal)

Counts item failures per `each` step and run-wide; trips when `max_failures` exceeded or `max_failure_rate` exceeded over attempted items. Tripping emits `RunHaltedEvent` with `halt_reason` and marks remaining units `not_attempted` (recorded in the halt event payload, per the spec edge case).

### Lock file (`events.jsonl.lock`)

`{ "pid": int, "started_at": iso8601 }` - O_EXCL acquisition; stale-reclaim per R18, reclaim noted in the resume diff.

### Resume diff (payload of `run_resumed` event + summary section)

| Field | Type |
|-------|------|
| `skipped` | `list[key]` (prior successes eligible for hash-match skip at the boundary) |
| `recompute` | `list[{key, reason}]` reserved; realized recomputes are recorded in `run_finished.totals.recomputed` |
| `failed_not_retried` | `list[key]` |
| `failed_retried` | `list[key]` (only with `--retry-failed`) |
| `lock_reclaimed` | `bool` |

## Event vocabulary (existing types, payload conventions pinned)

- `run_started`: includes `config_snapshot` (resolved inputs, alias table with provider names, settings, test hooks used - R23).
- `each_expanded`: `{step, item_count}` - emitted even when `item_count == 0` (fixture 7).
- `step_result`: wraps `StepResult`; skip records carry `error.category == "upstream_failure"` with the upstream key in detail.
- `run_resumed`: resume diff payload above.
- `run_halted`: `{halt_reason, attempted, failed, not_attempted, attempted_units, failed_units, not_attempted_units}`.
- `run_finished`: terminal totals.

## Comparison record (workflow output, not a runner type)

Produced by `compare.py` (R24); JSON + rendered markdown into `outputs/`. Per entry (student × problem): workflow score, raw-v2 score, published score, match flags per baseline, delta, implied cause (quantized lookup), classification `agrees | expected_human_correction | unexplained`, annotations (known-patched, academic-integrity override, absent). Statistics object (per-baseline exact-match rates, three-category counts, unexplained-above-floor figure) is declared as a workflow output named `summary_agreement` so `derive_summary` surfaces it via the `summary_*` naming convention (R21, no schema change).
