# Quickstart: Validating Feature 001

Runnable scenarios proving the feature's exit criteria. Contracts:
[workflow-schema](contracts/workflow-schema.md), [run-record-schema](contracts/run-record-schema.md),
[validate-cli](contracts/validate-cli.md). Entities: [data-model.md](data-model.md).

## Prerequisites

- Python 3.12+ and `uv` (everything runs through `uv`; never `pip`)
- For the spike's live scenarios only: a hosted-provider API key in the environment
  (e.g. `ANTHROPIC_API_KEY`) and a local Ollama with a small model pulled
- No other services; everything is local files

## Setup

```bash
uv sync                  # product deps: pydantic, pyyaml (+ dev: pytest)
uv sync --group spike    # adds pydantic-ai for spike scenarios only
```

## Scenario 1: Conformance suite passes (SC-002)

```bash
uv run pytest tests/conformance -q
```

Expected: all schema-level tests pass; execution-behavior fixtures report as
xfail/skip with reason "Feature 002 runner" - present and counted, not silently absent.
Includes the import-boundary test: the contract modules (`schema/`, `records/`,
`canonical.py`, `validation.py`) import no substrate (R10) - a permanent guard that
Feature 002 keeps intact.

## Scenario 2: GradeBot fixture validates, both surfaces, identical bytes (SC-003)

```bash
uv run pipyer validate tests/fixtures/gradebot/workflow.yaml
# → exit 0, prints workflow name, schema version, and hash

uv run pytest tests/conformance/test_canonical.py -q
# → asserts: YAML surface and construct.py produce byte-identical canonical JSON
#   and the same SHA-256 workflow hash; fixture contains zero forbidden constructs
```

## Scenario 3: Invalid workflows fail legibly (SC-004)

```bash
uv run pipyer validate tests/fixtures/invalid/dangling_ref.yaml; echo "exit=$?"
```

Expected: exit 1; error output names the exact location
(`steps[1].inputs.test_output: reference to unknown step ...`). Repeat with `--json` and
confirm machine-readable errors with `loc` and `code` fields. Every file in
`tests/fixtures/invalid/` is also exercised by the suite in Scenario 1.

## Scenario 4: Spike evidence (SC-001, SC-007)

```bash
uv run --group spike python spike/01_usage_capture.py     # hosted + local + stub
uv run --group spike python spike/02_retry_accounting.py  # bounded, counted, non-multiplying
uv run --group spike python spike/03_error_shapes.py      # exhaustion/transport/rate-limit → taxonomy
uv run --group spike python spike/04_gradebot_skeleton.py --interrupt-after 1
uv run --group spike python spike/04_gradebot_skeleton.py --resume
```

Expected for the skeleton pair: first invocation processes item 0 then stops; the resume
completes items 1-2 (including the forced failure as a failure-status record) and recomputes
zero completed items; per-item JSONL evidence exists for all three items. Spikes 05/06 (evals,
graph) run the same way and feed the report.

Report: `specs/001-pydanticai-spike-contracts/spike-report.md` answers all four areas, cites
the exact substrate version probed, and states one of the four boundary outcomes (SC-001).

## Scenario 5: Open decisions closed (SC-005)

```bash
grep -c '^## R' specs/001-pydanticai-spike-contracts/research.md   # → 14
```

R1-R6 record the six SPEC section 12 resolutions with rationale; none says "open". R10-R11
record the import-boundary scope and the `python`-component decision (ADR-002 knock-on
superseded), R12 settles the empty-collection rule (empty matrix dimension rejected at
dry-run; empty `each` recorded at runtime), R13-R14 record the toolchain (typer, ruff, ty,
uv_build) and the household 1Password secrets pattern, and the static-argv watch item is on
file for the census.

## Scenario 6: Falsification census recorded (SC-008)

The feature exit notes (in `spike-report.md` or alongside it) contain the per-step census of
the GradeBot fixture - author's and context-free reviewer's, independently - with zero steps
existing only because the schema forbids expressions, or the ADR-004 escalation instead.
