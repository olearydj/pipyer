# Document Extraction Bench - Experiment Design

Status: design only; nothing built. Drafted 2026-07-27 in a dema-llm session; to be built in a session here. This is Pipyer usage (a real workflow, like `gradebot-t2` and `dema-adjudication-matrix`), not a sprint feature - no spec-kit ceremony required. It does, however, rehearse the Feature 004 pattern (external CLIs as workflow components) at low stakes.

## Question

Which document-to-markdown converter should be the standard high-quality extraction path for doc/pdf/pptx sources, as of 2026-07? The prior answer (2026-05-11, `vault/dojo/document-extraction-tools.md`) was: Claude Code native (`claude -p`) for quality, local Python extractors for cheap inventory. The landscape has since shifted - open-weight VLM parsers matured (Docling v2.9x + Granite-Docling, DeepSeek-OCR 2, MinerU 2.5, dots.ocr), Claude gained a true high-resolution vision pass (Fable 5), and a Claude-Code-integrated converter appeared (doc2md). This bench revisits the decision with locked inputs and an evidence trail so future revisits are re-runs, not re-debates.

## Consumers of the Answer

1. `vault/projects/dema/correspondence/` - planned `convert.py` generating md versions (with in-context image/chart descriptions) of curated email-recovered documents. The immediate trigger.
2. `vault/dojo/document-extraction-tools.md` - the knowledge home; its Current Decision and comparison tables get updated from this bench's findings.
3. `/casa/dev/cdex` - course/project inventory tooling whose extractor choices cite the dojo note.

## Contenders

| Cell key | Converter | Invocation sketch | Notes |
|----------|-----------|-------------------|-------|
| `claude` | Claude Code (`claude -p`) | `claude -p "<extraction prompt>" <file>` | Incumbent. Record model ID in evidence (currently claude-fable-5). Fixed prompt: faithful markdown; describe every image, chart, diagram in context; preserve tables; include speaker notes (pptx). |
| `docling` | Docling v2.9x | `docling <file> --to md` (+ VLM/Granite mode flags TBD) | The credible self-hosted challenger. ~2 GB model download on first run; check MPS support on M-series. |
| `markitdown` | Microsoft MarkItDown v0.1.5+ | `markitdown <file>` (+ optional LLM image plugin) | Cheap deterministic baseline; expected to lose on images/layout - included to quantify the gap. |
| `doc2md` | neoncapy/doc2md | TBD after a look at the repo | Claude-Code-integrated newcomer with multi-stage QC. Include only if setup is reasonable; may be redundant with `claude` cell - that redundancy check is itself the point (adopt vs write our own convert.py). |

Deferred unless a driver appears: DeepSeek-OCR 2 / dots.ocr local VLMs (relevant if subscription-independence or air-gap becomes a requirement - the DEMA deployment logic), Mistral OCR 3 (cheap API, ~$2/1k pages), Marker (GPL + PyTorch, superseded by Docling for our purposes).

## Test Set (fixtures/, locked)

| Fixture | Source | Tests |
|---------|--------|-------|
| `meeting-notes.docx` | `vault/projects/dema/correspondence/source/2026-05-08-dema-meeting-notes.docx` (238K, image-bearing) | Born-digital docx, embedded images, the recurring-series case convert.py will handle weekly |
| `software-doc.pdf` | `.../2026-07-10-dema-final-software-documentation.pdf` | Screenshot-heavy PDF, tables, reading order |
| `marketing-deck.pptx` | `.../2026-07-01-dema-marketing-strategy.pptx` (46 MB) | Slides, charts, images, speaker-notes preservation |
| `ti-datasheet.pdf` | The TI AM62x TRM 5-page extract from the original 2026-03-28 comparison (locate it - probably under `/casa/au/teaching/INSY7740-PD2/`; if unfindable, substitute any dense multi-column datasheet and note the break in continuity) | Anchors comparability with the prior results table (ligatures, multi-column, layout) |

Copy fixtures in (do not reference the vault paths at run time); they are project-internal documents - this folder stays private like the rest of the repo.

## Workflow Shape

Matrix over `converter` (4 values) × `document` (4 values) = 16 cells; parameters only, topology fixed - one shell step per cell calling `scripts/convert_stage.py <converter> <document>`, a dispatcher that maps converter key → invocation (the `dema_stage.py` pattern). Each cell writes `output.md` (+ extracted assets if the tool produces them) and emits JSON to stdout: wall time, output size, exit status, and cost fields where knowable (tokens for `claude` via its JSON output mode if available; $0 for local tools).

Settings: modest concurrency (Docling and claude cells are heavyweight; the 46 MB pptx may need a long `timeout_s`), cell-local failure budget so one broken converter doesn't halt the matrix.

A second, non-matrix step can collect all 16 outputs into a comparison folder for side-by-side reading; `pipyer compare` covers cost/latency deltas between converter cells.

## Metrics and Judgment

Same axes as the prior note, so tables are directly comparable: text fidelity (spot-diff against source; ligature check on the datasheet), table preservation, heading/structure semantics, reading order, speaker notes (pptx only), image handling scored 0-3 (0 ignored / 1 extracted file only / 2 described generically / 3 described in context), speed, setup + dependency cost, $ cost per document.

Judgment is human side-by-side reading - 16 short outputs, no eval harness. An optional LLM-judge pass on description quality only if human reading is inconclusive.

## Decision Rule (stated before running)

`claude -p` keeps the correspondence `convert.py` role unless a challenger matches it on in-context description quality (the axis that matters most to the consumers) or unless subscription-independence becomes a requirement, in which case best-local wins for that context and the dojo note records both modes (quality path + local path), as it did in May.

## Outputs and Where They Land

- Run evidence: `runs/doc-extract-bench/` per Pipyer convention.
- `findings.md` in this folder: the filled comparison tables + decision narrative.
- `vault/dojo/document-extraction-tools.md`: updated Current Decision, landscape table, and 2026-07 comparison section (conclusions only; link back here).
- Follow-on (separate work, dema side): `correspondence/convert.py` per the decided tool; design already sketched - separate stage from sync.py, cache keyed by source sha256, md frontmatter recording source/sha/date/model.

## Open Questions for the Build Session

- doc2md viability after actually reading its repo (install weight, does it add QC value over a bare `claude -p`?).
- Docling invocation details: VLM mode vs default pipeline, MPS acceleration, and whether its docx/pptx paths are mature or PDF-first.
- `claude -p` mechanics: headless flags, attaching binary files, JSON output for token counts, model pinning for reproducibility.
- Whether the 46 MB pptx needs preprocessing (e.g., media downscale) for any contender, and whether that invalidates comparability.
