# Sprint 03 Reproducibility Notes

Date: 2026-06-14

## Context

Sprint 03 introduced matrix execution, run comparison, and reproducible run
archives. The current GradeBot T2 and DEMA matrix harnesses are strong enough to
validate Pipyer mechanics: matrix expansion, cell-local results, compare
artifacts, raw event-log retention, resume behavior, and archive organization.

They are not yet a fully hermetic experiment system. Provider-backed model
behavior can drift unless the workflow pins model ids and records enough model,
prompt, schema, runtime, and input provenance to explain a result later.

## Model Id Policy

Eval workflows should prefer provider model ids that are documented as fixed
snapshots. Avoid `latest`, `preview`, and convenience aliases for durable
comparison evidence.

Anthropic's current model docs use two relevant patterns:

- Dated ids such as `claude-sonnet-4-5-20250929` are pinned snapshots.
- Anthropic 4.6+ canonical ids such as `claude-sonnet-4-6` are documented as
  snapshot ids even though they do not carry an eight-digit date.

OpenAI's current docs show a mixed pattern. Some ids are dated snapshots, while
dateless ids such as `gpt-4o-mini` are not proven pinned by the docs we checked.
For durable evidence, treat those as weaker unless OpenAI documents a fixed
snapshot guarantee for the specific id.

Open and local models reduce provider-backend drift, but they introduce their
own requirements: record artifact digest, runtime/version, quantization,
sampler/decoding parameters, hardware or serving stack where material, and the
prompt/schema versions used.

## DEMA Matrix

The DEMA matrix remains a bridge harness. Pipyer calls the locked `dema-llm`
CLI, and DEMA performs the provider calls. This validates Pipyer against an
existing DEMA experiment surface, but the long-term target is a Pipyer-native
workflow where DEMA supplies domain functions and Pipyer owns provider calls,
usage, cost, retry, failure semantics, and comparison records.

Current DEMA reproducibility strengths:

- Pipyer archives its own git head, status, diff, workflow snapshot, `uv.lock`,
  commands, transcript, raw run directory, and event log.
- The harness locks DEMA to a specific commit and requires a clean DEMA
  worktree unless `ALLOW_DEMA_DRIFT=1` is set.
- Archives copy DEMA `router.yaml`, `pyproject.toml`, `uv.lock`, and input CSVs.
- DEMA logs include route, observed model name, decoding parameters, prompt and
  payload hashes, router hash, schema version, latency, and errors.

Sprint 03 follow-up implemented in the DEMA archive writer:

- `manifest.json.model_provenance.routes`: route, provider, requested model id,
  effective route parameters, and a best-effort pinning assessment.
- `manifest.json.model_provenance.cells`: per-cell adjudication status and
  observed log summaries, including model names, model versions when reported,
  fingerprints when reported, prompt/payload hash counts and digests, schema
  versions, router hashes, decoding parameters, and error counts.
- `manifest.json.source_file_digests`: hashes of the staged workflow, wrapper
  script, Pipyer lockfile, DEMA router, DEMA lockfile, and DEMA input data.

Remaining DEMA limitations:

- Provider backend state is not frozen.
- DEMA currently reports `model_version` as `null` for the observed calls.
- Prompt and payload hash summaries prove the rendered requests changed or
  stayed stable, but the manifest intentionally avoids embedding all prompts.
- OpenAI route reproducibility remains weaker unless its model id is replaced by
  a documented fixed snapshot or recorded as an explicit limitation.

## GradeBot T2 Future Work

The GradeBot T2 matrix currently has good workflow and repo provenance. It
archives the staged workflow, prompt file, scripts, Pipyer git state, `uv.lock`,
raw run directory, event log, commands, transcript, and matrix model strings.
Pipyer `llm` step results record provider, requested model id, token counts,
cost estimate, cost table version, and input hashes.

Changes to improve future GradeBot runs:

- Add manifest-level prompt, schema, workflow, script, and lockfile digests.
- Summarize resource digests that already contribute to `input_hash`, so users
  can inspect them without replaying every step record.
- Record provider-resolved model version or system fingerprint when the provider
  exposes one.
- Add a workflow or run-script check that rejects `latest`, `preview`, and
  non-pinned model ids for eval evidence unless explicitly allowed.
- Add a PII-safe corpus manifest for external corpus inputs: file list, sizes,
  mtimes where useful, and hashes where policy allows.
- Capture decoding parameters explicitly in the archive manifest, even when the
  component relies on provider defaults.
- For open/local models, record model artifact digest, runtime/serving version,
  quantization, sampler settings, and hardware/runtime notes.

## Practical Standard

For Sprint 03 acceptance, a run can be considered valid if it verifies Pipyer's
matrix, checkpoint, comparison, and archive behavior. For long-term benchmark
evidence, the archive should also demonstrate pinned model identity, explicit
prompt/schema/resource digests, input-data provenance, runtime provenance, and
known limits.

## References

- Anthropic model IDs and versioning:
  <https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions>
- Anthropic model deprecations:
  <https://platform.claude.com/docs/en/about-claude/model-deprecations>
- OpenAI models:
  <https://developers.openai.com/api/docs/models>
- OpenAI deprecations:
  <https://developers.openai.com/api/docs/deprecations>
