# Feature 001 Exit Notes

## Falsification census (FR-019, SC-008)

The GradeBot fixture validates with zero forbidden constructs (mechanical half,
`test_gradebot_fixture.py` - vacuously guaranteed by FR-012, as the spec notes). The
information lives in the census: for every code step, would this step exist if the schema had
a template language? A step that disappears under that hypothetical is expression-emulation
and fails the test.

### Author census (2026-06-11, implementing session)

Code steps in the fixture: 3 (`collect_submissions` python, `run_tests` shell, `summarize`
python).

1. `collect_submissions` (`scripts/collect_submissions.py`) - SURVIVES. Directory scanning
   cannot be expressed by substitution under any template language; the step exists to
   discover the batch. Honest note: it also computes `feedback_path`
   (output_dir + stem + ".md"), which is the watch-item shape relocated - a template language
   with functions (basename, strip-extension) could express that path inline. But the path
   computation rides along with genuine discovery work; deleting the template-expressible
   part does not delete the step. It does not exist *only* because the schema forbids
   expressions.
2. `run_tests` (`scripts/run_submission_tests.py`) - SURVIVES. This is the assignment's test
   harness: compile check, behavioral checks against the assignment contract, JSON summary,
   meaningful exit status. With argv templating one might invoke pytest directly, but the
   check logic and structured summary are domain work that would still need a script. Watch
   item did not trip: the per-item path reaches the harness via the stdin/env input
   convention, so no argv substitution need ever arose.
3. `summarize` (`scripts/summarize_grades.py`) - SURVIVES. Computes statistics (mean, min,
   max, graded/ungraded counts) across aligned collections - computation, not rendering.
   Honest note: the markdown-table portion of its output is template-shaped (a Jinja loop
   could render rows from data); the statistics are not. The step does not exist only for
   rendering.

Author verdict: PASS - 0 of 3 code steps exist only because the schema forbids expressions.
The predicted argv stress point (research.md watch item) was absorbed by the stdin/env
delivery convention; the per-item file path was absorbed by item data computed during
genuine collection work (`item.feedback_path`).

### Independent context-free review (2026-06-11)

A fresh reviewer agent received only the four fixture files and the single adversarial
question (no author census, no design rationale). Its census:

1. `collect_submissions` - SURVIVES, with an explicit flag: the glob discovery is genuine
   and non-template-expressible, but `student: path.stem` and `feedback_path:
   output_dir/stem.md` are "pure expression-emulation bundled into a step that must exist
   anyway" - failing a per-field standard while passing the per-step test. Its sharpest
   line: if `collect_submissions` ever stops globbing (the list arriving as an input) and
   only decorates items with derived strings, it becomes a hard FAIL.
2. `run_tests` - SURVIVES cleanly: a real harness (compile, behavioral cases, exit
   semantics); the only template-expressible portion is a summary f-string, incidental.
3. `summarize` - SURVIVES, borderline-noted: the report-rendering half is expressible by a
   loop-capable template language; it passes because the stats object (consumed as a typed
   workflow output, which no template can emit into a mapping position) and the
   missing-grade alignment are load-bearing.

Overall: 0 of 3 FAIL; no step disappears under the counterfactual.

### Reconciliation and verdict

The two censuses agree - same enumeration, same per-step verdicts, same two flagged
portions, independently identified. **Falsification verdict: PASS (SC-008).** ADR-004 is
confirmed: the GradeBot workflow expresses cleanly as data, the watch item's predicted argv
trip never materialized (stdin/env delivery absorbed it), and the per-item path question was
absorbed into item data computed during genuine discovery work.

Retained as the operational definition of the language-creep breach signal, sharpened by
this round (the census is now procedure, not vibes):

- The counterfactual question per code step: would this step exist if the schema had a
  template language?
- The per-field watch: expression-emulation can ride inside legitimate steps
  (`collect_submissions`' derived fields are the canonical example). The step-level standard
  is the falsification bar; the field-level observation is the early-warning signal future
  workflow reviews record.
- The tripwire condition: a code step that stops doing its discovery/computation and only
  derives strings has crossed from vehicle to violation - hard FAIL at that point.

## ADR-002 knock-on supersession (R11)

The vault ADR-002 knock-on note ("a separate code component is unnecessary for v1") was
annotated as superseded on 2026-06-11 after the plan review - reference, not new work. The
`python` component exists for census visibility (R11); this census is the first consumer of
that visibility, and the filter worked as designed: `component: python` enumerated the
transformation steps mechanically.

## Taxonomy amendments from the spike

None required (spike-report.md Q3): the R8 ten-category enum stands. Two documented mappings
recorded in `src/pipyer/records/step_result.py` for the Feature 002 `llm` component:
ContentFilterError → `provider_error` (type preserved in detail); IncompleteToolCall →
`output_validation_error` (detail). `FallbackExceptionGroup` is out of v1 scope;
`unclassified` catches it honestly if ever observed.

## Backlog exit criteria (finalized 2026-06-11)

Per docs/BACKLOG.md Feature 001:

- [x] Spike report written: `spike-report.md`, all four areas evidenced (stub + live legs
  closed in the review addendum), boundary outcome standalone-runner, T013 gate GO with
  cross-session review trail.
- [x] Both schemas exist with passing conformance tests: workflow schema
  (`src/pipyer/schema/`) and run-record schema (`src/pipyer/records/`); 106 conformance
  tests pass, 8 execution-behavior fixtures authored and skip-marked for Feature 002.
  Toolchain gates clean (`ruff format --check`, `ruff check`, `ty check`).
- [x] The GradeBot fixture validates: both surfaces, byte-identical canonical serialization,
  equal workflow hash (`tests/fixtures/gradebot/`, `test_gradebot_fixture.py`).
- [x] ADR-004 confirmed or escalated: CONFIRMED - falsification census PASS, two
  independent censuses in agreement (above).

## Carried into Feature 002

- Output mode (tool / native / prompted) must be alias-configurable, and local aliases must
  not be auto-picked - the live-local spike leg failed tool-mode structured output on every
  local model tried and succeeded immediately with NativeOutput (spike-report.md addendum).
- The secrets resolver graduates from `spike/_common.py` to `src/pipyer/secrets.py` (R14) -
  outside the contract modules, so the import-boundary guard is untouched.
- Error-shape mappings for the `llm` component: ContentFilterError → `provider_error`,
  IncompleteToolCall → `output_validation_error` (documented in
  `src/pipyer/records/step_result.py`).
- The 8 skip-marked execution fixtures in `tests/conformance/execution/` are written against
  the `pipyer.runner` API they expect - Feature 002 unskips them rather than rewriting.
