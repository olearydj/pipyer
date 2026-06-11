# Contract: Workflow Schema

The authoring-side contract. Full field definitions live in [data-model.md](../data-model.md); this file states the external guarantees that conformance tests pin and that any future runner rebuild must honor.

## Guarantees

1. A workflow is data. The schema cannot represent templating, expressions, conditionals, or loops; attempts to express them fail validation with `extra="forbid"` errors naming the offending key. There is no escape hatch.
2. Two equal authoring surfaces. `yaml.safe_load` + `model_validate` (nothing more) and direct Python construction produce the same validated model and byte-identical canonical serialization.
3. Validation is the dry-run. A workflow that passes validation is executable in principle; one that fails is rejected before anything runs, with every error naming the offending element by location path (e.g. `steps[2].inputs.test_output`).
4. References are dotted paths in mapping positions only, with reserved roots `inputs | steps | matrix | models | item | index`. Backward references only. `item`/`index` only inside `each` steps. Ref versus literal is full-match, never prefix-match: a root-prefixed string that does not fully match the grammar is a validation error naming the declare-an-input escape hatch - never a silent literal.
5. Prompts are external files with named placeholders; the step input map binds all placeholders, and binds nothing else (unbound and unused are both errors).
6. Uniformity by construction: no schema mechanism varies steps, prompts, or configuration per item within a batch (FR-013).
7. Self-identification: every workflow declares `schema_version`; unsupported versions are validation errors, not best-effort parses.
8. No credential surface: no schema field holds a secret; provider keys are environment-only.

## Canonical serialization

- Deterministic JSON over the validated model: UTF-8, sorted keys, compact separators, defaults materialized explicitly, `schema_version` included.
- `workflow_hash` = SHA-256 over exactly those bytes.
- This is the single definition used for dual-surface equality (SC-003), the workflow hash in run records, and resume matching. A schema-version bump changes canonical bytes by design, ending hash continuity at the version boundary.

## Conformance fixtures (schema-level, must pass in this feature)

| Fixture area | Expectation |
|--------------|-------------|
| Minimal valid workflow | Validates; canonical bytes stable across repeated serialization |
| GradeBot workflow, both surfaces | Validates; byte-identical canonical form; zero forbidden constructs |
| Unknown field anywhere | Rejected, key named |
| Dangling step reference | Rejected, `steps[i].inputs.<name>` named |
| Root-prefixed string not matching ref grammar | Rejected, error names the declare-an-input escape hatch |
| Forward/self step reference | Rejected |
| `item` outside `each` | Rejected |
| Unknown model alias in `llm` step | Rejected |
| Unbound prompt placeholder | Rejected, placeholder named |
| Unused prompt input binding | Rejected, binding named |
| Duplicate step names | Rejected |
| Unsupported `schema_version` | Rejected with supported-versions message |
| Matrix dimension with non-list value | Rejected |
| Matrix dimension with empty list | Rejected - zero executable cells is an authoring error (R12) |
