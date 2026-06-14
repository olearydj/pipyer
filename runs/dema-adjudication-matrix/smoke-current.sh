#!/usr/bin/env bash
set -u -o pipefail

usage() {
  cat <<'USAGE'
Usage: runs/dema-adjudication-matrix/smoke-current.sh [options]

Runs a zero-spend DEMA matrix smoke with the local stub adjudicator, then
compares cell[0] and cell[1].

Options:
  -h, --help  Show this help.

Environment overrides:
  DEMA_REPO     Local DEMA repository. Defaults to /Volumes/Casa/dev/dema-llm.
  RESULTS_DIR   Pipyer results dir used during the smoke run.
  MAX_PAIRS     Candidate-pair cap. Defaults to 16.
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

DEMA_REPO="${DEMA_REPO:-/Volumes/Casa/dev/dema-llm}"
MAX_PAIRS="${MAX_PAIRS:-16}"
ROUTES=(adjudicator_stub)
CONFIDENCES=(0.60 0.70)
ROUTES_JOINED="$(IFS=,; printf "%s" "${ROUTES[*]}")"
CONFIDENCES_JOINED="$(IFS=,; printf "%s" "${CONFIDENCES[*]}")"
START_STAMP="$(date -u +%Y%m%d-%H%M%S)"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PENDING_DIR="$SCRIPT_DIR/.pending-smoke-$START_STAMP"
RESULTS_DIR="${RESULTS_DIR:-$PENDING_DIR/.pipyer-results}"
ARTIFACTS_DIR="$PENDING_DIR/artifacts"
DEMA_OUTPUT_ROOT="$ARTIFACTS_DIR/dema"
INPUTS_DIR="$PENDING_DIR/inputs"
COMMANDS_MD="$PENDING_DIR/commands.md"
TRANSCRIPT_LOG="$PENDING_DIR/transcript.log"
CREATED_BY="runs/dema-adjudication-matrix/smoke-current.sh"
WORKFLOW="$PENDING_DIR/workflows/dema-adjudication-matrix/workflow.yaml"

mkdir -p "$ARTIFACTS_DIR" "$INPUTS_DIR" "$RESULTS_DIR" "$DEMA_OUTPUT_ROOT" || exit 1
if ! copy_repo_evidence; then
  printf "Failed to copy Pipyer repo evidence; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi
if ! copy_dema_evidence; then
  printf "Failed to copy DEMA repo evidence; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi
if ! stage_dema_workflow "$PENDING_DIR"; then
  printf "Failed to stage the DEMA matrix workflow; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

cat > "$COMMANDS_MD" <<EOF
# DEMA Adjudication Matrix Smoke Commands

Generated: $START_ISO

Archive was created by \`$CREATED_BY\`.

## Environment

\`\`\`bash
cd $REPO_ROOT
DEMA_REPO=$DEMA_REPO
RESULTS_DIR=$RESULTS_DIR
DEMA_OUTPUT_ROOT=$DEMA_OUTPUT_ROOT
MAX_PAIRS=$MAX_PAIRS
ROUTES=(${ROUTES[*]})
CONFIDENCES=(${CONFIDENCES[*]})
\`\`\`
EOF

{
  printf "DEMA adjudication matrix smoke transcript\n"
  printf "Generated: %s\n" "$START_ISO"
  printf "Repo: %s\n" "$REPO_ROOT"
  printf "DEMA repo: %s\n" "$DEMA_REPO"
  printf "Workflow: %s\n" "$WORKFLOW"
} > "$TRANSCRIPT_LOG"

run_logged "validate staged DEMA matrix workflow" uv run pipyer validate "$WORKFLOW"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Validation failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

run_logged "zero-spend DEMA matrix smoke run" uv run pipyer run "$WORKFLOW" \
  --input "dema_repo=$DEMA_REPO" \
  --input "output_root=$DEMA_OUTPUT_ROOT" \
  --input "max_pairs=$MAX_PAIRS" \
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

run_logged "compare DEMA smoke cells" uv run pipyer compare "$ARTIFACTS_DIR/run" \
  --results-dir "$RESULTS_DIR" \
  --left-cell-index 0 \
  --right-cell-index 1 \
  --output-dir "$ARTIFACTS_DIR/comparison/cell0-vs-cell1"
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
  printf -- "- DEMA artifacts: \`artifacts/dema\`\n"
  printf -- "- Comparison artifacts: \`artifacts/comparison\`\n"
} >> "$COMMANDS_MD"

mv "$PENDING_DIR" "$FINAL_DIR"
ARCHIVE_DIR="$FINAL_DIR"
ARTIFACT_RUN="$ARCHIVE_DIR/artifacts/run"
write_dema_archive_metadata

printf "\nSmoke archive complete:\n%s\n" "$ARCHIVE_DIR"
