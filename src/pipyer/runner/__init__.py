"""pipyer.runner - the execution engine (Feature 002).

Public surface (contracts/runner-api.md, pinned by the 8 execution fixtures):
`run_workflow`, `reconstruct_checkpoint`, `derive_summary`, plus the pre-run
exception types. Everything else is internal.
"""

from pipyer.runner.checkpoint import reconstruct_checkpoint
from pipyer.runner.engine import Run, ValidationFailure, run_workflow
from pipyer.runner.events import RunLockedError
from pipyer.runner.resume import NoPriorRunError
from pipyer.runner.summary import derive_summary
from pipyer.secrets import SecretResolutionError

__all__ = [
    "NoPriorRunError",
    "Run",
    "RunLockedError",
    "SecretResolutionError",
    "ValidationFailure",
    "derive_summary",
    "reconstruct_checkpoint",
    "run_workflow",
]
