"""Dry-run validation: structural pass plus cross-checks 1-10 (data-model.md).

Validation IS the dry-run (FR-010): a workflow that passes is executable in
principle; one that fails is rejected before anything runs, every issue naming
the offending element by location path, in document order, deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from pipyer.prompts import extract_placeholders
from pipyer.schema.components import AssertionsConfig, LlmConfig, LlmJudgeConfig, PythonConfig
from pipyer.schema.refs import ESCAPE_HATCH, Kind, Ref, classify
from pipyer.schema.workflow import SUPPORTED_SCHEMA_VERSIONS, Workflow


@dataclass(frozen=True)
class Issue:
    loc: str
    code: str
    message: str


def _loc_str(loc: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for piece in loc:
        if isinstance(piece, int):
            parts.append(f"[{piece}]")
        elif parts:
            parts.append(f".{piece}")
        else:
            parts.append(str(piece))
    return "".join(parts)


def _structural_issues(error: ValidationError) -> list[Issue]:
    issues = []
    for err in error.errors():
        # Discriminated-union loc pieces name the matched tag (e.g. 'python');
        # drop them so locations read steps[0].config.script, not
        # steps[0].python.config.script.
        loc = tuple(
            piece for piece in err["loc"] if not (isinstance(piece, str) and piece in _UNION_TAGS)
        )
        issues.append(Issue(loc=_loc_str(loc), code=err["type"], message=err["msg"]))
    return issues


_UNION_TAGS = {
    "file_read",
    "file_write",
    "shell",
    "python",
    "llm",
    "llm_judge",
    "assertions",
}


def validate_workflow(workflow: Workflow, base_dir: Path | None = None) -> list[Issue]:
    """Cross-checks over a structurally valid workflow, in document order."""
    issues: list[Issue] = []
    add = issues.append

    # Rule 9: supported schema version.
    if workflow.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        add(
            Issue(
                loc="schema_version",
                code="unsupported_schema_version",
                message=(
                    f"schema version {workflow.schema_version!r} is not supported; "
                    f"supported: {', '.join(SUPPORTED_SCHEMA_VERSIONS)}"
                ),
            )
        )

    # Rule 1: unique step names (the identifier pattern itself is structural).
    seen: dict[str, int] = {}
    for i, step in enumerate(workflow.steps):
        if step.name in seen:
            add(
                Issue(
                    loc=f"steps[{i}].name",
                    code="duplicate_step_name",
                    message=f"step name {step.name!r} already used by steps[{seen[step.name]}]",
                )
            )
        else:
            seen[step.name] = i

    def resolve(value: object, loc: str, *, step_index: int | None, in_each: bool) -> None:
        """Rules 2-5: classify a mapping-position value; resolve it if a Ref."""
        kind, ref = classify(value)
        if kind is Kind.LITERAL:
            return
        if kind is Kind.ERROR:
            add(Issue(loc=loc, code="malformed_ref", message=f"{value!r} {ESCAPE_HATCH}"))
            return
        assert isinstance(ref, Ref)
        if ref.root in ("item", "index"):
            if not in_each:
                add(
                    Issue(
                        loc=loc,
                        code="item_outside_each",
                        message=f"{ref} is only available inside a step with `each`",
                    )
                )
        elif ref.root == "inputs":
            if ref.segments[0] not in workflow.inputs:
                add(
                    Issue(
                        loc=loc,
                        code="unknown_input_ref",
                        message=f"reference to undeclared workflow input {ref.segments[0]!r}",
                    )
                )
        elif ref.root == "matrix":
            if ref.segments[0] not in workflow.matrix:
                add(
                    Issue(
                        loc=loc,
                        code="unknown_matrix_ref",
                        message=f"reference to unknown matrix dimension {ref.segments[0]!r}",
                    )
                )
        elif ref.root == "models":
            if ref.segments[0] not in workflow.models:
                add(
                    Issue(
                        loc=loc,
                        code="unknown_model_ref",
                        message=f"reference to unknown model alias {ref.segments[0]!r}",
                    )
                )
        elif ref.root == "steps":
            target = ref.segments[0]
            if target not in seen:
                add(
                    Issue(
                        loc=loc,
                        code="unknown_step_ref",
                        message=f"reference to unknown step {target!r}",
                    )
                )
            elif step_index is None:
                pass  # outputs section: every step is in scope
            elif seen[target] == step_index:
                add(
                    Issue(
                        loc=loc,
                        code="self_step_ref",
                        message=f"step {workflow.steps[step_index].name!r} references itself",
                    )
                )
            elif seen[target] > step_index:
                add(
                    Issue(
                        loc=loc,
                        code="forward_step_ref",
                        message=(
                            f"reference to later step {target!r}; references must point to "
                            "earlier steps only (sequential order)"
                        ),
                    )
                )

    # R1: alias targets may be Refs to inputs/matrix only.
    for alias_name, alias in workflow.models.items():
        kind, ref = classify(alias.model)
        if kind is Kind.ERROR:
            add(
                Issue(
                    loc=f"models.{alias_name}.model",
                    code="malformed_ref",
                    message=f"{alias.model!r} {ESCAPE_HATCH}",
                )
            )
        elif kind is Kind.REF and ref is not None:
            if ref.root not in ("inputs", "matrix"):
                add(
                    Issue(
                        loc=f"models.{alias_name}.model",
                        code="invalid_alias_target",
                        message="alias targets may reference workflow inputs or matrix "
                        "dimensions only (R1)",
                    )
                )
            else:
                resolve(
                    alias.model,
                    f"models.{alias_name}.model",
                    step_index=None,
                    in_each=False,
                )

    # Rule 11 (R16): local aliases never auto-pick a structured-output mode. An
    # alias is local when its settings carry a base_url (the Ollama pattern);
    # such aliases must declare output_mode explicitly.
    for alias_name, alias in workflow.models.items():
        if alias.settings.get("base_url") and alias.output_mode is None:
            add(
                Issue(
                    loc=f"models.{alias_name}.output_mode",
                    code="local_alias_output_mode_required",
                    message=(
                        f"alias {alias_name!r} targets a local endpoint (settings.base_url); "
                        "structured-output mode must be set explicitly "
                        "(tool / native / prompted) - local aliases are never auto-picked"
                    ),
                )
            )

    # Per-step checks, document order.
    for i, step in enumerate(workflow.steps):
        in_each = step.each is not None
        loc_base = f"steps[{i}]"

        # Rule 4: `each` must be a Ref to a collection.
        if step.each is not None:
            kind, _ = classify(step.each)
            if kind is not Kind.REF:
                add(
                    Issue(
                        loc=f"{loc_base}.each",
                        code="each_not_ref",
                        message="`each` must be a reference to a collection "
                        "(e.g. steps.collect.items)",
                    )
                )
            else:
                resolve(step.each, f"{loc_base}.each", step_index=i, in_each=False)

        # Rules 2-3: input map values.
        for key, value in step.inputs.items():
            resolve(value, f"{loc_base}.inputs.{key}", step_index=i, in_each=in_each)

        # Path-typed config fields are mapping positions too.
        config = step.config
        if hasattr(config, "path"):
            resolve(config.path, f"{loc_base}.config.path", step_index=i, in_each=in_each)

        # Rule 6a (review finding): python script files are checkable at
        # dry-run exactly like prompt files - a missing script must fail up
        # front, not at runtime as `unclassified`.
        if isinstance(config, PythonConfig):
            script_loc = f"{loc_base}.config.script"
            if base_dir is None:
                add(
                    Issue(
                        loc=script_loc,
                        code="script_base_dir_missing",
                        message="script files cannot be checked without a base directory; "
                        "pass base_dir (the workflow file's directory; explicit for "
                        "direct construction)",
                    )
                )
            elif not (Path(base_dir) / config.script).is_file():
                add(
                    Issue(
                        loc=script_loc,
                        code="script_file_missing",
                        message=f"script file not found: {config.script}",
                    )
                )

        # Rules 5-6: llm/llm_judge alias existence and prompt coverage.
        if isinstance(config, LlmConfig | LlmJudgeConfig):
            if config.model not in workflow.models:
                add(
                    Issue(
                        loc=f"{loc_base}.config.model",
                        code="unknown_model_alias",
                        message=f"model alias {config.model!r} is not declared in `models`",
                    )
                )
            prompt_loc = f"{loc_base}.config.prompt"
            if base_dir is None:
                add(
                    Issue(
                        loc=prompt_loc,
                        code="prompt_base_dir_missing",
                        message="prompt files cannot be checked without a base directory; "
                        "pass base_dir (the workflow file's directory; explicit for "
                        "direct construction)",
                    )
                )
            else:
                prompt_path = Path(base_dir) / config.prompt
                if not prompt_path.is_file():
                    add(
                        Issue(
                            loc=prompt_loc,
                            code="prompt_file_missing",
                            message=f"prompt file not found: {config.prompt}",
                        )
                    )
                else:
                    placeholders = extract_placeholders(prompt_path.read_text(encoding="utf-8"))
                    bound = set(step.inputs)
                    for missing in sorted(placeholders - bound):
                        add(
                            Issue(
                                loc=prompt_loc,
                                code="unbound_placeholder",
                                message=f"placeholder {missing!r} is not bound by inputs",
                            )
                        )
                    for stray in sorted(bound - placeholders):
                        add(
                            Issue(
                                loc=f"{loc_base}.inputs.{stray}",
                                code="unused_prompt_binding",
                                message=f"input {stray!r} does not correspond to any prompt "
                                "placeholder",
                            )
                        )

        # Check inputs must be bound in the step's input map.
        if isinstance(config, AssertionsConfig):
            for j, check in enumerate(config.checks):
                if check.input not in step.inputs:
                    add(
                        Issue(
                            loc=f"{loc_base}.config.checks[{j}].input",
                            code="unknown_check_input",
                            message=f"check input {check.input!r} is not bound in the "
                            "step's input map",
                        )
                    )

    # Rule 8: outputs resolve, with every step in scope.
    for name, value in workflow.outputs.items():
        kind, _ = classify(value)
        if kind is not Kind.REF:
            add(
                Issue(
                    loc=f"outputs.{name}",
                    code="output_not_ref",
                    message="outputs must be references",
                )
            )
        else:
            resolve(value, f"outputs.{name}", step_index=None, in_each=False)

    return issues


def validate_data(data: Any, base_dir: Path | None = None) -> tuple[Workflow | None, list[Issue]]:
    """Structural validation + cross-checks. Returns (workflow|None, issues)."""
    try:
        workflow = Workflow.model_validate(data)
    except ValidationError as error:
        return None, _structural_issues(error)
    issues = validate_workflow(workflow, base_dir=base_dir)
    return workflow, issues


def validate_file(path: Path) -> tuple[Workflow | None, list[Issue]]:
    """Load a YAML workflow (`safe_load`, nothing more) and run the dry-run.

    Raises OSError / yaml.YAMLError for I/O and parse failures - usage errors,
    not validation results (the CLI maps them to exit 2).
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return validate_data(data, base_dir=path.parent)
