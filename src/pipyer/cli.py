"""`pipyer validate` - the authoring loop until the Feature 002 runner (FR-021).

Typer app (R13, annotated-options style). Validates and never executes: exit 0
valid, exit 1 validation errors, exit 2 usage/I/O/YAML errors. `--json` emits
the machine-readable error list for agent authoring loops. Library parity: this
command reports exactly what pipyer.validation reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from pipyer.canonical import workflow_hash
from pipyer.validation import validate_file

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def _root() -> None:
    """Pipyer: deterministic orchestration. Workflows validate before anything runs."""


@app.command()
def validate(
    workflow_file: Annotated[Path, typer.Argument(help="Path to a YAML workflow file")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Machine-readable error output")
    ] = False,
) -> None:
    """Run the full dry-run validation on a workflow file. Executes nothing."""
    try:
        workflow, issues = validate_file(workflow_file)
    except OSError as error:
        typer.echo(f"error: cannot read {workflow_file}: {error}", err=True)
        raise typer.Exit(2) from error
    except yaml.YAMLError as error:
        typer.echo(f"error: not valid YAML (safe_load): {error}", err=True)
        raise typer.Exit(2) from error

    if issues:
        name = workflow.name if workflow is not None else workflow_file.stem
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "valid": False,
                        "workflow": name,
                        "schema_version": workflow.schema_version if workflow else None,
                        "errors": [
                            {"loc": i.loc, "code": i.code, "message": i.message} for i in issues
                        ],
                    },
                    indent=2,
                )
            )
        else:
            plural = "s" if len(issues) != 1 else ""
            typer.echo(f"INVALID {name} ({len(issues)} error{plural})")
            for issue in issues:
                typer.echo(f"  {issue.loc}: {issue.message}")
        raise typer.Exit(1)

    assert workflow is not None
    digest = workflow_hash(workflow)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "valid": True,
                    "workflow": workflow.name,
                    "schema_version": workflow.schema_version,
                    "hash": digest,
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"OK {workflow.name} (schema v{workflow.schema_version}, hash {digest[:19]}…)")


@app.command()
def run(
    workflow_file: Annotated[Path, typer.Argument(help="Path to a YAML workflow file")],
    input_: Annotated[
        list[str] | None,
        typer.Option(
            "--input", help="Workflow input as k=v (v parses as a YAML scalar); repeatable"
        ),
    ] = None,
    resume: Annotated[
        str | None, typer.Option("--resume", help="Resume a prior run: a run id, or 'last'")
    ] = None,
    retry_failed: Annotated[
        bool,
        typer.Option("--retry-failed", help="Re-execute prior failed items (requires --resume)"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Exactly `pipyer validate`: check, execute nothing")
    ] = False,
    results_dir: Annotated[
        Path | None, typer.Option("--results-dir", help="Override settings.results_dir")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit the RunRecord as JSON")] = False,
) -> None:
    """Execute a workflow (contracts/run-cli.md). Validates first; nothing runs unvalidated."""
    if dry_run:
        validate(workflow_file, json_output)  # one implementation (FR-011)
        return
    if retry_failed and resume is None:
        typer.echo("error: --retry-failed requires --resume", err=True)
        raise typer.Exit(2)

    inputs: dict[str, object] = {}
    for pair in input_ or []:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            typer.echo(f"error: --input expects k=v, got {pair!r}", err=True)
            raise typer.Exit(2)
        inputs[key] = yaml.safe_load(raw) if raw != "" else ""

    from pipyer.runner import (
        NoPriorRunError,
        RunLockedError,
        SecretResolutionError,
        ValidationFailure,
        run_workflow,
    )

    try:
        workflow, issues = validate_file(workflow_file)
    except OSError as error:
        typer.echo(f"error: cannot read {workflow_file}: {error}", err=True)
        raise typer.Exit(2) from error
    except yaml.YAMLError as error:
        typer.echo(f"error: not valid YAML (safe_load): {error}", err=True)
        raise typer.Exit(2) from error
    if issues or workflow is None:
        for issue in issues:
            typer.echo(f"error: {issue.loc}: {issue.message}", err=True)
        raise typer.Exit(2)

    effective_results_dir = results_dir or Path(workflow.settings.results_dir)
    try:
        result = run_workflow(
            workflow_file,
            results_dir=effective_results_dir,
            inputs=inputs,
            resume=(resume or False) if resume != "last" else True,
            retry_failed=retry_failed,
        )
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    except (ValidationFailure, SecretResolutionError, RunLockedError, NoPriorRunError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(2) from error

    if json_output:
        typer.echo(result.record.model_dump_json(indent=2))
    else:
        totals = result.record.totals
        typer.echo(f"run {result.run_id}: {result.status}")
        typer.echo(f"  directory: {result.run_dir}")
        typer.echo(
            f"  units: {totals.get('succeeded', 0)} succeeded, {totals.get('failed', 0)} failed, "
            f"{totals.get('skipped', 0)} skipped, {totals.get('not_attempted', 0)} not attempted"
        )
        if result.record.halt_reason:
            typer.echo(f"  halt: {result.record.halt_reason}")
        typer.echo(f"  summary: {result.run_dir / 'summary.md'}")

    if result.status == "interrupted":
        raise typer.Exit(130)
    failed = int(result.record.totals.get("failed", 0))
    if result.status == "halted" or failed > 0:
        raise typer.Exit(1)


def main() -> None:
    app()
