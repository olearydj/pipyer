# Data Model: PydanticAI Spike and Contracts

Two contract families: the workflow schema (authoring side) and the run-record schema (evidence side). Both carry explicit schema-version fields (clarification 2026-06-10). All models are Pydantic v2 with `extra="forbid"` - unknown fields are validation errors, never silently ignored (a stale workflow must fail loudly).

## Workflow schema entities

### Workflow

| Field | Type | Rules |
|-------|------|-------|
| `schema_version` | str | Required. Workflow-schema version this file conforms to (`"1"` for this feature). Unsupported version → validation error. |
| `name` | str | Required. Identifier pattern `[a-z][a-z0-9_]*`. |
| `description` | str \| None | Optional. |
| `inputs` | dict[str, InputDecl] | Declared workflow inputs. Keys follow identifier pattern. |
| `models` | dict[str, ModelAlias] | Model alias table (R1). May be empty when no LLM steps exist. |
| `matrix` | dict[str, list[JSON]] | Matrix dimensions: name → list of parameter values. Expansion over parameters only, never topology. |
| `steps` | list[Step] | Required, ordered, non-empty. Step names unique. |
| `settings` | Settings | Defaults apply when omitted (and are materialized in canonical form, R7). |
| `outputs` | dict[str, Ref] | Declared run outputs: name → dotted-path reference. |

### InputDecl

| Field | Type | Rules |
|-------|------|-------|
| `type` | enum: `string`, `number`, `boolean`, `path`, `json` | Required. |
| `required` | bool = true | |
| `default` | JSON \| None | Only when not required. |
| `description` | str \| None | |

### ModelAlias (R1)

| Field | Type | Rules |
|-------|------|-------|
| `model` | str \| Ref | Model identifier (e.g. `provider:model-name`) or a dotted-path reference to a workflow input or matrix dimension - the DEMA pattern for varying models per cell. |
| `settings` | dict[str, JSON] | Optional model settings (temperature, max tokens). No credential fields exist; secrets are environment-only. |

### Step

| Field | Type | Rules |
|-------|------|-------|
| `name` | str | Required, unique within workflow, identifier pattern. |
| `component` | enum: `file_read`, `file_write`, `shell`, `python`, `llm`, `llm_judge`, `assertions` | Discriminator for `config`. `python` is a distinct component so transformation steps are visible and countable in the artifact itself: the falsification census classifies code steps by type instead of intent-auditing every `shell` step (R11; deliberately supersedes the ADR-002 knock-on note). |
| `config` | component config model | Discriminated union, see below. |
| `inputs` | dict[str, Ref \| JSON literal] | The explicit input map. Mapping values that are strings beginning with a reserved ref root are references; everything else is a literal. |
| `each` | Ref \| None | When present, the step fans out positionally over the referenced collection; `item` and `index` ref roots become available in this step's `inputs`. |

### Reference grammar (Ref)

A Ref is a string in a mapping position matching:

```text
ref        = root ("." segment)*
root       = "inputs" | "steps" | "matrix" | "models" | "item" | "index"
segment    = identifier | integer
```

Rules:

- References appear in mapping positions only (input maps, `each`, `outputs`, alias targets). Nothing is ever interpolated into strings - there is no template syntax to put one in.
- `steps.<name>.<field...>` may reference earlier steps only (sequential order; no forward or self references).
- `item` / `index` are valid only inside a step with `each`.
- Ref versus literal is decided by full match, never prefix match: a string is a Ref iff it fully matches the grammar. A string matching `^(inputs|steps|matrix|models|item|index)(\.|$)` that does not fully match the grammar is a validation error - never a silent literal - and the error names the escape hatch: declare the value as a workflow input with a default. Strings without a reserved-root prefix are literals.

### Component configs

| Component | Config fields | Notes |
|-----------|---------------|-------|
| `file_read` | `path: str \| Ref`, `format: text \| json \| jsonl = text` | Output: parsed content. |
| `file_write` | `path: str \| Ref`, `format: text \| json \| jsonl \| markdown = text` | Content arrives via the input map. Final writes follow dry-run-gated idempotent conventions (runner semantics, Feature 002). |
| `shell` | `command: list[str]`, `parse_stdout: text \| json = text`, `timeout_s: int \| None` | `command` is a static argv list - no interpolation. The step's resolved inputs are delivered as a JSON object on stdin and as `PIPYER_INPUT_*` environment variables. Outputs: `stdout`, `stderr`, `exit_code`. Nonzero exit is a failure, not retried by default. |
| `python` | `script: path`, `timeout_s: int \| None` | Same I/O convention as `shell` (JSON stdin → JSON stdout), run in the project environment. The sanctioned transformation step. |
| `llm` | `model: str` (alias name), `prompt: path`, `output_schema: path \| inline JSON Schema`, `max_validation_retries: int = 2` | Prompt file placeholders bound by the input map (all bound, none unused). Alias must exist in `models`. |
| `llm_judge` | as `llm`, with a default output schema (`verdict: pass \| fail`, `score: number \| None`, `reasoning: str`) overridable via `output_schema` | |
| `assertions` | `checks: list[Check]` | Data, not expressions: each check applies one closed-enum operator to one named input. |

### Check (assertions component)

| Field | Type | Rules |
|-------|------|-------|
| `input` | str | Key into the step's input map. |
| `op` | enum: `equals`, `not_equals`, `contains`, `matches`, `gte`, `lte`, `exists`, `non_empty` | Closed set; growing it is a schema change with conformance tests. |
| `expected` | JSON \| None | Literal only - never a reference inside `expected`; compare two computed values by binding both as inputs and using a python step if genuinely needed. |

### Settings

| Field | Type | Rules |
|-------|------|-------|
| `concurrency` | int = 1 | Item-level parallelism bound (runner semantics in Feature 002). |
| `max_failures` | int \| None | Failure budget: absolute count (None = unlimited). |
| `max_failure_rate` | float \| None | Failure budget: fraction 0..1. |
| `results_dir` | str = `"runs"` | Where run evidence and checkpoints land, `<results_dir>/<run_id>/`. |

## Dry-run validation rules (FR-010, FR-021)

Structural validation (`model_validate`) plus these cross-checks, every failure naming the offending element by location (e.g. `steps[2].inputs.test_output`):

1. Step names unique; all identifiers match the pattern.
2. Every Ref resolves: to a declared input, an earlier step, a matrix dimension, a model alias, or `item`/`index` within an `each` step.
3. Root-prefixed strings that fail the full-grammar match are errors naming the declare-an-input escape hatch (never silently treated as literals).
4. `each` targets a Ref (which must, structurally, be able to yield a collection).
5. Every `llm`/`llm_judge` `model` names an existing alias; alias Ref targets resolve.
6. Prompt files exist; every named placeholder in the prompt is bound by the input map; every input-map binding for a prompt corresponds to a placeholder (unbound and unused are both errors - legible strictness). Prompt paths resolve relative to the workflow file's location, identically in the library API and the CLI (library parity, SC-004); direct-construction workflows supply the base directory as an explicit validation argument.
7. Matrix dimensions are non-empty lists: an empty dimension means zero executable cells and is rejected as an authoring error (R12). Empty `each` collections are runtime data and not a dry-run concern.
8. `outputs` refs resolve.
9. `schema_version` is supported.
10. `extra="forbid"` everywhere: unknown keys are named in errors.

## Canonical serialization (R7)

- Deterministic JSON over the validated model: UTF-8, sorted keys, compact separators, defaults materialized, `schema_version` included.
- `workflow_hash` = SHA-256 of exactly those bytes.
- One definition, three jobs: dual-surface equality (SC-003), workflow hashing (FR-016), resume matching (Feature 002).

## Run-record schema entities

### StepResult (FR-014, FR-015)

| Field | Type | Rules |
|-------|------|-------|
| `schema_version` | str | Run-record schema version (`"1"`). |
| `run_id` | str | Unique, lexically sortable. |
| `step` | str | Step name. |
| `component` | str | Component type. |
| `status` | enum: `success`, `failure`, `skipped` | Every execution outcome is one of these - never an omission. |
| `attempt` | int = 1 | Runner-level attempt number. |
| `output` | JSON \| None | Present on success. |
| `error` | StepError \| None | Present on failure; on `skipped`, holds the skip reason (`upstream_failure`). |
| `started_at` / `finished_at` | ISO-8601 UTC | |
| `duration_ms` | int | |
| `usage` | UsageCost \| None | Required for `llm`/`llm_judge` steps. |
| `matrix` | dict[str, JSON] \| None | The cell's parameters, attached to every relevant result (aggregation key). |
| `item_index` | int \| None | Positional identity within `each` (duplicate item values stay unambiguous). |
| `entity_id` | str \| None | Optional durable entity ID (ADR-006 carve-out). |
| `input_refs` | dict[str, str] | Input name → source reference (provenance). |
| `input_hash` | str | Hash of resolved inputs (resume matching). |
| `component_version` | str | |

### UsageCost (FR-015)

| Field | Type |
|-------|------|
| `provider` | str |
| `model` | str |
| `input_tokens` / `output_tokens` | int |
| `estimated_cost` | decimal (string-serialized) \| None |
| `cost_table_version` | str \| None |
| `counts_source` | enum: `provider_reported`, `estimated` |
| `validation_attempts` | int = 1 (internal attempts consumed, bounded and visible - FR-002) |

### StepError

| Field | Type | Rules |
|-------|------|-------|
| `category` | enum, R8 taxonomy | `output_validation_error`, `transport_error`, `rate_limited`, `provider_error`, `timeout`, `nonzero_exit`, `assertion_failed`, `upstream_failure`, `interrupted`, `unclassified`. |
| `message` | str | Human-legible. |
| `detail` | JSON \| None | Shape-preserving capture of the underlying failure. |

### Run-level record (FR-016)

| Field | Type |
|-------|------|
| `schema_version` | str |
| `run_id` | str |
| `workflow_name` | str |
| `workflow_hash` | str (over canonical bytes) |
| `config_snapshot` | JSON: resolved inputs (never secrets), resolved alias table, settings, matrix dimensions |
| `git_commit` | str \| None (when available) |
| `started_at` / `finished_at` | ISO-8601 UTC |
| `status` | enum: `completed`, `halted`, `interrupted` |
| `halt_reason` | str \| None (failure-budget halts are recorded events) |
| `totals` | JSON: step count, item count, failures, skips, tokens, estimated cost |

### JSONL event framing

Each line of the machine log is one self-contained event: `run_started`, `step_result`, `run_halted`, `run_finished` - each carrying `schema_version` and `run_id`. Append-only, single-writer. A corrupt trailing line (interrupted write) is detectable by JSON parse failure on the final line only; the contract requires detection to be representable (recovery behavior is Feature 002, fixture authored now). The markdown run summary is derivable from the log alone.

### CheckpointSnapshot (R6)

| Field | Type |
|-------|------|
| `schema_version` | str |
| `run_id` | str |
| `workflow_hash` | str |
| `config_hash` | str |
| `completed` | dict: step key (`step`, `item_index`, matrix cell) → `{input_hash, event_ref}` |
| `written_at` | ISO-8601 UTC |

Derived from the event log, atomically written, never authoritative: missing or corrupt snapshots reconstruct from the log (conformance area).

## Relationships

```text
Workflow 1──* Step ──1 ComponentConfig
Workflow 1──* ModelAlias        (llm steps reference by name)
Workflow 1──* MatrixDimension   (expansion → cells; params attach to StepResults)
Run      1──* StepResult        (per step × item × cell × attempt)
Run      1──1 CheckpointSnapshot (derived from the event log)
StepResult *──1 ErrorTaxonomy category (closed enum)
```

## State transitions

Records are immutable events - a `StepResult` is written once with its final status; nothing mutates. Run status is the only lifecycle: `running → completed | halted | interrupted` (halted = failure budget breached, itself a recorded event).
