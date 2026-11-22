# Document Extraction Bench - Round 2 Brief

Status: design only; drafted 2026-07-27 in a dema-llm session after evaluating round 1 (`findings.md`). Round 1's quality-path verdict (Claude Sonnet 5 headless) is adopted and out of scope here - the correspondence converter proceeds on it separately. Round 2 answers the two questions round 1 left open.

## Questions

1. Local ladder: does the local verdict change when local mode is represented by real models instead of the sub-1B pair (Granite-Docling-258M, SmolVLM-256M) that Docling auto-selected? Round 1's "no local tool matched agent quality" is provisional until mid-size local models are tested.
2. Evaluation governance: replace the single, unblinded, self-family judge with an evaluation matrix that is mostly computed and, where judgment is irreducible, blind, pairwise, cross-family, and agreement-measured. This stage becomes permanent infrastructure: any future converter is one new convert cell scored by the same machinery.

## Stage 1: Convert (expanded local matrix)

Reuse, do not re-run: the four locked fixtures (`fixtures/MANIFEST.json`) and all round-1 outputs (agent cells and round-1 Docling/MarkItDown cells) from `runs/doc-extract-bench/2026-07-27-harness-02/` and `2026-07-27-docling-01/`. New cells only:

| Tier | Cell | Notes |
|---|---|---|
| ~3B ladder | Docling with a ~3B VLM replacing the 258M default | Config change to the existing Docling dispatcher path; keep `--device mps` |
| ~3B ladder | DeepSeek-OCR 2 (3B) | The headline candidate: 91% OmniDocBench v1.5, reported parse edit distance better than Gemini-3 Pro. Runtime TBD (MLX community port vs Ollama vs vllm); if only PDF-capable, score PDF fixtures and mark Office cells N/A rather than forcing it |
| ~3B ladder | dots.ocr | Same benchmark cohort; packaging TBD; same N/A rule |
| 7B+ ceiling | One Qwen-VL-class model via Ollama or MLX, used as Docling's VLM or as a standalone describe pass | Answers "does local ever reach agent-grade visual interpretation" |

Deferred unless trivially easy: MinerU 2.5 (heavy pipeline), Marker (GPL). Record any exclusion with a one-line reason, as round 1 did for doc2md.

Ladder context: the tiers map onto the DEMA air-gap hardware tiers (dema-llm TDD ch 7); the ladder's output is a quality-vs-footprint frontier, not just a winner.

## Stage 2: Evaluate (the new matrix)

### Computed metrics first (python steps; deterministic; score ALL cells, round-1 outputs included)

- Speaker-note recall: presence of the 6 known PPTX note payloads (exact/normalized string match).
- Outline recall: heading/section match against a source outline extracted once per fixture.
- Table fidelity: table-cell F1 against gold cell grids for the TI fixture and the DOCX comparison table. Gold is built once, human-verified, committed under `fixtures/gold/` - it amortizes across every future round.
- Coverage alarm: output size ratio vs raw text-layer extraction (would have flagged Terra's 186 KB → 50 KB compression automatically).
- Image accounting: every source image maps to an extracted asset or a description; count misses.

### Judged residue (llm_judge matrix; only the contextual-description axis)

- Pairwise forced choice, not absolute scores: present two anonymized outputs for the same fixture, ask which describes visuals more faithfully-in-context; Bradley-Terry (or simple win-rate) ranking. Round 1's 0-3 rubric saturated at 3 for four converters; pairwise is the discriminator.
- Blind and randomized: strip converter identity, shuffle A/B order per comparison.
- Cross-family panel: an output is never judged solely by its own model family. Minimum panel: Claude judges Codex+local outputs, Codex judges Claude+local outputs; add a third family (Gemini CLI) if available - open question below.
- Agreement statistics in the summary: inter-judge agreement (Cohen's kappa or Krippendorff's alpha) across the panel. This is the standing "who judges the judges" answer - low agreement means the axis is underspecified, and the report must say so.
- Human anchor: emit a stratified 6-cell sample (2 per non-TI fixture, mixing tiers) for Dan to score on the same pairwise questions; report judge-vs-human agreement. Pause the workflow or deliver the sample as a follow-up artifact - do not skip it.

### Stability check

Re-run the round-1 winning convert cell (Sonnet, one fixture) 3x; report output variance (diff magnitude, metric deltas). Closes round 1's admitted rerun-variance gap.

## Evidence, Recommendation, and Decision Authority

Governing principle: the workflow produces evidence and a recommendation; the human in the loop decides. Neither the computed metrics nor the judge panel has authority to overturn a standing decision on its own - the same division of labor as DEMA-LLM's three-outcome model and Pipyer's ADR-001 (directing, not delegating). The report must therefore end with an explicit recommendation section that states, for each standing decision, whether the new evidence supports keeping it, revising it, or cannot say - with the supporting evidence cited and any conflicts between evidence sources (metrics vs panel, judge vs human anchor) surfaced rather than resolved silently.

Precommitted evidence thresholds (these define when evidence is *strong enough to flag for revision*, not when revision happens):

- Local verdict: flag the dojo note's "no local tool matched agent quality" claim for revision if any local converter (a) wins >= 40% of blind pairwise comparisons against Claude Sonnet 5 on the description axis, and (b) shows no regression vs round-1 Docling on the computed metrics. Partial outcome ("structure yes, interpretation approaching") is reportable as a graded claim with the win-rate attached.
- Quality path: flag the Sonnet recommendation for reconsideration if computed metrics reveal a defect in its outputs the round-1 judge missed (Terra-style omission, table loss), or if a challenger beats it in blind pairwise comparison decisively (>= 70% win rate) with substantial inter-judge agreement (kappa >= 0.6). Either way, report the evidence and a recommendation; do not rewrite the standing recommendation in the findings as if decided.
- Method adoption: recommend the panel as the standing evaluation method if inter-judge agreement is substantial (kappa >= 0.6) and judge-human agreement on the anchor sample is comparable; otherwise recommend keeping the human anchor mandatory. Report the statistics either way.

## Deliverables

- `findings-round-2.md`: ladder frontier table (quality vs footprint vs speed), pairwise rankings with agreement statistics, stability results, and a closing recommendation section per the evidence-thresholds framework - evidence and recommendations for the human decision, not verdicts.
- `fixtures/gold/` committed gold references + the extraction scripts that built them.
- Updated `proposed-vault-update.md` superseding round 1's draft (still review-only; the vault is not modified by the workflow).
- Run archives + checksums per round-1 convention; judging evidence included.

## Open Questions for the Build Session

- Third judge family: is a Gemini CLI available and authenticated on this host? If not, run the two-family panel and note the limitation.
- DeepSeek-OCR 2 and dots.ocr runtimes on Apple Silicon: MLX ports vs Ollama vs skip-with-reason. Time-box packaging fights; a candidate that cannot run headless and pinned within the time box is excluded with a one-liner, round-1 style.
- Judge cost/budget: pairwise comparisons x panel size multiplies calls; outputs are short, but set a `--max-budget-usd`-style cap per judge cell and report total judging cost separately from conversion cost.
- Whether Docling's VLM swap accepts an arbitrary HF/MLX model id cleanly; if not, run the 3B VLM as a standalone describe pass and note the harness difference.
