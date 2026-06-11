# Contract: Run-Record Schema

The evidence-side contract. Full field definitions live in
[data-model.md](../data-model.md); this file states the guarantees conformance tests pin.

## Guarantees

1. No silent omissions. Every step execution outcome - success, failure of any category,
   skip - is representable as a status-bearing `StepResult`. Failure budgets halting a run is
   itself a recorded event (`run_halted`).
2. Positional identity. Per-item records carry `item_index`; duplicate item values never make
   records ambiguous. `entity_id` is optional and additive.
3. Cost is first-class. Every `llm`/`llm_judge` result carries provider, model, token counts,
   estimated cost, cost-table version, and `counts_source` (provider-reported vs estimated).
   Internal validation attempts are counted in `validation_attempts` - bounded, visible, and
   non-multiplying with runner-level `attempt`.
4. Matrix parameters attach to every relevant result; cost and quality aggregate by dimension
   without joins against external state.
5. Provenance: each result records `input_refs` (where every input came from) and
   `input_hash` (what the inputs were, for resume matching).
6. The error taxonomy is a closed enum with an explicit `unclassified` member; nothing is
   coerced into a wrong category.
7. Append-only JSONL machine log, single-writer, each line a self-contained event carrying
   `schema_version` and `run_id`; lines are append-friendly to external stores. A corrupt
   trailing line is detectable. The human-readable markdown summary is derivable from the log
   alone.
8. The checkpoint snapshot is derived state: atomically written, reconstructible from the
   event log, never authoritative over it.

## Conformance fixtures

Schema-level (must pass in this feature):

| Fixture area | Expectation |
|--------------|-------------|
| StepResult for every status × component | Validates |
| Failure record per taxonomy category | Validates; categories closed (unknown → rejected) |
| Skip record with `upstream_failure` reason | Validates |
| LLM result without usage | Rejected (usage required for LLM components) |
| Usage with `counts_source: estimated` and no cost table | Validates (local-model case) |
| Matrix params attached; aggregation by dimension over a fixture log | Totals match hand-computed values |
| Duplicate item values, distinct `item_index` | Unambiguous |
| Run-level record with/without `git_commit` | Validates |
| CheckpointSnapshot instance | Validates (derived-state schema only; reconstruction is Feature 002) |
| JSONL log with corrupt trailing line | Detection representable (parse isolates final line) |

Execution-behavior (authored now with expected outcomes, exercised in Feature 002):

resume-after-interruption without recomputing completed work; failure-budget halt event;
checkpoint reconstruction from event log; downstream skip on upstream item failure; shell
nonzero exit without retry; LLM validation failure after bounded internal attempts; empty
`each` collection yielding zero per-item records, recorded explicitly (R12); markdown run
summary derived from a fixture event log alone (FR-016).
