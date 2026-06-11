"""Secrets resolution: the household 1Password pattern, graduated from the spike (R14).

Provider chain `auto`/`1password`/`env`: 1Password resolves
`PIPYER_<KEY>_OP_REFERENCE` via `op read`; env reads the conventional variable.
Returns `(secret, provider_name)` so provenance is reportable - the provider
name lands in the run record, the value never does. Workflow files and run
records MUST NOT contain credentials (constitution, Operational Constraints).
"""

from __future__ import annotations

import os
import shutil
import subprocess

_cache: dict[str, tuple[str, str]] = {}


class SecretResolutionError(RuntimeError):
    """No provider in the chain could supply the secret; the message names what was tried."""


def resolve_secret(key: str, provider: str | None = None) -> tuple[str, str]:
    """Resolve a secret by key, returning (secret, provider_name).

    `provider` (or PIPYER_SECRET_PROVIDER, default 'auto') selects '1password'
    (`op read` of PIPYER_<KEY>_OP_REFERENCE), 'env' (the conventional env var),
    or 'auto' (1password then env).
    """
    if key in _cache:
        return _cache[key]
    provider = provider or os.environ.get("PIPYER_SECRET_PROVIDER", "auto")
    attempts: list[str] = []

    def from_1password() -> tuple[str, str] | None:
        ref = os.environ.get(f"PIPYER_{key}_OP_REFERENCE")
        if not ref:
            attempts.append(f"1password: PIPYER_{key}_OP_REFERENCE not set")
            return None
        if not shutil.which("op"):
            attempts.append("1password: `op` CLI not on PATH")
            return None
        proc = subprocess.run(["op", "read", ref], capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            attempts.append(f"1password: op read failed ({proc.stderr.strip()[:120]})")
            return None
        return proc.stdout.strip(), "1password"

    def from_env() -> tuple[str, str] | None:
        value = os.environ.get(key)
        if not value:
            attempts.append(f"env: {key} not set")
            return None
        return value, "env"

    legs = {"1password": [from_1password], "env": [from_env], "auto": [from_1password, from_env]}
    if provider not in legs:
        raise SecretResolutionError(f"unknown secret provider {provider!r}")
    for leg in legs[provider]:
        got = leg()
        if got:
            _cache[key] = got
            return got
    raise SecretResolutionError(f"could not resolve {key}; tried: {'; '.join(attempts)}")


def clear_cache() -> None:
    """Drop cached resolutions (test isolation; also lets a long process re-resolve)."""
    _cache.clear()
