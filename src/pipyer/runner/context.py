"""Run context: resolved inputs, reference resolution, unit identity (R17, R20).

Execution-unit keys are positional - "<step>" for scalar steps,
"<step>[<index>]" for `each` items - never value-based, so duplicate item
values cannot break lookup (FR-002). A unit's input hash covers its fully
resolved inputs, its config, and the workflow hash, so resume skips exactly
the work whose meaning is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipyer.canonical import workflow_hash
from pipyer.schema.refs import Ref, parse
from pipyer.schema.workflow import Settings, Workflow

UNIT_KEY_RE = re.compile(r"^(?P<step>[a-z][a-z0-9_]*)(?:\[(?P<index>\d+)\])?$")


def unit_key(step: str, index: int | None) -> str:
    return step if index is None else f"{step}[{index}]"


def stable_hash(payload: Any) -> str:
    """SHA-256 over canonical JSON (sorted keys, compact) of any JSON-able payload."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def new_run_id(results_dir: Path, wf_hash: str, now: datetime | None = None) -> str:
    """`<UTC yyyymmdd-HHMMSS>-<6-hex hash prefix>`, with -2/-3... on collision (R17)."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    digest = wf_hash.removeprefix("sha256:")[:6]
    base = f"{stamp}-{digest}"
    candidate, n = base, 1
    while (results_dir / candidate).exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


class ResolutionError(RuntimeError):
    """A reference failed to resolve at runtime (post-validation, so a runner bug
    or upstream-failure propagation handled by the caller)."""

    def __init__(self, message: str, *, upstream_failed: str | None = None) -> None:
        super().__init__(message)
        self.upstream_failed = upstream_failed


class UpstreamFailure(RuntimeError):
    """The referenced value is unavailable because its producing unit failed/skipped."""

    def __init__(self, upstream_key: str) -> None:
        super().__init__(f"upstream unit {upstream_key} failed")
        self.upstream_key = upstream_key


@dataclass
class StepState:
    """Runtime state of one step: per-unit projections and outcomes."""

    each: bool
    item_count: int | None = None  # each steps only
    # unit key -> projection mapping (StepResult.output); only successful units
    projections: dict[str, Any] = field(default_factory=dict)
    failed: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)


class RunContext:
    """Everything resolution needs, plus identity hashes."""

    def __init__(
        self,
        workflow: Workflow,
        *,
        inputs: dict[str, Any],
        settings: Settings,
        workflow_dir: Path,
        run_dir: Path,
        run_id: str,
        secret_providers: dict[str, str],
    ) -> None:
        self.workflow = workflow
        self.workflow_hash = workflow_hash(workflow)
        self.inputs = inputs
        self.settings = settings
        self.workflow_dir = workflow_dir
        self.run_dir = run_dir
        self.run_id = run_id
        self.secret_providers = secret_providers  # alias -> provider name, never values
        self.steps: dict[str, StepState] = {}
        self.step_each: dict[str, str | None] = {s.name: s.each for s in workflow.steps}
        self.test_hooks: dict[str, Any] = {}

    # ------------------------------------------------------------ config snapshot

    def config_snapshot(self, hooks: dict[str, Any]) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "inputs": self.inputs,
            "settings": self.settings.model_dump(mode="json"),
            "matrix": self.workflow.matrix,
            "models": {
                name: {
                    "model": alias.model,
                    "settings": alias.settings,
                    "output_mode": alias.output_mode,
                    "secret_provider": self.secret_providers.get(name),
                }
                for name, alias in self.workflow.models.items()
            },
        }
        recorded_hooks = {k: v for k, v in hooks.items() if v}
        if recorded_hooks:
            snapshot["test_hooks"] = recorded_hooks  # no run lies about how it was produced (R23)
        return snapshot

    def config_hash(self, hooks: dict[str, Any]) -> str:
        return stable_hash(self.config_snapshot(hooks))

    # ----------------------------------------------------------------- resolution

    def resolve(self, value: Any, *, index: int | None, each_ref: str | None) -> Any:
        """Resolve one mapping-position value in the context of a unit.

        `index`/`each_ref` describe the consuming unit (None for scalar steps).
        Raises UpstreamFailure when the referenced producing unit failed or was
        skipped - the caller turns that into a skip record, never an omission.
        """
        ref = parse(value)
        if ref is None:
            return value
        return self._resolve_ref(ref, index=index, each_ref=each_ref)

    def _resolve_ref(self, ref: Ref, *, index: int | None, each_ref: str | None) -> Any:
        if ref.root == "inputs":
            return _navigate(self.inputs[ref.segments[0]], ref.segments[1:], str(ref))
        if ref.root == "item":
            assert index is not None, "item reference outside an each unit"
            item = self._aligned_collection(each_ref)[index]
            return _navigate(item, ref.segments, str(ref))
        if ref.root == "index":
            return index
        if ref.root == "models":
            alias = self.workflow.models[ref.segments[0]]
            return _navigate(alias.model_dump(mode="json"), ref.segments[1:], str(ref))
        if ref.root == "steps":
            return self._resolve_step_ref(ref, index=index)
        raise ResolutionError(f"unsupported reference root {ref.root!r} ({ref})")

    def _aligned_collection(self, each_ref: str | None) -> list[Any]:
        assert each_ref is not None, "item/index reference outside an each unit"
        collection = self.resolve(each_ref, index=None, each_ref=None)
        if not isinstance(collection, list):
            raise ResolutionError(f"`each` target {each_ref!r} did not resolve to a list")
        return collection

    def _resolve_step_ref(self, ref: Ref, *, index: int | None) -> Any:
        step_name, rest = ref.segments[0], ref.segments[1:]
        state = self.steps.get(step_name)
        if state is None:
            raise ResolutionError(f"reference to step {step_name!r} before it ran ({ref})")
        if not state.each:
            key = unit_key(step_name, None)
            if key in state.failed or key in state.skipped:
                raise UpstreamFailure(key)
            return _navigate(state.projections[key], rest, str(ref))
        scalar_key = unit_key(step_name, None)
        if scalar_key in state.failed or scalar_key in state.skipped:
            raise UpstreamFailure(scalar_key)
        if index is not None:
            # Aligned access from inside an each unit: same index, by position.
            key = unit_key(step_name, index)
            if key in state.failed or key in state.skipped:
                raise UpstreamFailure(key)
            if key not in state.projections:
                raise ResolutionError(f"no record for {key} ({ref})")
            return _navigate(state.projections[key], rest, str(ref))
        # Whole-collection access from a scalar step: aligned list, None where
        # the item failed or was skipped (downstream code sees the gap explicitly).
        items: list[Any] = []
        for i in range(state.item_count or 0):
            key = unit_key(step_name, i)
            if key in state.projections:
                items.append(_navigate(state.projections[key], rest, str(ref), none_ok=True))
            else:
                items.append(None)
        return items

    def unit_input_hash(
        self,
        step_name: str,
        resolved_inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> str:
        return stable_hash(
            {
                "workflow_hash": self.workflow_hash,
                "step": step_name,
                "inputs": resolved_inputs,
                "config": config,
            }
        )


def _navigate(value: Any, segments: tuple[str, ...], ref: str, *, none_ok: bool = False) -> Any:
    for segment in segments:
        if value is None and none_ok:
            return None
        if isinstance(value, dict):
            if segment not in value:
                raise ResolutionError(f"{ref}: {segment!r} not present")
            value = value[segment]
        elif isinstance(value, list):
            try:
                value = value[int(segment)]
            except (ValueError, IndexError) as error:
                raise ResolutionError(f"{ref}: bad list index {segment!r}") from error
        else:
            raise ResolutionError(f"{ref}: cannot navigate into {type(value).__name__}")
    return value
