"""Shared spike helpers. Disposable evidence code, not product (plan.md; R10).

Includes the vendored household secrets resolver (R14): provider chain
auto/1password/env, `op read` with availability check, returning
(secret, provider_name) so provenance is reportable without logging the secret.
Product adoption happens in Feature 002 as src/pipyer/secrets.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ---------------------------------------------------------------- secrets (R14)

_secret_cache: dict[str, tuple[str, str]] = {}


class SecretResolutionError(RuntimeError):
    """Raised when no provider in the chain could supply the secret; names what was tried."""


def resolve_secret(key: str, provider: str | None = None) -> tuple[str, str]:
    """Resolve a secret by key, returning (secret, provider_name).

    Chain per R14: PIPYER_SECRET_PROVIDER (default 'auto') selects
    '1password' (op read of PIPYER_<KEY>_OP_REFERENCE), 'env' (conventional
    env var), or 'auto' (1password then env).
    """
    if key in _secret_cache:
        return _secret_cache[key]
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
            _secret_cache[key] = got
            return got
    raise SecretResolutionError(f"could not resolve {key}; tried: {'; '.join(attempts)}")


# ------------------------------------------------------------------- providers


def hosted_model_name() -> tuple[str, str] | None:
    """Return (model_name, secret_provider) for the hosted leg, or None if unavailable."""
    try:
        secret, via = resolve_secret("ANTHROPIC_API_KEY")
    except SecretResolutionError:
        return None
    os.environ.setdefault("ANTHROPIC_API_KEY", secret)
    return os.environ.get("PIPYER_SPIKE_HOSTED_MODEL", "anthropic:claude-haiku-4-5"), via


def ollama_base_url() -> str:
    return os.environ.get("PIPYER_SPIKE_OLLAMA_URL", "http://localhost:11434")


def ollama_available_model() -> str | None:
    """Return the first locally available Ollama model tag, or None."""
    override = os.environ.get("PIPYER_SPIKE_OLLAMA_MODEL")
    try:
        with urllib.request.urlopen(f"{ollama_base_url()}/api/tags", timeout=2) as resp:
            tags = json.load(resp)
    except Exception:
        return None
    names = [m["name"] for m in tags.get("models", [])]
    if override:
        return override if override in names else override  # trust the override
    return names[0] if names else None


def make_ollama_model(tag: str):
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.ollama import OllamaProvider

    return OpenAIChatModel(tag, provider=OllamaProvider(base_url=f"{ollama_base_url()}/v1"))


def make_stub_model(custom_output_args: dict | None = None):
    from pydantic_ai.models.test import TestModel

    return TestModel(custom_output_args=custom_output_args)


# ------------------------------------------------------------------- evidence


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_run_id(prefix: str) -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{prefix}"


def input_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def make_step_result(
    *,
    run_id: str,
    step: str,
    component: str,
    status: str,
    output: Any = None,
    error: dict | None = None,
    usage: dict | None = None,
    item_index: int | None = None,
    started_at: str,
    duration_ms: int,
    inputs: Any = None,
) -> dict:
    """A StepResult-shaped dict per data-model.md (evidence of mappability, not the schema)."""
    return {
        "schema_version": "1",
        "run_id": run_id,
        "step": step,
        "component": component,
        "status": status,
        "attempt": 1,
        "output": output,
        "error": error,
        "started_at": started_at,
        "finished_at": now_iso(),
        "duration_ms": duration_ms,
        "usage": usage,
        "matrix": None,
        "item_index": item_index,
        "entity_id": None,
        "input_refs": {},
        "input_hash": input_hash(inputs),
        "component_version": "spike",
    }


def usage_to_cost_fields(model_name: str, usage: Any, counts_source: str) -> dict:
    """Map a pydantic_ai RunUsage onto the FR-015 cost-field shape."""
    return {
        "provider": model_name.split(":", 1)[0] if ":" in model_name else "stub",
        "model": model_name,
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "estimated_cost": None,  # no price tables in pydantic-ai RunUsage; see report
        "cost_table_version": None,
        "counts_source": counts_source,
        "validation_attempts": getattr(usage, "requests", 1),
        "raw_requests": getattr(usage, "requests", None),
        "details": getattr(usage, "details", None) or None,
    }


def write_evidence(name: str, payload: Any) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    with path.open("a" if name.endswith(".jsonl") else "w", encoding="utf-8") as fh:
        if name.endswith(".jsonl"):
            fh.write(json.dumps(payload, default=str) + "\n")
        else:
            json.dump(payload, fh, indent=2, default=str)
            fh.write("\n")
    return path


def timed() -> tuple[str, float]:
    return now_iso(), time.monotonic()


def ms_since(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
