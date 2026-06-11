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


def main() -> None:
    app()
