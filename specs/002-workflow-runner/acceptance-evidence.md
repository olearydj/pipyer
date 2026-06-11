# Feature 002 Acceptance Evidence (T036/T037)

**Run**: `20260611-210517-6a8fb0` at
`/Volumes/Casa/au/teaching/INSY3010-PySQL/_archive/25-26.Sp/grading/t2/runs/pipyer-acceptance/`
(external, gitignored; the corpus and all outputs stay beside the archive, never in this repo).
**Gate verdict**: GO - recorded 2026-06-12 after cross-session review with user arbitration (SC-008).

## What ran

The archived INSY 3010 Spring 2026 Test 2 corpus (47 students × 4 problems, 188 rows), graded by
`workflows/gradebot-t2/` on the pinned baseline model `anthropic:claude-sonnet-4-5-20250929`,
compared per entry against the raw v2 machine baseline and the published v2-patched totals.
One logical run, one append-only event log, spanning: a real SIGINT mid-batch, four resumes
(including one demonstrating R25 failed-carryover semantics by refusing to re-run the very unit
under repair without `--retry-failed`), 224 hash-skipped units with zero recomputation, and the
R14 op-chain resolving the provider key end to end.

Cost: 183 grade calls, 342,298 input / 41,128 output tokens, $1.64 estimated
(provider-reported counts; genai-prices-verified table entry).

## Agreement (FR-022, SC-004)

| Statistic | Value |
|-----------|-------|
| Entries / graded | 188 / 183 |
| Raw v2 exact-match rate | 89.07% |
| Published exact-match rate | 86.89% |
| Agrees | 159 |
| Expected human correction (known patches) | 9 |
| Unexplained | 15 (8.2% vs the 1.7% rerun-noise floor) |
| Ungraded (harness timeouts) | 5 |

Decomposition of the 15 unexplained:

- 13 are single-rubric-item flips (delta exactly 0.12) - the same shape as the measured rerun
  noise, elevated above the floor by reconstructed-vs-archived prompt differences and the
  structured-output channel change (StructuredDict JSON vs the original grader's format).
- 2 are threshold crossings (0.0 → 0.68) that the independent reviewer flagged as possibly
  systematic - adjudicated below, in the runner's favor.

The 5 ungraded rows are infinite-loop submissions whose harness runs timed out; the baseline
graded their code anyway (grade-the-logic-despite-execution-failure policy) while the workflow's
R2 skip policy did not. Recorded as a workflow-design difference with a known fix
(the harness reports execution failure as data so grading proceeds), not a runner defect.

## Cross-session review trail (SC-008, never self-graded)

1. Independent context-free reviewer (comparison record + run summary only): DISSENT, on
   exactly the two threshold-crossing rows - "0.0 to 0.68 on identical code suggests a
   structural difference, not noise; investigate before accepting."
2. Adjudication by forensics, not argument: both submissions contain syntax errors
   (`def total_by_group = (records...)`; a missing colon). The baseline's cached analysis shows
   its grader zeroed all four rubric items for both - the documented undergrading failure mode
   that the v2-patched round corrected in seven other cases ("correct algorithms with typos...
   evaluate based on code logic even when execution fails"). These two rows escaped that human
   correction because the cross-validation band was 0.44-0.88 and they scored 0.0, below it.
   Pipyer's grading (one false rubric item each) follows the documented policy that the
   baseline's raw output violated. The reviewer's structural-difference hypothesis was correct;
   the differing system is the baseline.
3. Standing reviewer: CONCUR - uniform execution, honest per-item evidence, disagreements
   explained at rubric-item granularity, and the two scariest rows resolved as the runner
   outperforming the baseline's documented weakness on rows human review never reached.
4. User arbitration: GO.

## Runner defects found by the acceptance run (all fixed, tested, committed)

1. Orphaned subprocess children on interrupt (system OOM in the field): every component child
   now runs in its own process group, group-killed on timeout/completion/engine-exit;
   captured output is byte-capped with recorded truncation (`_subproc.py`, 4 unit tests).
2. Harness stdout contamination: student module-level prints corrupted the JSON contract;
   the harness now captures student stdout as capped data, and the scorer salvages legacy
   raw-text records by trailing-JSON extraction.
3. Stale skip/failure state across resume segments: a unit retried to success left its
   prior-segment skip marker in place, blocking downstreams. Unit state is now mutually
   exclusive with latest-record-wins in both the replay fold and all runtime finish paths
   (regression test walks the exact history that exposed it).

## Carried forward

- Script content is not part of unit identity: fixing a script does not recompute a succeeded
  unit, and re-running a failed one needs `--retry-failed` even when the fix is the point.
  Candidate for the next contracts touch: hash script-file content into unit identity.
- Workflow fix for the 5 ungraded rows: harness-internal bounding of student execution with
  timeout-as-data, so grading proceeds per the grade-the-logic policy.
- The agreement-comparison machinery (layered baselines, quantized-cause lookup,
  classification) is direct design input for Feature 003's run-comparison tooling, along with
  the archived 1.7%/17.5% stability numbers.
- A same-corpus, second-model matrix run is Feature 003's ready-made acceptance experiment
  ("should we upgrade the grading model for fall").
