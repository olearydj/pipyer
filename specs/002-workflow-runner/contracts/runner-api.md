# Contract: `pipyer.runner` Public API

This surface is pinned by the 8 pre-authored fixtures in `tests/conformance/execution/test_execution_fixtures.py`. The fixtures are unskipped and never rewritten; if implementation pressure suggests a different API, that is a review finding, not an adaptation (FR-016).

## `run_workflow`

```python
def run_workflow(
    workflow_path: Path,
    *,
    results_dir: Path,
    inputs: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,        # recorded override of workflow settings
    resume: bool | str = False,                     # True = last, str = run-id
    retry_failed: bool = False,                     # only meaningful with resume
    model_overrides: dict[str, Any] | None = None,  # alias -> model instance (test stub injection)
    interrupt_after_items: int | None = None,       # test hook: controlled interruption
    force_invalid_llm_output: bool = False,         # test hook: stub failing output validation
) -> Run
```

Behavior:

- Validates first (same implementation as `pipyer validate`); validation issues raise before any run directory exists.
- Secrets preflight (research R15) after validation, before run-directory creation; failure raises `SecretResolutionError` naming alias, key, providers tried.
- Creates `<results_dir>/<run_id>/` per the run-directory contract; acquires the single-writer lock; appends `run_started` with the full config snapshot (test hooks included when used).
- Executes per SPEC section 6 semantics; returns a `Run` whose fields are listed in `data-model.md`.
- `resume`: locates the prior run (id or lexically-last), replays `events.jsonl` (authoritative; checkpoint is an optimization), computes the resume diff, appends `run_resumed`, executes only non-matching units. `recomputed_step_count == 0` when nothing changed (fixture 1).
- Never raises for step failures, budget halts, or injected interruption - those are recorded statuses; exceptions are reserved for pre-run errors (validation, preflight, lock conflict, missing prior run) and programmer errors.

## `reconstruct_checkpoint`

```python
def reconstruct_checkpoint(event_log_path: Path) -> CheckpointSnapshot
```

Rebuilds the checkpoint purely from the event log (R6); tolerates a corrupt trailing line via the existing `parse_event_log`. `completed` keys follow the `"<step>"` / `"<step>[<index>]"` convention (research R20). Must equal the on-disk checkpoint for any cleanly written run (fixture 3 deletes the checkpoint and compares).

## `derive_summary`

```python
def derive_summary(event_log_path: Path) -> str
```

Markdown derived from the log alone (sections per research R21); contains the run id and `## ` headers (fixture 8); byte-stable across regenerations of the same log; renders any declared workflow output whose name starts with `summary_` and resolves to a JSON object as a section (naming convention, no schema surface).

## Exceptions

| Exception | Raised when |
|-----------|-------------|
| `ValidationFailure` | workflow invalid (carries `list[Issue]`) |
| `SecretResolutionError` | preflight chain exhausted (from `pipyer.secrets`) |
| `RunLockedError` | live lock held by a running pid |
| `NoPriorRunError` | `resume` with no matching run directory |

All other failure modes are recorded events, never exceptions.
