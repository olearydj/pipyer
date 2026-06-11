# PydanticAI Capability Spike

Entry gate for implementation (SPEC sections 4 and 12; backlog feature 001a). This is a technical spike producing evidence for an architectural choice, not product code.

## Purpose

Determine whether Pipyer should be:

1. a standalone runner using PydanticAI internally for LLM steps (current hypothesis),
2. a thin pipeline-player layer around PydanticAI's own execution primitives,
3. a conventions/templates package for PydanticAI,
4. or unnecessary because PydanticAI already covers the desired workflow semantics.

Current hypothesis, to confirm, modify, or reject:

> Pipyer uses PydanticAI for structured LLM calls and possibly eval internals, while owning the workflow artifact, `each`, matrix expansion, `StepResult`, JSONL records, resume, and CLI UX.

## Context That Narrows the Spike

PydanticAI is already proven for raw and structured calls across providers in two production-adjacent codebases by the same author (DEMA-LLM adjudicators: OpenAI, Anthropic, Google, Ollama, deterministic stub; twc-bridge extraction: Ollama, MLX/OpenAI-compatible, OpenAI, Anthropic). Do not re-prove those. The open questions are below.

## Spike 1: LLM Component Fit (Narrowed)

- Usage metadata: can token counts and cost inputs be captured reliably into a `StepResult` shape, per call, including on validation-retry paths?
- Retry accounting: are internal validation retries bounded, countable, and visible? Confirm they cannot silently multiply with runner-level retries.
- Error shapes: what does the exception/result look like after retry exhaustion, transport failure, and rate limiting? Map each to the SPEC error taxonomy.
- Interface choice: `Agent`, `direct`, or other - which fits a component that must stay workflow-configured (model alias resolved from workflow data, not code)?

Output: short report with code snippets, observed result objects, and a recommendation.

## Spike 2: GradeBot Skeleton (Boundary Test)

Minimal scenario: 3 fake submissions; one shell command simulating test execution; one structured LLM feedback call per submission; JSONL records per item; one forced item failure; one resume after simulated interruption.

Questions: does PydanticAI help with batch orchestration beyond the LLM call, or is it simpler for Pipyer to own `each`, `StepResult`, and JSONL directly? What is the cleanest boundary?

Output: minimal runnable prototype plus a boundary recommendation.

## Spike 3: Pydantic Evals Review

Minimal scenario: 2 cases, 2 prompts, 2 model aliases, structured response, judge step, usage collection.

Questions: does Pydantic Evals provide first-class matrix semantics? Can Pipyer wrap it while preserving JSONL run records, or is native matrix execution simpler? Does promptfoo fit this slice better as an external adapter?

Output: mapping of the model-eval workflow to Pydantic Evals concepts and a recommendation: native, integrate, or defer.

## Spike 4: Graph and Durable Execution Review

Model a fixed two-step workflow as a PydanticAI graph; inspect state representation; check whether node outputs map cleanly to `StepResult` and whether durable execution supports deterministic item-level resume.

Questions: useful internal engine, or heavier than owning execution directly? Would graphs compromise the workflows-are-data surface?

Output: recommendation - use, ignore for v1, or revisit later.

## Decision Criteria

- Standalone runner: PydanticAI excellent for calls but unhelpful for batch/matrix/run-record semantics; owning JSONL and resume is simpler.
- Thin layer: PydanticAI naturally represents workflow execution; durable execution maps to resume; Evals maps to model-eval.
- Conventions only: PydanticAI already provides a good declarative artifact and CLI story.
- Abandon: another tool runs the proof workflows with equivalent evidence and less conceptual overhead.
