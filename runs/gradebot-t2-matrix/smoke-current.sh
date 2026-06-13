#!/usr/bin/env bash
set -u -o pipefail

usage() {
  cat <<'USAGE'
Usage: runs/gradebot-t2-matrix/smoke-current.sh [options]

Runs a zero-spend GradeBot T2 matrix smoke against the PII-free fixture using
two duplicate `test` model cells, then compares cell[0] and cell[1].

Options:
  -h, --help  Show this help.

Environment overrides:
  SMOKE        Smoke corpus path. Defaults to tests/fixtures/gradebot_t2_smoke.
  RESULTS_DIR  Pipyer results dir used during the smoke run.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf "Unknown option: %s\n\n" "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

START_STAMP="$(date -u +%Y%m%d-%H%M%S)"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PENDING_DIR="$SCRIPT_DIR/.pending-smoke-$START_STAMP"
RESULTS_DIR="${RESULTS_DIR:-$PENDING_DIR/.pipyer-results}"
ARTIFACTS_DIR="$PENDING_DIR/artifacts"
INPUTS_DIR="$PENDING_DIR/inputs"
COMMANDS_MD="$PENDING_DIR/commands.md"
TRANSCRIPT_LOG="$PENDING_DIR/transcript.log"
CREATED_BY="runs/gradebot-t2-matrix/smoke-current.sh"
SMOKE="${SMOKE:-$REPO_ROOT/tests/fixtures/gradebot_t2_smoke}"
SMOKE_PATH="$(cd "$SMOKE" && pwd)"
WORKFLOW="$PENDING_DIR/workflows/gradebot-t2-matrix/workflow.yaml"

mkdir -p "$ARTIFACTS_DIR" "$INPUTS_DIR" "$RESULTS_DIR" || exit 1
if ! copy_repo_evidence; then
  printf "Failed to copy repo evidence; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi
if ! stage_matrix_workflows "$PENDING_DIR" test test; then
  printf "Failed to stage the test-model matrix workflow; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

cat > "$COMMANDS_MD" <<EOF
# GradeBot T2 Matrix Smoke Commands

Generated: $START_ISO

Archive was created by \`$CREATED_BY\`.

## Environment

\`\`\`bash
cd $REPO_ROOT
SMOKE=$SMOKE_PATH
RESULTS_DIR=$RESULTS_DIR
MATRIX=(test test)
\`\`\`
EOF

{
  printf "GradeBot T2 matrix smoke transcript\n"
  printf "Generated: %s\n" "$START_ISO"
  printf "Repo: %s\n" "$REPO_ROOT"
  printf "Workflow: %s\n" "$WORKFLOW"
  printf "Smoke corpus: %s\n" "$SMOKE_PATH"
} > "$TRANSCRIPT_LOG"

run_logged "validate staged matrix workflow" uv run pipyer validate "$WORKFLOW"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Validation failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

run_logged "zero-spend matrix smoke run" uv run pipyer run "$WORKFLOW" \
  --input "corpus_dir=$SMOKE_PATH" \
  --input "raw_baseline_csv=published/scored/grading_results_smoke.csv" \
  --input "published_baseline_csv=published/final/grading_results_smoke.csv" \
  --input "patch_manifest=published/patched/patch_manifest.json" \
  --input "annotations_file=$SMOKE_PATH/annotations.json" \
  --input 'point_weights={"test2.1-double_it": 30, "test2.2-shout": 20}' \
  --results-dir "$RESULTS_DIR"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Smoke run failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

RUN_DIR="$(latest_run_dir)"
if [[ -z "$RUN_DIR" || ! -f "$RUN_DIR/run.json" ]]; then
  printf "No Pipyer run directory found under %s\n" "$RESULTS_DIR" >&2
  printf "Partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

mv "$RUN_DIR" "$ARTIFACTS_DIR/run"
rmdir "$RESULTS_DIR" 2>/dev/null || true

run_logged "compare duplicate test cells" uv run pipyer compare "$ARTIFACTS_DIR/run" \
  --results-dir "$RESULTS_DIR" \
  --left-cell-index 0 \
  --right-cell-index 1 \
  --stability \
  --output-dir "$ARTIFACTS_DIR/comparison"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Cell comparison failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

RUN_ID="$(run_record_id "$ARTIFACTS_DIR/run")"
FINAL_DIR="$SCRIPT_DIR/smoke-$RUN_ID"
if [[ -e "$FINAL_DIR" ]]; then
  FINAL_DIR="$SCRIPT_DIR/smoke-$RUN_ID-$START_STAMP"
fi

{
  printf "\n## Archive Finalization\n\n"
  printf -- "- Final archive: \`%s\`\n" "$FINAL_DIR"
  printf -- "- Pipyer run directory: \`artifacts/run\`\n"
  printf -- "- Comparison artifacts: \`artifacts/comparison\`\n"
} >> "$COMMANDS_MD"

mv "$PENDING_DIR" "$FINAL_DIR"
ARCHIVE_DIR="$FINAL_DIR"
ARTIFACT_RUN="$ARCHIVE_DIR/artifacts/run"
write_run_archive_metadata

printf "\nSmoke archive complete:\n%s\n" "$ARCHIVE_DIR"
