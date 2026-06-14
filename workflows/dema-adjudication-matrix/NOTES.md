# DEMA Pipyer Integration Notes

This workflow is a bridge harness, not the target architecture.

The current implementation drives DEMA through shell steps that call the
`dema-llm` CLI. That is useful Sprint 03 evidence: it validates Pipyer's matrix
execution, run archive, resume/checkpoint semantics, and comparison artifacts
against an existing DEMA experiment surface without rewriting DEMA first.

The long-term direction is different. Pipyer should own orchestration, matrix
expansion, provider calls, secrets, usage/cost capture, failure semantics,
resume, and comparison. DEMA should provide domain logic as importable modules
or workflow assets, not act as the runner inside the Pipyer path.

Expected migration path:

1. Keep this CLI bridge as compatibility evidence and a regression baseline.
2. Factor or expose DEMA library functions for deterministic domain work:
   candidate-pair generation, prompt/context construction, decision validation,
   gate application, clustering, and evaluation.
3. Build a Pipyer-native workflow where:
   - `python` steps call DEMA domain functions for triage, gates, clustering,
     and evaluation.
   - Pipyer `llm` steps adjudicate candidate pairs directly.
   - Pipyer records provider usage, cost, latency, errors, and retries as native
     `StepResult` data.
4. Compare the native workflow against this bridge harness on the same locked
   DEMA inputs before retiring the shell-driven path.

This avoids making DEMA drive Pipyer development in reverse. The bridge exists
to validate equivalence; the native workflow should make Pipyer the durable
runtime and DEMA the domain package.
