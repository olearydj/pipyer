# Document Extraction Bench Findings

Run date: 2026-07-27

## Result

The quality-path recommendation remains an agent CLI, with `claude -p --model claude-sonnet-5` as the default for correspondence conversion. Claude Sonnet 5 matched Claude Opus 5 on the decisive in-context image-description axis, completed the four documents 21% faster, and cost 44% less. Opus is an escalation option when marginally richer prose is worth the extra cost.

Codex GPT-5.6 Sol also matched the in-context description standard and therefore triggered the precommitted challenger clause. The tie-break still favors Sonnet: Sol was 27% slower than Sonnet across this set, its CLI exposed token counts but no dollar cost, and its much larger audit stream did not produce a material quality advantage. Sol is a credible independent fallback and cross-check, not the default. GPT-5.6 Terra does not qualify for the quality role because it summarized away substantive material in the 73-page PDF and used generic placeholders for important deck visuals.

No local tool matched an agent on contextual visual interpretation. If subscription independence becomes a requirement, use Docling for PDFs and dense tables, and MarkItDown for fast Office extraction when speaker notes matter. That local mode knowingly leaves contextual image descriptions for a separate vision pass.

## Verdict Against the Decision Rule

The decision rule was: `claude -p` keeps the correspondence role unless a challenger matches its in-context description quality, or subscription independence becomes a requirement.

**Verdict:** the match clause was triggered by Codex GPT-5.6 Sol, but the operational tie-break retains the Claude CLI family and selects Claude Sonnet 5 as the default model. Sol matched the decisive quality axis but did not beat Sonnet on latency, known cost, or output quality. Subscription independence was not imposed for this decision; if it is imposed later, the best-local route is format-specific rather than a single converter: Docling for PDF/table work and MarkItDown for Office text plus PPTX notes.

## Scope and Evidence

The expanded matrix contains six converters over four locked documents, for 24 scored cells. It ran in two stages so the harness was proven before the heavyweight local model was added.

| Phase | Pipyer run | Cells | Result | Wall time |
|---|---|---:|---|---:|
| MarkItDown plus four agent models | `20260727-145127-c56d86` | 20 | 20 succeeded | 46m 29s |
| Docling | `20260727-153922-a5b99c` | 4 | 4 succeeded | 4m 32s |
| Combined scored matrix | both runs | 24 | 24 succeeded | 51m 01s |

The scored harness evidence is under `runs/doc-extract-bench/2026-07-27-harness-02/`; Docling evidence is under `runs/doc-extract-bench/2026-07-27-docling-01/`. The diagnostic run `2026-07-27-harness-01/` is retained because its Claude binary-file failure led to the final headless invocation, but it is not scored.

The four source hashes are locked in `fixtures/MANIFEST.json`. The requested March 2026 TI extract could not be found in the project, teaching workspace, Spotlight results, or available session-history index. The substitute is pages 70–74 of TI's current official AM62x datasheet. This preserves a dense five-page table case, but it breaks direct comparability with the old ligature result.

## Scoring Method

The source DOCX was rendered and inspected across all five pages, including its two embedded map images and comparison table. The PPTX was rendered and inspected across all 15 slides; its package contained six nonempty speaker-note payloads. Both PDFs were inspected through rendered pages and extracted text. Each Markdown output was then read side by side against those sources.

Qualitative scores use `0` = absent or failed, `1` = substantial loss, `2` = usable with meaningful defects, and `3` = faithful and semantically useful. Image handling keeps the design's exact rubric: `0` ignored, `1` extracted file only, `2` generic description, `3` description in context. The table reports an across-fixture judgment; fixture-specific exceptions follow it.

## Quality Comparison

| Converter | Text fidelity | Tables | Structure | Reading order | PPTX notes | Images | Overall finding |
|---|---:|---:|---:|---:|---:|---:|---|
| MarkItDown 0.1.6 | 3 | 2 | 1 | 2 | 3 | 0 | Complete raw text and notes at exceptional speed; flat PDF structure, malformed dense tables, and no visual interpretation. |
| Claude Opus 5 | 3 | 3 | 3 | 3 | 3 | 3 | Richest descriptions, complete content, and excellent reconstruction; highest measured agent cost. |
| Claude Sonnet 5 | 3 | 3 | 3 | 3 | 3 | 3 | Matches Opus on the decisive quality axes at lower cost and latency; one harmless duplicated note linkage in the deck. |
| Codex GPT-5.6 Sol | 3 | 3 | 3 | 3 | 3 | 3 | Matches contextual-description quality and preserves content; one harmless duplicated note linkage and no dollar-cost field. |
| Codex GPT-5.6 Terra | 2 | 3 | 2 | 2 | 2 | 2 | Good on the short DOCX and datasheet, but compresses the long PDF and replaces key deck visuals with generic summaries. |
| Docling 2.114.0 | 3 | 3 | 2 | 2 | 0 | 1 | Excellent local PDF tables and broadly complete text; loses deck notes/boundaries and mostly exports rather than interprets visuals. |

### Image Handling by Fixture

The TI fixture is excluded from image scoring because its challenge is dense rendered tables rather than standalone figures.

| Converter | Meeting DOCX | Software PDF | Marketing PPTX |
|---|---:|---:|---:|
| MarkItDown | 0 | 0 | 0 |
| Claude Opus 5 | 3 | 3 | 3 |
| Claude Sonnet 5 | 3 | 3 | 3 |
| Codex GPT-5.6 Sol | 3 | 3 | 3 |
| Codex GPT-5.6 Terra | 3 | 2 | 2 |
| Docling | 1 | 1 | 2 |

### Fixture Findings

| Fixture | Ground-truth checks | What separated the converters |
|---|---|---|
| Meeting notes DOCX | 5 pages, 2 map screenshots, 1 seven-row comparison table | Opus, Sonnet, and Sol preserved the table and explained both old/new maps in context. Terra was briefer but still contextual. MarkItDown ignored both images. Docling exported both; one description was absent and the other was generic and partly inaccurate. |
| Software documentation PDF | 73 pages, 15 numbered sections, central seven-layer architecture figure | Opus and Sonnet retained all sections and gave precise contextual descriptions of the architecture. Sol was complete with a somewhat shorter but still contextual description. Terra retained headings but reduced a 186 KB raw source extraction to 50 KB and omitted substantive requirements. Docling retained structure and text but only referenced the figure asset. MarkItDown was text-complete but flat and visually unaware. |
| Marketing strategy PPTX | 15 slides, 6 nonempty speaker-note payloads, multiple visual-heavy slides | Opus, Sonnet, and Sol retained slide boundaries, all notes, and meaningful visual descriptions. Terra retained the note text but sometimes mislinked it and used generic placeholders for key visuals. MarkItDown retained slide text and notes but ignored images. Docling lost slide boundaries and notes; its repeated descriptions such as “some objects and some text” were not useful context. |
| TI datasheet substitute | 5 pages of dense pin-signal tables | Opus, Sonnet, Sol, Terra, and Docling reconstructed 190 Markdown table rows with useful semantics. MarkItDown emitted roughly 180 pipe-led lines but malformed table boundaries and hierarchy. No converter showed a detected ligature corruption, but the old `ff`-to-`<` trigger was not present in this substitute, so the continuity metric is not applicable. |

## Speed and Cost

Elapsed time is measured inside `convert_stage.py`, so it includes converter execution and any cell-local model preparation but not Pipyer scheduling. Agent cost is whatever the CLI returned. Claude returned exact API-equivalent dollar fields; Codex returned token usage but no dollar field, so fabricating a dollar comparison would be misleading.

### Elapsed Seconds per Document

| Converter | Meeting DOCX | Software PDF | Marketing PPTX | TI PDF | Total | Mean |
|---|---:|---:|---:|---:|---:|---:|
| MarkItDown | 0.683 | 1.503 | 0.285 | 0.666 | 3.137 | 0.784 |
| Claude Opus 5 | 81.846 | 448.849 | 144.224 | 118.740 | 793.659 | 198.415 |
| Claude Sonnet 5 | 53.814 | 337.211 | 149.199 | 89.890 | 630.114 | 157.529 |
| Codex GPT-5.6 Sol | 72.970 | 409.655 | 204.899 | 115.585 | 803.109 | 200.777 |
| Codex GPT-5.6 Terra | 80.917 | 208.652 | 155.917 | 112.233 | 557.719 | 139.430 |
| Docling | 18.727 | 221.337 | 8.886 | 22.464 | 271.414 | 67.854 |

### Dollar Cost per Document

| Converter | Meeting DOCX | Software PDF | Marketing PPTX | TI PDF | Total | Mean |
|---|---:|---:|---:|---:|---:|---:|
| MarkItDown | $0 | $0 | $0 | $0 | $0 | $0 |
| Claude Opus 5 | $0.3574 | $2.1623 | $0.7318 | $0.5212 | $3.7727 | $0.9432 |
| Claude Sonnet 5 | $0.1563 | $1.1489 | $0.4637 | $0.3424 | $2.1113 | $0.5278 |
| Codex GPT-5.6 Sol | N/A | N/A | N/A | N/A | N/A | N/A |
| Codex GPT-5.6 Terra | N/A | N/A | N/A | N/A | N/A | N/A |
| Docling | $0 | $0 | $0 | $0 | $0 | $0 |

### Agent Token Evidence

| Model | Reported input tokens | Reported output tokens | Reported cache-read tokens | Cost field |
|---|---:|---:|---:|---|
| Claude Opus 5 | 84 | 75,442 | 960,704 | $3.772688 total |
| Claude Sonnet 5 | 86 | 69,929 | 760,053 | $2.111283 total |
| Codex GPT-5.6 Sol | 1,016,193 | 40,156 | 873,728 | Not exposed by CLI |
| Codex GPT-5.6 Terra | 973,348 | 27,774 | 868,352 | Not exposed by CLI |

Claude rows report the requested primary model; the total CLI cost also includes tiny helper-model calls recorded in each response. Claude's input/cache accounting is not directly comparable with Codex's token schema. These numbers are provenance, not a model-efficiency ranking.

## Setup and Dependency Cost

| Converter | Reproducibility pin | Observed setup/dependency profile | Operational caveat |
|---|---|---|---|
| MarkItDown | `markitdown[pdf,docx,pptx]==0.1.6` via isolated `uvx` | Small Python stack; warm cells complete in under two seconds | No contextual image path in the tested configuration. |
| Claude models | Claude Code 2.1.220; exact `claude-opus-5` and `claude-sonnet-5` model names | Existing authenticated CLI; no project dependency install | Network/subscription required; safe-mode denied two compound cleanup commands but conversion recovered. |
| Codex models | Codex CLI 0.145.0; exact `gpt-5.6-sol` and `gpt-5.6-terra`; low reasoning effort | Existing authenticated CLI; no project dependency install | Network/subscription required; dollar cost absent from JSONL. |
| Docling | `docling[vlm]==2.114.0` via isolated `uvx` | Heavy Python/ML stack plus Granite Docling and SmolVLM MLX weights; shared MarkItDown/Docling cache ended at 4.7 GiB | PDF VLM quality is strong, but Office enrichment and PPTX semantics lag. |

## Resolved Build Questions

### `doc2md` viability

The public [`neoncapy/doc2md`](https://github.com/neoncapy/doc2md) snapshot was inspected rather than admitted as a seventh converter. It is an unversioned, low-activity wrapper around MarkItDown, Docling, and related dependencies, with roughly 19.5 K lines in the inspected checkout. Its advertised Claude second tier is a manual Claude Code workflow rather than a reproducible one-shot converter with machine-readable usage evidence. It therefore adds installation weight and orchestration ambiguity without a distinct extraction engine or demonstrated QC advantage over this dispatcher plus a direct agent cell. Decision: do not adopt or score it now; revisit only if it ships a versioned noninteractive command and automated QC loop.

### Docling flags and Apple acceleration

PDFs use `docling convert ... --pipeline vlm --vlm-model granite_docling --device mps`; Office files use the standard pipeline with `--enrich-picture-description`. Referenced image export preserves assets. On this Apple Silicon host, Docling accepted the MPS device request while its auto-inline VLM resolution downloaded and used MLX variants (`ibm-granite/granite-docling-258M-mlx` and `moot20/SmolVLM-256M-Instruct-MLX`). The scored run JSON carries the earlier descriptive `/mps` label, but the invocation, cache contents, and corrected dispatcher preserve the actual distinction. No 46 MB PPTX preprocessing was required.

### Claude `-p` headless mechanics

A plain Read-only Claude cell refused the binary DOCX in the diagnostic run. The working mechanism is `claude --safe-mode -p <prompt> --model <exact-name> --tools Read,Bash --allowed-tools Read,Bash --permission-mode dontAsk --output-format json --no-session-persistence --max-budget-usd 5`. The source path is embedded in the prompt; Bash lets the agent render or unpack the binary under `/private/tmp`. JSON output supplies resolved model usage and dollar cost. The failed diagnostic evidence is intentionally archived because it validates why Bash is part of the external-CLI contract.

### Codex headless mechanics

The direct comparison uses `codex exec --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check --sandbox read-only --model <exact-name> --config model_reasoning_effort=\"low\" --json --output-last-message <output> <prompt>`. Ephemeral, read-only execution isolates the benchmark from user rules and prevents source mutation. JSONL preserves events and token usage; the final-message file is the Markdown artifact.

## Recommended Use

| Context | Choice | Reason |
|---|---|---|
| Correspondence `convert.py` quality path | Claude Sonnet 5 through headless Claude Code | Best quality/cost/latency balance among the models that achieved contextual visual descriptions. |
| Quality escalation | Claude Opus 5 | Marginally richer prose for unusually ambiguous visual documents, at materially higher cost. |
| Independent agent fallback or adjudication | Codex GPT-5.6 Sol | Matches the contextual-description bar and provides a different agent stack. |
| Subscription-independent PDFs or dense tables | Docling Granite Docling VLM | Best local structured extraction in this matrix. |
| Fast Office inventory, especially PPTX notes | MarkItDown | Sub-second-to-low-second extraction and complete note text, when image meaning is not required. |
| Codex Terra | Do not use for faithful conversion | Faster than Sol on the long PDF, but speed came with substantive compression and visual loss. |

The eventual correspondence converter should keep the design's source-SHA cache, record the exact model and prompt hash in front matter, preserve the raw agent response evidence, and expose the local fallback by format rather than pretending it is quality-equivalent.

## Limitations

This is a four-document judgment set, not a statistical benchmark. Agent CLIs can vary across reruns even with exact model names and prompt hashes. Claude's reported dollar figures and Codex's subscription/token accounting are not symmetric. The TI fixture substitution invalidates direct comparison with the March 2026 ligature table. Finally, the software PDF was less screenshot-heavy than its design description: inspection found one central substantive architecture figure, so the deck and DOCX carried more of the visual-quality judgment.
