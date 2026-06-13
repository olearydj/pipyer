"""llm / llm_judge executor - the ONLY src/ module importing pydantic_ai (R10).

PydanticAI owns model-call mechanics; this module owns the mapping into
Pipyer's records: alias-driven structured-output mode (tool/native/prompted,
never auto-picked for local aliases), bounded output-validation retries counted
into usage.validation_attempts, the FR-010 error-shape taxonomy, call-time
secret resolution (R15), wall-clock timeout_s, and usage→cost capture (FR-006).
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any, cast

from pydantic_ai import Agent, ModelRetry, NativeOutput, PromptedOutput, StructuredDict
from pydantic_ai.exceptions import (
    AgentRunError,
    ContentFilterError,
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models.test import TestModel

from pipyer.prompts import render_prompt
from pipyer.records.step_result import ErrorCategory, UsageCost
from pipyer.runner.components import StepFailure
from pipyer.secrets import SecretResolutionError, resolve_secret

# Provider prefix -> conventional API-key variable (preflight uses the same map).
PROVIDER_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-chat": "OPENAI_API_KEY",
    "openai-responses": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "google-gla": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "CO_API_KEY",
}

# Minimal cost table: USD per million tokens (input, output). Models absent
# here record estimated_cost None with the table version, never a guess.
COST_TABLE_VERSION = "2026-06"
COST_TABLE: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    "claude-sonnet-4-6": (Decimal("3.00"), Decimal("15.00")),
    # T036 acceptance model; verified against genai-prices on 2026-06-11
    "claude-sonnet-4-5-20250929": (Decimal("3.00"), Decimal("15.00")),
}


def secret_key_for(model: str, settings: dict[str, Any]) -> str | None:
    """The env key an alias needs, or None (test models and local endpoints)."""
    if settings.get("base_url"):
        return None
    prefix = (model.split(":", 1)[0] if ":" in model else model).removeprefix("gateway/")
    if prefix == "test" or model == "test":
        return None
    return PROVIDER_KEYS.get(prefix)


def _build_hosted_model(model: str, *, key: str, secret: str):
    """Build a pydantic-ai model with an explicit provider key.

    The key must not be written to `os.environ`: shell/python components scrub
    inherited env too, but model construction should be scoped to this object.
    """
    from pydantic_ai.models import infer_model
    from pydantic_ai.providers import infer_provider, infer_provider_class

    def provider_factory(provider_name: str):
        provider_key = PROVIDER_KEYS.get(provider_name.removeprefix("gateway/"))
        if provider_key == key:
            provider_class = cast(Any, infer_provider_class(provider_name))
            return provider_class(api_key=secret)
        return infer_provider(provider_name)

    return infer_model(model, provider_factory=provider_factory)


def _schema_issues(schema: dict[str, Any], value: Any) -> list[str]:
    """Minimal JSON-schema conformance for structured outputs: required keys,
    top-level property types, numeric bounds. Enough to make validation real."""
    issues: list[str] = []
    if not isinstance(value, dict):
        return [f"output is {type(value).__name__}, expected object"]
    for key in schema.get("required", []):
        if key not in value:
            issues.append(f"missing required property {key!r}")
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, spec in schema.get("properties", {}).items():
        if key not in value or not isinstance(spec, dict):
            continue
        got = value[key]
        expected = spec.get("type")
        if isinstance(expected, str) and expected in type_map:
            if expected == "integer" and isinstance(got, bool):
                issues.append(f"{key!r} is boolean, expected integer")
            elif not isinstance(got, type_map[expected]) and got is not None:
                if not (expected == "number" and isinstance(got, int)):
                    issues.append(f"{key!r} is {type(got).__name__}, expected {expected}")
        if isinstance(got, int | float) and not isinstance(got, bool):
            if "minimum" in spec and got < spec["minimum"]:
                issues.append(f"{key!r} below minimum {spec['minimum']}")
            if "maximum" in spec and got > spec["maximum"]:
                issues.append(f"{key!r} above maximum {spec['maximum']}")
        if "enum" in spec and key in value and got not in spec["enum"]:
            issues.append(f"{key!r} not in enum {spec['enum']}")
    return issues


def _build_model(alias, *, model_overrides: dict[str, Any], alias_name: str, force_invalid: bool):
    if force_invalid:
        return TestModel(custom_output_args={})
    if alias_name in model_overrides:
        return model_overrides[alias_name]
    model = alias.model
    if alias.settings.get("base_url"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        tag = model.split(":", 1)[1] if ":" in model else model
        return OpenAIChatModel(tag, provider=OllamaProvider(base_url=alias.settings["base_url"]))
    key = secret_key_for(model, alias.settings)
    if key is not None:
        try:
            secret, _provider = resolve_secret(key)
        except SecretResolutionError as error:
            # Double-fault: preflight passed, environment changed mid-run (R15).
            raise StepFailure(
                ErrorCategory.PROVIDER_ERROR,
                f"secret resolution failed at call time for {key}",
                detail={"kind": "secret_resolution_failed", "error": str(error)},
            ) from error
        return _build_hosted_model(model, key=key, secret=secret)
    return model  # string form; pydantic_ai infers ("test" -> TestModel)


def _output_type(schema: dict[str, Any], output_mode: str | None, name: str):
    structured = StructuredDict(schema, name=f"{name}_output")
    if output_mode == "native":
        return NativeOutput(structured)
    if output_mode == "prompted":
        return PromptedOutput(structured)
    return structured  # tool mode / provider default


def _model_settings(settings: dict[str, Any]) -> dict[str, Any] | None:
    passthrough = {k: v for k, v in settings.items() if k != "base_url"}
    return passthrough or None


def _usage_cost(alias, usage, *, attempts: int) -> UsageCost:
    model = alias.model
    provider = (
        model.split(":", 1)[0]
        if ":" in model
        else ("local" if alias.settings.get("base_url") else model)
    )
    bare = model.split(":", 1)[1] if ":" in model else model
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    estimated = None
    if bare in COST_TABLE and input_tokens is not None and output_tokens is not None:
        per_in, per_out = COST_TABLE[bare]
        estimated = (per_in * input_tokens + per_out * output_tokens) / Decimal(1_000_000)
    counts_source = (
        "provider_reported"
        if input_tokens is not None or output_tokens is not None
        else "unavailable"
    )
    return UsageCost(
        provider=provider,
        model=bare,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimated,
        cost_table_version=COST_TABLE_VERSION,
        counts_source=counts_source,
        validation_attempts=attempts,
    )


def _load_schema(config, ctx) -> dict[str, Any]:
    # Deep copy: pydantic_ai's StructuredDict mutates the schema it receives
    # (adds "title"), and a mutated workflow config would shift input hashes.
    import copy

    if isinstance(config.output_schema, dict):
        return copy.deepcopy(config.output_schema)
    return json.loads((ctx.workflow_dir / config.output_schema).read_text(encoding="utf-8"))


def execute(step, resolved_inputs: dict[str, Any], ctx, index) -> tuple[dict[str, Any], UsageCost]:
    config = step.config
    alias = ctx.model_alias(config.model)
    schema = _load_schema(config, ctx)
    hooks = getattr(ctx, "test_hooks", {})
    model = _build_model(
        alias,
        model_overrides=hooks.get("model_overrides") or {},
        alias_name=config.model,
        force_invalid=bool(hooks.get("force_invalid_llm_output")),
    )

    prompt_text = (ctx.workflow_dir / config.prompt).read_text(encoding="utf-8")
    rendered = render_prompt(
        prompt_text,
        resolved_inputs,
    )

    agent = Agent(  # ty: ignore[no-matching-overload]
        model,
        output_type=_output_type(schema, alias.output_mode, step.name),
        retries={"output": config.max_validation_retries},
        model_settings=_model_settings(alias.settings),
    )

    @agent.output_validator
    def _validate(output: Any) -> Any:
        issues = _schema_issues(schema, output)
        if issues:
            raise ModelRetry("output failed schema validation: " + "; ".join(issues))
        return output

    max_attempts = config.max_validation_retries + 1

    async def _acall():
        # asyncio.wait_for CANCELS the in-flight call on timeout - the HTTP
        # request is torn down, not abandoned in a thread the executor would
        # then wait on. (Review finding: the previous ThreadPoolExecutor form
        # raised on timeout but blocked at context exit until the hung call
        # returned, so timeout_s was not actually a wall-clock bound.)
        if config.timeout_s is not None:
            return await asyncio.wait_for(agent.run(rendered), timeout=config.timeout_s)
        return await agent.run(rendered)

    try:
        result = asyncio.run(_acall())
    except TimeoutError:
        raise StepFailure(
            ErrorCategory.TIMEOUT,
            f"model call exceeded timeout_s={config.timeout_s} (call cancelled)",
            usage=None,
        ) from None
    except IncompleteToolCall as error:
        raise StepFailure(
            ErrorCategory.OUTPUT_VALIDATION_ERROR,
            "incomplete tool call from model",
            detail=str(error),
            usage=_usage_cost(alias, None, attempts=max_attempts),
        ) from error
    except ContentFilterError as error:
        raise StepFailure(
            ErrorCategory.PROVIDER_ERROR,
            "content filter rejected the request",
            detail={"type": type(error).__name__, "error": str(error)},
        ) from error
    except UnexpectedModelBehavior as error:
        raise StepFailure(
            ErrorCategory.OUTPUT_VALIDATION_ERROR,
            "output validation exhausted bounded retries",
            detail=str(error),
            usage=_usage_cost(alias, None, attempts=max_attempts),
        ) from error
    except ModelHTTPError as error:
        category = (
            ErrorCategory.RATE_LIMITED if error.status_code == 429 else ErrorCategory.PROVIDER_ERROR
        )
        raise StepFailure(
            category, f"provider HTTP {error.status_code}", detail=str(error)
        ) from error
    except ModelAPIError as error:
        raise StepFailure(
            ErrorCategory.TRANSPORT_ERROR, "transport-level model API failure", detail=str(error)
        ) from error
    except AgentRunError as error:
        raise StepFailure(
            ErrorCategory.PROVIDER_ERROR,
            f"agent run failed: {type(error).__name__}",
            detail=str(error),
        ) from error

    usage = result.usage
    attempts = getattr(usage, "requests", 1) or 1
    return {"output": result.output}, _usage_cost(alias, usage, attempts=attempts)
