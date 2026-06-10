# Pipyer

Pipyer is a deterministic orchestration tool for reproducible LLM pipelines: the workflow controls what happens; the model works inside the steps. Declarative data defines the shape, Python and shell do the deterministic work, LLMs supply judgment within steps, and every run leaves a complete evidence record (inputs, outputs, failures, cost) that supports resume, comparison, and improvement.

Status: pre-implementation. The consolidated base specification is `docs/SPEC.md`; the feature sequence is `docs/BACKLOG.md`; the entry-gate spike is `docs/SPIKE.md`.

## Bootstrap (First Session)

This repo is scaffolded for spec-driven development with [spec-kit](https://github.com/github/spec-kit):

1. `specify init . --integration <claude|codex>` (or both).
2. `/speckit.constitution` - generate the constitution from the Philosophy and Decision Record sections of `docs/SPEC.md`. Transcribe decided content; do not re-explore.
3. `/speckit.specify` for feature 001 from `docs/BACKLOG.md` (spike plus contracts), then `/speckit.plan`, `/speckit.tasks`, `/speckit.implement`.

Python tooling: `uv` only (never pip). Project not yet initialized; `uv init` is part of feature 001.

## Lineage

Design history, ADRs (001-006), and the empirical evidence base live in the author's Obsidian vault at `projects/pipyer/` (private). This repo is self-contained; the vault is provenance, not a dependency. Predecessors and consumers: GradeBot (`/Volumes/Casa/dev/gradebot`), DEMA-LLM (`/Volumes/Casa/dev/dema-llm`), twc-bridge (`/Volumes/Casa/dev/twc-bridge`), danvas (`/Volumes/Casa/dev/danvas`), and the CLIDE specification (March 2026).
