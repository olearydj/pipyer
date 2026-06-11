"""The execution engine (SPEC section 6; contracts/runner-api.md).

Six jobs, nothing else: parse, validate, execute, persist, resume, report.
Sequential steps; `each` items scheduled under settings.concurrency with
results funneled to the single event-log writer; failure budgets halt with a
recorded event; no automatic in-run retries (R25) - recovery is resume.
"""

from __future__ import annotations

import concurrent.futures
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipyer.records.run import (
    EachExpandedEvent,
    RunFinishedEvent,
    RunHaltedEvent,
    RunRecord,
    RunStartedEvent,
    RunStatus,
    StepResultEvent,
)
from pipyer.records.step_result import ErrorCategory, StepError
from pipyer.runner.checkpoint import (
    RECORD_SCHEMA_VERSION,
    build_checkpoint,
    write_checkpoint,
)
from pipyer.runner.components import StepFailure, get_executor
from pipyer.runner.context import (
    RunContext,
    StepState,
    UpstreamFailure,
    new_run_id,
    unit_key,
)
from pipyer.runner.events import EventLog
from pipyer.runner.resume import ResumePlan, load_resume_plan
from pipyer.runner.summary import derive_summary
from pipyer.schema.workflow import Settings, Workflow
from pipyer.secrets import resolve_secret
from pipyer.validation import Issue, validate_file

COMPONENT_VERSION = "0.2.0"


class ValidationFailure(RuntimeError):
    """The workflow failed validation; nothing ran. Carries the issue list."""

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("; ".join(f"{i.loc}: {i.message}" for i in issues) or "validation failed")
        self.issues = issues


class _Interrupted(Exception):
    """Internal control flow for the interrupt hook and SIGINT."""


@dataclass
class Run:
    """The in-memory handle the fixtures exercise (data-model.md)."""

    run_id: str
    status: str
    record: RunRecord
    events: list[dict[str, Any]]
    recomputed_step_count: int
    run_dir: Path
    event_log_path: Path
    checkpoint_path: Path


@dataclass
class _Totals:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    resume_skipped: list[str] = field(default_factory=list)
    recomputed: list[str] = field(default_factory=list)


def _git_commit(workflow_dir: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=workflow_dir,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _resolve_run_inputs(workflow: Workflow, provided: dict[str, Any]) -> dict[str, Any]:
    issues: list[Issue] = []
    resolved: dict[str, Any] = {}
    for name, decl in workflow.inputs.items():
        if name in provided:
            resolved[name] = provided[name]
        elif not decl.required:
            resolved[name] = decl.default
        else:
            issues.append(
                Issue(
                    loc=f"inputs.{name}",
                    code="missing_input",
                    message="required input not provided",
                )
            )
    for name in provided:
        if name not in workflow.inputs:
            issues.append(
                Issue(
                    loc=f"inputs.{name}",
                    code="unknown_input",
                    message="not a declared workflow input",
                )
            )
    if issues:
        raise ValidationFailure(issues)
    return resolved


def _preflight_secrets(
    workflow: Workflow, model_overrides: dict[str, Any] | None = None
) -> dict[str, str]:
    """R15: resolve every needed credential before the run directory exists.

    Returns alias -> provider name ('none' for stub/local aliases). Raises
    SecretResolutionError (from pipyer.secrets) on the first unresolvable key.
    """
    from pipyer.runner.components.llm import secret_key_for

    used_aliases = {
        getattr(step.config, "model")  # noqa: B009 - union-typed config; llm/llm_judge only
        for step in workflow.steps
        if step.component in ("llm", "llm_judge")
    }
    providers: dict[str, str] = {}
    for alias_name in sorted(used_aliases):
        if model_overrides and alias_name in model_overrides:
            providers[alias_name] = "override"  # injected model makes no provider call
            continue
        alias = workflow.models[alias_name]
        key = secret_key_for(alias.model, alias.settings)
        if key is None:
            providers[alias_name] = "none"
        else:
            _secret, provider = resolve_secret(key)  # value discarded; resolved again at call time
            providers[alias_name] = provider
    return providers


def run_workflow(
    workflow_path: Path,
    *,
    results_dir: Path,
    inputs: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    resume: bool | str = False,
    retry_failed: bool = False,
    model_overrides: dict[str, Any] | None = None,
    interrupt_after_items: int | None = None,
    force_invalid_llm_output: bool = False,
) -> Run:
    workflow_path = Path(workflow_path)
    results_dir = Path(results_dir)
    workflow, issues = validate_file(workflow_path)
    if issues or workflow is None:
        raise ValidationFailure(issues)

    run_inputs = _resolve_run_inputs(workflow, dict(inputs or {}))
    effective_settings = Settings.model_validate(
        {**workflow.settings.model_dump(), **(settings or {})}
    )
    secret_providers = _preflight_secrets(workflow, model_overrides)

    resume_plan: ResumePlan | None = None
    if resume:
        resume_plan = load_resume_plan(
            results_dir, run_id=None if resume is True else str(resume), retry_failed=retry_failed
        )
        run_dir = resume_plan.run_dir
        run_id = resume_plan.run_id
    else:
        from pipyer.canonical import workflow_hash

        results_dir.mkdir(parents=True, exist_ok=True)
        run_id = new_run_id(results_dir, workflow_hash(workflow))
        run_dir = results_dir / run_id
        run_dir.mkdir()
        (run_dir / "outputs").mkdir()

    ctx = RunContext(
        workflow,
        inputs=run_inputs,
        settings=effective_settings,
        workflow_dir=workflow_path.resolve().parent,
        run_dir=run_dir,
        run_id=run_id,
        secret_providers=secret_providers,
    )
    hooks = {
        "interrupt_after_items": interrupt_after_items,
        "force_invalid_llm_output": force_invalid_llm_output,
        "settings_override": settings or None,
        "model_overrides": sorted(model_overrides) if model_overrides else None,
    }
    ctx.test_hooks = {
        "model_overrides": model_overrides or {},
        "force_invalid_llm_output": force_invalid_llm_output,
    }

    engine = _Engine(ctx, hooks=hooks, resume_plan=resume_plan)
    return engine.run()


class _Engine:
    def __init__(
        self, ctx: RunContext, *, hooks: dict[str, Any], resume_plan: ResumePlan | None
    ) -> None:
        self.ctx = ctx
        self.hooks = hooks
        self.resume_plan = resume_plan
        self.totals = _Totals()
        self.failure_count = 0
        self.item_completions = 0
        self.halt_reason: str | None = None
        self.interrupted = False
        self.started_at = datetime.now(UTC)
        self.log = EventLog(ctx.run_dir)
        self.prior_completed = resume_plan.completed if resume_plan else {}
        self.retry_units = resume_plan.retry_units if resume_plan else set()
        self.prior_attempts = resume_plan.attempts if resume_plan else {}

    # ------------------------------------------------------------------ events

    def _emit(self, event) -> int:
        return self.log.append(event)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _write_snapshot(self) -> None:
        events = self._all_events()
        write_checkpoint(self.ctx.run_dir / "checkpoint.json", build_checkpoint(events))

    def _all_events(self) -> list[dict[str, Any]]:
        from pipyer.records.run import parse_event_log

        events, _ = parse_event_log((self.ctx.run_dir / "events.jsonl").read_text(encoding="utf-8"))
        return events

    # -------------------------------------------------------------------- run

    def run(self) -> Run:
        ctx = self.ctx
        with self.log:
            config_snapshot = ctx.config_snapshot(self.hooks)
            config_snapshot["config_hash"] = ctx.config_hash(self.hooks)
            config_snapshot["results_dir"] = str(ctx.run_dir.parent)
            self._emit(
                RunStartedEvent(
                    schema_version=RECORD_SCHEMA_VERSION,
                    run_id=ctx.run_id,
                    workflow_name=ctx.workflow.name,
                    workflow_hash=ctx.workflow_hash,
                    config_snapshot=config_snapshot,
                    git_commit=_git_commit(ctx.workflow_dir),
                    started_at=self.started_at,
                )
            )
            if self.resume_plan is not None:
                event = self.resume_plan.boundary_event(
                    schema_version=RECORD_SCHEMA_VERSION,
                    lock_reclaimed=self.log.lock_reclaimed,
                    at=self._now(),
                )
                self._emit(event)
                self._replay_projections()

            status: RunStatus = "completed"
            try:
                for step in ctx.workflow.steps:
                    self._run_step(step)
                    if self.halt_reason is not None:
                        status = "halted"
                        break
            except _Interrupted:
                status = "interrupted"
            except KeyboardInterrupt:
                status = "interrupted"

            if self.halt_reason is not None:
                status = "halted"
                self._emit(
                    RunHaltedEvent(
                        schema_version=RECORD_SCHEMA_VERSION,
                        run_id=ctx.run_id,
                        reason=self.halt_reason,
                        at=self._now(),
                    )
                )

            totals = self._final_totals(status)
            finished_at = self._now()
            self._emit(
                RunFinishedEvent(
                    schema_version=RECORD_SCHEMA_VERSION,
                    run_id=ctx.run_id,
                    status=status,
                    finished_at=finished_at,
                    totals=totals,
                )
            )
            self._write_snapshot()
            record = RunRecord(
                schema_version=RECORD_SCHEMA_VERSION,
                run_id=ctx.run_id,
                workflow_name=ctx.workflow.name,
                workflow_hash=ctx.workflow_hash,
                config_snapshot=config_snapshot,
                git_commit=_git_commit(ctx.workflow_dir),
                started_at=self.started_at,
                finished_at=finished_at,
                status=status,
                halt_reason=self.halt_reason,
                totals=totals,
            )
            (ctx.run_dir / "run.json").write_text(
                record.model_dump_json(indent=2), encoding="utf-8"
            )
            events = self._all_events()
            (ctx.run_dir / "summary.md").write_text(
                derive_summary(ctx.run_dir / "events.jsonl"), encoding="utf-8"
            )

        return Run(
            run_id=ctx.run_id,
            status=status,
            record=record,
            events=events,
            recomputed_step_count=len(self.totals.recomputed),
            run_dir=ctx.run_dir,
            event_log_path=ctx.run_dir / "events.jsonl",
            checkpoint_path=ctx.run_dir / "checkpoint.json",
        )

    def _replay_projections(self) -> None:
        """Rebuild step state from the prior log so references resolve on resume."""
        assert self.resume_plan is not None
        for step in self.ctx.workflow.steps:
            self.ctx.steps[step.name] = StepState(each=step.each is not None)
        for event in self.resume_plan.events:
            if event.get("event") == "each_expanded":
                state = self.ctx.steps.get(event["step"])
                if state is not None:
                    state.item_count = event["item_count"]
            if event.get("event") != "step_result":
                continue
            state = self.ctx.steps.get(event["step"])
            if state is None:
                continue
            key = unit_key(event["step"], event.get("item_index"))
            if event.get("status") == "success":
                state.projections[key] = event.get("output")
                state.failed.discard(key)
            elif event.get("status") == "failure":
                state.failed.add(key)
            else:
                state.skipped.add(key)
        # Fresh run re-evaluates skips and failures; only successes carry over
        # as resolvable projections. Failed/skipped sets reset per unit at
        # execution time below.

    # ------------------------------------------------------------------- steps

    def _run_step(self, step) -> None:
        ctx = self.ctx
        state = ctx.steps.setdefault(step.name, StepState(each=step.each is not None))
        state.each = step.each is not None
        if step.each is None:
            self._run_unit(step, None)
            return

        try:
            collection = ctx.resolve(step.each, index=None, each_ref=None)
        except UpstreamFailure as failure:
            started = self._now()
            self._finish_unit(
                step, None, ("skip", unit_key(step.name, None), started, failure.upstream_key, {})
            )
            return
        if not isinstance(collection, list):
            collection = list(collection or [])
        state.item_count = len(collection)
        self._emit(
            EachExpandedEvent(
                schema_version=RECORD_SCHEMA_VERSION,
                run_id=ctx.run_id,
                step=step.name,
                item_count=len(collection),
                at=self._now(),
            )
        )
        if not collection:
            return

        concurrency = max(1, ctx.settings.concurrency)
        if concurrency == 1:
            for index in range(len(collection)):
                self._run_unit(step, index)
                if self.halt_reason is not None:
                    self._note_not_attempted(step, range(index + 1, len(collection)))
                    return
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            pending = {}
            interrupted: _Interrupted | None = None
            indices = iter(range(len(collection)))
            try:
                while True:
                    while len(pending) < concurrency:
                        try:
                            index = next(indices)
                        except StopIteration:
                            break
                        future = pool.submit(self._execute_unit, step, index)
                        pending[future] = index
                    if not pending:
                        break
                    done, _ = concurrent.futures.wait(
                        pending, return_when=concurrent.futures.FIRST_COMPLETED
                    )
                    for future in done:
                        index = pending.pop(future)
                        try:
                            self._finish_unit(step, index, future.result())
                        except _Interrupted as stop:
                            interrupted = stop
                    if (self.halt_reason is not None or interrupted) and pending:
                        # in-flight units finish and are recorded; nothing new starts
                        for future in concurrent.futures.as_completed(list(pending)):
                            index = pending.pop(future)
                            try:
                                self._finish_unit(step, index, future.result())
                            except _Interrupted as stop:
                                interrupted = stop
                    if self.halt_reason is not None or interrupted:
                        break
            finally:
                remaining = list(indices)
                if remaining and (self.halt_reason is not None or interrupted):
                    self._note_not_attempted(step, remaining)
            if interrupted is not None:
                raise interrupted

    def _note_not_attempted(self, step, indices) -> None:
        # Recorded inside the halt reason/totals; not_attempted units have no
        # StepResult by definition - they were never started, and the halt
        # event plus totals account for them.
        self.totals_not_attempted = getattr(self, "totals_not_attempted", 0) + len(list(indices))

    # ------------------------------------------------------------------- units

    def _run_unit(self, step, index: int | None) -> None:
        self._finish_unit(step, index, self._execute_unit(step, index))

    def _execute_unit(self, step, index: int | None):
        """Runs in a worker thread: produces the outcome without touching shared
        state or the event log; `_finish_unit` (engine thread) records it."""
        ctx = self.ctx
        key = unit_key(step.name, index)
        started = self._now()

        # Resolve inputs first: an upstream failure becomes a skip record.
        resolved: dict[str, Any] = {}
        input_refs: dict[str, str] = {}
        try:
            for name, value in step.inputs.items():
                if isinstance(value, str):
                    input_refs[name] = value
                resolved[name] = ctx.resolve(value, index=index, each_ref=step.each)
        except UpstreamFailure as failure:
            return ("skip", key, started, failure.upstream_key, input_refs)

        config = step.config.model_dump(mode="json")
        # Resolved config refs (e.g. a file path of "item.path" or
        # "inputs.summary_file") are part of the unit's meaning: hash the
        # resolved value, not just the ref string, so an input change that
        # moves only the path recomputes the write (R5/R20).
        if hasattr(step.config, "path"):
            try:
                config["path_resolved"] = ctx.resolve(
                    step.config.path, index=index, each_ref=step.each
                )
            except UpstreamFailure as failure:
                return ("skip", key, started, failure.upstream_key, input_refs)
        input_hash = ctx.unit_input_hash(step.name, _hashable(resolved), _hashable(config))

        prior = self.prior_completed.get(key)
        if prior is not None and prior == input_hash and key not in self.retry_units:
            return ("resume_skip", key, started, input_hash, resolved)
        if (
            self.resume_plan is not None
            and key in self.resume_plan.failed_units
            and key not in self.retry_units
            and prior is None
        ):
            # A prior failure re-executes only with --retry-failed (R20); it
            # stays failed in this run's accounting, already recorded in the log.
            return ("failed_carryover", key, started)

        try:
            outcome = get_executor(step.component)(step, resolved, ctx, index)
        except StepFailure as failure:
            return ("failure", key, started, failure, input_hash, input_refs)
        except UpstreamFailure as failure:
            return ("skip", key, started, failure.upstream_key, input_refs)
        if isinstance(outcome, tuple):
            projection, usage = outcome
        else:
            projection, usage = outcome, None
        return ("success", key, started, projection, usage, input_hash, input_refs)

    def _finish_unit(self, step, index: int | None, outcome) -> None:
        ctx = self.ctx
        state = ctx.steps[step.name]
        kind = outcome[0]
        key = outcome[1]
        started = outcome[2]
        finished = self._now()
        duration_ms = max(0, int((finished - started).total_seconds() * 1000))
        attempt = self.prior_attempts.get(key, 0) + 1

        if kind == "failed_carryover":
            state.failed.add(key)
            self.totals.failed += 1  # still failed; counts against status/exit, not re-run
            return

        if kind == "resume_skip":
            _, _, _, input_hash, resolved = outcome
            state.projections[key] = self._prior_projection(key)
            self.totals.resume_skipped.append(key)
            return

        if kind == "skip":
            _, _, _, upstream_key, input_refs = outcome
            self._emit_result(
                step,
                index,
                status="skipped",
                error=StepError(
                    category=ErrorCategory.UPSTREAM_FAILURE,
                    message=f"upstream unit {upstream_key} failed; skipped by policy (R2)",
                    detail={"upstream": upstream_key},
                ),
                started=started,
                finished=finished,
                duration_ms=duration_ms,
                input_hash="sha256:" + "0" * 64,
                input_refs=input_refs,
                attempt=attempt,
            )
            state.skipped.add(key)
            self.totals.skipped += 1
            return

        if kind == "failure":
            _, _, _, failure, input_hash, input_refs = outcome
            self._emit_result(
                step,
                index,
                status="failure",
                error=StepError(
                    category=failure.category, message=failure.message, detail=failure.detail
                ),
                usage=failure.usage,
                started=started,
                finished=finished,
                duration_ms=duration_ms,
                input_hash=input_hash,
                input_refs=input_refs,
                attempt=attempt,
            )
            state.failed.add(key)
            self.totals.failed += 1
            self.totals.attempted += 1
            self.failure_count += 1
            if key in self.prior_completed:
                self.totals.recomputed.append(key)
            self._check_budget(step, index)
            self._after_item(step, index)
            return

        # success
        _, _, _, projection, usage, input_hash, input_refs = outcome
        self._emit_result(
            step,
            index,
            status="success",
            output=projection,
            usage=usage,
            started=started,
            finished=finished,
            duration_ms=duration_ms,
            input_hash=input_hash,
            input_refs=input_refs,
            attempt=attempt,
        )
        state.projections[key] = projection
        state.failed.discard(key)
        self.totals.succeeded += 1
        self.totals.attempted += 1
        if key in self.prior_completed:
            self.totals.recomputed.append(key)
        self._write_snapshot()
        self._after_item(step, index)

    def _prior_projection(self, key: str) -> Any:
        assert self.resume_plan is not None
        return self.resume_plan.projections.get(key)

    def _emit_result(
        self,
        step,
        index,
        *,
        status,
        started,
        finished,
        duration_ms,
        input_hash,
        input_refs,
        attempt,
        output=None,
        error=None,
        usage=None,
    ) -> None:
        self._emit(
            StepResultEvent(
                schema_version=RECORD_SCHEMA_VERSION,
                run_id=self.ctx.run_id,
                step=step.name,
                component=step.component,
                status=status,
                attempt=attempt,
                output=output,
                error=error,
                started_at=started,
                finished_at=finished,
                duration_ms=duration_ms,
                usage=usage,
                item_index=index,
                input_refs=input_refs,
                input_hash=input_hash,
                component_version=COMPONENT_VERSION,
            )
        )

    def _after_item(self, step, index: int | None) -> None:
        if index is None:
            return
        self.item_completions += 1
        limit = self.hooks.get("interrupt_after_items")
        if limit is not None and self.item_completions >= limit:
            raise _Interrupted()

    def _check_budget(self, step, index: int | None) -> None:
        settings = self.ctx.settings
        if settings.max_failures is not None and self.failure_count > settings.max_failures:
            self.halt_reason = (
                f"failure budget exceeded: {self.failure_count} failures > "
                f"max_failures={settings.max_failures}"
            )
            return
        if settings.max_failure_rate is not None and index is not None:
            state = self.ctx.steps[step.name]
            total = state.item_count or 0
            if total:
                rate = len(state.failed) / total
                if rate > settings.max_failure_rate:
                    self.halt_reason = (
                        f"failure budget exceeded: step {step.name!r} item failure rate "
                        f"{rate:.2f} > max_failure_rate={settings.max_failure_rate}"
                    )

    # ----------------------------------------------------------------- finish

    def _final_totals(self, status: RunStatus) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for name, ref in self.ctx.workflow.outputs.items():
            try:
                outputs[name] = self.ctx.resolve(ref, index=None, each_ref=None)
            except Exception:
                outputs[name] = None
        return {
            "attempted": self.totals.attempted,
            "succeeded": self.totals.succeeded,
            "failed": self.totals.failed,
            "skipped": self.totals.skipped,
            "not_attempted": getattr(self, "totals_not_attempted", 0),
            "resume_skipped": self.totals.resume_skipped,
            "recomputed": self.totals.recomputed,
            "outputs": _hashable(outputs),
        }


def _hashable(value: Any) -> Any:
    """JSON-roundtrippable projection of resolved values (for hashing/recording)."""
    import json

    return json.loads(json.dumps(value, default=str))
