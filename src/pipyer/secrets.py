"""Secrets resolution: the household 1Password pattern, graduated from the spike (R14).

Provider chain `auto`/`1password`/`env`: 1Password resolves
`PIPYER_<KEY>_OP_REFERENCE` via `op read`; env reads the conventional variable.
Returns `(secret, provider_name)` so provenance is reportable - the provider
name lands in the run record, the value never does. Workflow files and run
records MUST NOT contain credentials (constitution, Operational Constraints).
"""

from __future__ import annotations

import os

from secretpath import SecretPathError
from secretpath import clear_cache as _clear_secretpath_cache
from secretpath import resolve_secret as _resolve_secretpath


class SecretResolutionError(RuntimeError):
    """No provider in the chain could supply the secret; the message names what was tried."""


def resolve_secret(key: str, provider: str | None = None) -> tuple[str, str]:
    """Resolve a secret by key, returning (secret, provider_name).

    `provider` (or PIPYER_SECRET_PROVIDER, default 'auto') selects '1password'
    (`op read` of PIPYER_<KEY>_OP_REFERENCE), 'env' (the conventional env var),
    or 'auto' (1password then env).
    """
    selected_provider = provider or os.environ.get("PIPYER_SECRET_PROVIDER", "auto")
    if selected_provider not in {"auto", "1password", "env"}:
        raise SecretResolutionError(f"unknown secret provider {selected_provider!r}")

    try:
        result = _resolve_secretpath(
            key,
            provider=selected_provider,
            op_reference_env=f"PIPYER_{key}_OP_REFERENCE",
            env_var=key,
        )
    except SecretPathError as error:
        raise SecretResolutionError(str(error)) from error

    return result.value, result.source


def clear_cache() -> None:
    """Drop cached resolutions (test isolation; also lets a long process re-resolve)."""
    _clear_secretpath_cache()
