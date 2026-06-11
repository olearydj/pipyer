# Planning Notes (carried from spec review)

Items deliberately not encoded in `spec.md`; they are planning decisions, not spec defects. `/speckit.plan` should resolve them.

## Secret-resolution failure: when and as what

The spec does not say what happens when the R14 secret chain fails - an LLM alias whose key resolves to nothing via `op` or env. Two open points:

- *Taxonomy*: the error taxonomy has no natural category for it. It is a configuration failure, not `transport_error` - decide whether it gets its own category or a `config_error`-style home, and where it lands in the run record.
- *Timing*: lazily at the first LLM call (mid-batch, after real work and spend) or eagerly at run start as a preflight check. The workflow declares its aliases, so the runner knows before step one whether every needed credential resolves. Fail-fast preflight is almost certainly right and matches the loud-stale-failure principle ([[design-review-standards]] loud boundary rules), but plan it explicitly rather than letting it fall out of implementation order.
