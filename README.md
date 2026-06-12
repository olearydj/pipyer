# Pipyer

Pipyer is a deterministic orchestration tool for reproducible LLM pipelines: the workflow controls what happens; the model works inside the steps. Declarative data defines the shape, Python and shell do the deterministic work, LLMs supply judgment within steps, and every run leaves a complete evidence record (inputs, outputs, failures, cost) that supports resume, comparison, and improvement.

Status: Features 001 and 002 complete (2026-06-12). The contracts exist as code, `pipyer validate` and `pipyer run` work end to end - sequential steps, `each` batching with failure budgets, content-hash resume, JSONL evidence with derived summaries, cost capture - and the runner passed its acceptance gate by re-grading a real archived exam against its own history (89% exact reproduction, every disagreement classified; `specs/002-workflow-runner/acceptance-evidence.md`). Feature 003 (matrix execution and run comparison) is next; its brief is `docs/sprint-03/BRIEF.md`.

## Orientation

- Constitution: `.specify/memory/constitution.md` (v2.1.0) - binds all features.
- Sprint 01 source material: `docs/sprint-01/` (base spec, feature backlog, spike plan); full record in `specs/001-pydanticai-spike-contracts/` (spike report, exit notes, plan, research R1-R14).
- Sprint 02 source material: `docs/sprint-02/BRIEF.md` - feeds `/speckit.specify` for Feature 002.
- Process: spec-driven with [spec-kit](https://github.com/github/spec-kit); each phase output gets a cross-session review; gates are never self-graded.

Try it:

```bash
uv sync
uv run pipyer validate tests/fixtures/gradebot/workflow.yaml
uv run pytest -q
```

Python tooling: `uv` only (never pip); build backend `uv_build`; ruff + ty.

## Lineage

Design history, ADRs (001-006), and the empirical evidence base live in the author's Obsidian vault at `projects/pipyer/` (private). This repo is self-contained; the vault is provenance, not a dependency. Predecessors and consumers: GradeBot (`/Volumes/Casa/dev/gradebot`), DEMA-LLM (`/Volumes/Casa/dev/dema-llm`), twc-bridge (`/Volumes/Casa/dev/twc-bridge`), danvas (`/Volumes/Casa/dev/danvas`), and the CLIDE specification (March 2026).
