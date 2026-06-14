#!/usr/bin/env bash
set -u -o pipefail

usage() {
  cat <<'USAGE'
Usage: runs/dema-adjudication-matrix/run-current.sh [options]

Runs the live DEMA adjudication matrix workflow from the current repo state and
archives the result using the Sprint 03 matrix convention.

Options:
  --yes                    Skip the initial live-spend confirmation.
  --dry-run-only           Validate and dry-run the staged workflow, then stop before live calls.
  --no-dry-run             Skip the dry-run command before the live run.
  --auto-resume            If the live run exits 130, resume automatically.
  --retry-failed-on-resume Add --retry-failed to automatic/manual resumes.
  -h, --help               Show this help.

Environment overrides:
  DEMA_REPO          Local DEMA repository. Defaults to /Volumes/Casa/dev/dema-llm.
  RESULTS_DIR        Pipyer results dir used during the run.
  ROUTE_MATRIX       Comma-separated DEMA adjudicator routes.
  CONFIDENCE_MATRIX  Comma-separated confidence thresholds.
  MAX_PAIRS          Candidate-pair cap. Defaults to 16.
  BUDGET_USD         Human-visible budget note in the confirmation prompt.
  ALLOW_DEMA_DRIFT   Set to 1 to run against a DEMA commit/dirty tree that does
                     not match workflows/dema-adjudication-matrix/dema.lock.json.
USAGE
}

YES=0
DO_DRY_RUN=1
DRY_RUN_ONLY=0
AUTO_RESUME=0
RETRY_FAILED_ON_RESUME=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      YES=1
      shift
      ;;
    --dry-run-only)
      DRY_RUN_ONLY=1
      DO_DRY_RUN=1
      shift
      ;;
    --no-dry-run)
      DO_DRY_RUN=0
      shift
      ;;
    --auto-resume)
      AUTO_RESUME=1
      shift
      ;;
    --retry-failed-on-resume)
      RETRY_FAILED_ON_RESUME=1
      shift
      ;;
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

if [[ "$DRY_RUN_ONLY" -eq 1 ]]; then
  DO_DRY_RUN=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

DEMA_REPO="${DEMA_REPO:-/Volumes/Casa/dev/dema-llm}"
MAX_PAIRS="${MAX_PAIRS:-16}"
BUDGET_USD="${BUDGET_USD:-not enforced by this script}"
ROUTES=()
CONFIDENCES=()
split_csv_routes "${ROUTE_MATRIX:-adjudicator_openai,adjudicator_claude}"
split_csv_confidences "${CONFIDENCE_MATRIX:-0.60,0.70}"
if [[ "${#ROUTES[@]}" -lt 1 ]]; then
  printf "Route matrix must contain at least one DEMA route.\n" >&2
  exit 2
fi
if [[ "${#CONFIDENCES[@]}" -lt 1 ]]; then
  printf "Confidence matrix must contain at least one threshold.\n" >&2
  exit 2
fi
ROUTES_JOINED="$(IFS=,; printf "%s" "${ROUTES[*]}")"
CONFIDENCES_JOINED="$(IFS=,; printf "%s" "${CONFIDENCES[*]}")"
START_STAMP="$(date -u +%Y%m%d-%H%M%S)"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PENDING_DIR="$SCRIPT_DIR/.pending-live-$START_STAMP"
RESULTS_DIR="${RESULTS_DIR:-$PENDING_DIR/.pipyer-results}"
ARTIFACTS_DIR="$PENDING_DIR/artifacts"
DEMA_OUTPUT_ROOT="$ARTIFACTS_DIR/dema"
INPUTS_DIR="$PENDING_DIR/inputs"
COMMANDS_MD="$PENDING_DIR/commands.md"
TRANSCRIPT_LOG="$PENDING_DIR/transcript.log"
CREATED_BY="runs/dema-adjudication-matrix/run-current.sh"
WORKFLOW="$PENDING_DIR/workflows/dema-adjudication-matrix/workflow.yaml"

if [[ "$YES" -ne 1 ]]; then
  if [[ "$DRY_RUN_ONLY" -eq 1 ]]; then
    printf "This will validate and dry-run the live DEMA matrix workflow, then stop before provider calls.\n"
  else
    printf "This will run live DEMA matrix adjudication from the current repo state.\n"
  fi
  printf "DEMA repo: %s\n" "$DEMA_REPO"
  printf "Results staging dir: %s\n" "$RESULTS_DIR"
  printf "DEMA output root: %s\n" "$DEMA_OUTPUT_ROOT"
  printf "Max pairs: %s\n" "$MAX_PAIRS"
  printf "Budget note: %s\n" "$BUDGET_USD"
  printf "Matrix cells:\n"
  cell=0
  for route in "${ROUTES[@]}"; do
    for confidence in "${CONFIDENCES[@]}"; do
      printf "  cell[%s] adjudicator_route=%s confidence_threshold=%s\n" "$cell" "$route" "$confidence"
      cell=$((cell + 1))
    done
  done
  if [[ "$DRY_RUN_ONLY" -eq 1 ]]; then
    CONFIRM_PROMPT="Continue with dry-run-only preflight"
  else
    CONFIRM_PROMPT="Continue"
  fi
  if ! confirm "$CONFIRM_PROMPT"; then
    exit 130
  fi
fi

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
  printf "Failed to stage the live DEMA matrix workflow; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

cat > "$COMMANDS_MD" <<EOF
# DEMA Adjudication Matrix Run Commands

Generated: $START_ISO

Archive was created by \`$CREATED_BY\`.

## Environment

\`\`\`bash
cd $REPO_ROOT
DEMA_REPO=$DEMA_REPO
RESULTS_DIR=$RESULTS_DIR
DEMA_OUTPUT_ROOT=$DEMA_OUTPUT_ROOT
MAX_PAIRS=$MAX_PAIRS
BUDGET_USD=$BUDGET_USD
ALLOW_DEMA_DRIFT=${ALLOW_DEMA_DRIFT:-0}
ROUTES=(${ROUTES[*]})
CONFIDENCES=(${CONFIDENCES[*]})
\`\`\`
EOF

{
  printf "DEMA adjudication matrix live run transcript\n"
  printf "Generated: %s\n" "$START_ISO"
  printf "Repo: %s\n" "$REPO_ROOT"
  printf "DEMA repo: %s\n" "$DEMA_REPO"
  printf "Workflow: %s\n" "$WORKFLOW"
  printf "Matrix cells:\n"
  cell=0
  for route in "${ROUTES[@]}"; do
    for confidence in "${CONFIDENCES[@]}"; do
      printf "  cell[%s] adjudicator_route=%s confidence_threshold=%s\n" "$cell" "$route" "$confidence"
      cell=$((cell + 1))
    done
  done
} > "$TRANSCRIPT_LOG"

{
  printf "\n## DEMA Lock Check\n\n"
  printf -- "- Lock file: \`workflows/dema-adjudication-matrix/dema.lock.json\`\n"
  printf -- "- DEMA repo: \`%s\`\n" "$DEMA_REPO"
  printf -- "- ALLOW_DEMA_DRIFT: \`%s\`\n" "${ALLOW_DEMA_DRIFT:-0}"
} >> "$COMMANDS_MD"
if ! check_dema_lock 2>&1 | tee -a "$TRANSCRIPT_LOG"; then
  printf "DEMA lock check failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 2
fi

run_logged "validate staged DEMA matrix workflow" uv run pipyer validate "$WORKFLOW"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Validation failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

if [[ "$DO_DRY_RUN" -eq 1 ]]; then
  run_logged "dry-run staged DEMA matrix workflow" uv run pipyer run "$WORKFLOW" \
    --dry-run \
    --input "dema_repo=$DEMA_REPO" \
    --input "output_root=$DEMA_OUTPUT_ROOT" \
    --input "max_pairs=$MAX_PAIRS" \
    --results-dir "$RESULTS_DIR"
  if [[ "$LAST_STATUS" -ne 0 ]]; then
    printf "Dry-run failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
    exit "$LAST_STATUS"
  fi
fi

if [[ "$DRY_RUN_ONLY" -eq 1 ]]; then
  FINAL_DIR="$SCRIPT_DIR/preflight-$START_STAMP"
  if [[ -e "$FINAL_DIR" ]]; then
    FINAL_DIR="$SCRIPT_DIR/preflight-$START_STAMP-2"
  fi
  {
    printf "\n## Archive Finalization\n\n"
    printf -- "- Final preflight archive: \`%s\`\n" "$FINAL_DIR"
    printf -- "- Live run was not launched.\n"
  } >> "$COMMANDS_MD"
  mv "$PENDING_DIR" "$FINAL_DIR"
  uv run python - "$FINAL_DIR" "$START_ISO" "$CREATED_BY" "$ROUTES_JOINED" "$CONFIDENCES_JOINED" <<'PY'
import json
import sys
from pathlib import Path

archive = Path(sys.argv[1])
created_at = sys.argv[2]
created_by = sys.argv[3]
routes = [part for part in sys.argv[4].split(",") if part]
confidences = [float(part) for part in sys.argv[5].split(",") if part]
cells = {}
index = 0
for route in routes:
    for confidence in confidences:
        cells[f"cell[{index}]"] = {
            "adjudicator_route": route,
            "confidence_threshold": confidence,
        }
        index += 1
manifest = {
    "archive_schema": "pipyer-dema-matrix-preflight-v0",
    "created_at": created_at,
    "created_by": created_by,
    "live_run_launched": False,
    "matrix_cells": cells,
    "retained_artifacts": {
        "commands": "commands.md",
        "transcript": "transcript.log",
        "staged_workflow": "workflows/dema-adjudication-matrix/workflow.yaml",
        "workflow_snapshot": "inputs/current-worktree/dema-adjudication-matrix",
    },
    "current_repo_state": {
        "head": (archive / "inputs/repo/git-head.txt").read_text(encoding="utf-8").strip(),
        "status_short_file": "inputs/repo/git-status-short.txt",
        "diff_stat_file": "inputs/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/repo/git-diff.patch",
        "untracked_file": "inputs/repo/git-untracked.txt",
    },
    "dema_repo_state": {
        "head": (archive / "inputs/dema/repo/git-head.txt").read_text(encoding="utf-8").strip(),
        "status_short_file": "inputs/dema/repo/git-status-short.txt",
        "diff_stat_file": "inputs/dema/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/dema/repo/git-diff.patch",
        "untracked_file": "inputs/dema/repo/git-untracked.txt",
        "router": "inputs/dema/repo/router.yaml",
        "data": "inputs/dema/data",
    },
}
lock_path = archive / "inputs/current-worktree/dema-adjudication-matrix/dema.lock.json"
if lock_path.exists():
    try:
        manifest["dema_lock"] = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        manifest["dema_lock"] = {"path": "inputs/current-worktree/dema-adjudication-matrix/dema.lock.json"}
(archive / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(archive / "README.md").write_text(
    f"""# DEMA Adjudication Matrix Preflight

Generated {created_at} by `{created_by}`.

This archive records validation and dry-run of the staged live matrix workflow.
No provider calls were launched.

- `commands.md`: exact commands and exit statuses.
- `transcript.log`: captured terminal output.
- `manifest.json`: structured preflight metadata.
- `workflows/`: staged workflow tree used for validation.
- `inputs/`: source workflow, Pipyer Git state, and DEMA snapshots.
""",
    encoding="utf-8",
)
PY
  printf "\nDry-run-only preflight complete:\n%s\n" "$FINAL_DIR"
  exit 0
fi

{
  printf "\n## Provider Credential Check\n\n"
  printf -- "- Routes: \`%s\`\n" "$ROUTES_JOINED"
} >> "$COMMANDS_MD"
if ! check_provider_env 2>&1 | tee -a "$TRANSCRIPT_LOG"; then
  printf "Provider credential check failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 2
fi

RESUME_ARGS=()
INVOCATION=1
while true; do
  CMD=(uv run pipyer run "$WORKFLOW")
  if [[ "${#RESUME_ARGS[@]}" -gt 0 ]]; then
    CMD+=("${RESUME_ARGS[@]}")
  fi
  CMD+=(
    --input "dema_repo=$DEMA_REPO"
    --input "output_root=$DEMA_OUTPUT_ROOT"
    --input "max_pairs=$MAX_PAIRS"
    --results-dir "$RESULTS_DIR"
  )

  run_logged "live DEMA matrix run invocation $INVOCATION" "${CMD[@]}"

  CURRENT_RUN_DIR="$(latest_run_dir)"
  RUN_RECORD_STATUS="$(run_record_status "$CURRENT_RUN_DIR" 2>/dev/null || true)"
  if [[ -n "$RUN_RECORD_STATUS" ]]; then
    printf "Run record status: %s\n" "$RUN_RECORD_STATUS" | tee -a "$TRANSCRIPT_LOG"
    printf "Run record status: %s\n" "$RUN_RECORD_STATUS" >> "$COMMANDS_MD"
  fi

  if [[ "$RUN_RECORD_STATUS" == "interrupted" ]]; then
    if [[ "$AUTO_RESUME" -eq 1 ]] || confirm "Run was interrupted. Resume now"; then
      RESUME_ARGS=(--resume last)
      if [[ "$RETRY_FAILED_ON_RESUME" -eq 1 ]]; then
        RESUME_ARGS+=(--retry-failed)
      fi
      INVOCATION=$((INVOCATION + 1))
      continue
    fi
    break
  fi

  case "$LAST_STATUS" in
    0|1)
      break
      ;;
    130)
      if [[ "$AUTO_RESUME" -eq 1 ]] || confirm "Run was interrupted. Resume now"; then
        RESUME_ARGS=(--resume last)
        if [[ "$RETRY_FAILED_ON_RESUME" -eq 1 ]]; then
          RESUME_ARGS+=(--retry-failed)
        fi
        INVOCATION=$((INVOCATION + 1))
        continue
      fi
      break
      ;;
    *)
      printf "Run exited with status %s; partial archive remains at %s\n" "$LAST_STATUS" "$PENDING_DIR" >&2
      break
      ;;
  esac
done

RUN_DIR="$(latest_run_dir)"
if [[ -z "$RUN_DIR" || ! -f "$RUN_DIR/run.json" ]]; then
  printf "No completed Pipyer run directory found under %s\n" "$RESULTS_DIR" >&2
  printf "Partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

RUN_RECORD_STATUS="$(run_record_status "$RUN_DIR" 2>/dev/null || true)"
if [[ "$RUN_RECORD_STATUS" == "interrupted" ]]; then
  printf "Run remains interrupted; partial archive remains at %s\n" "$PENDING_DIR" >&2
  printf "Resume with the same staged workflow and results dir, or remove the pending directory if it is disposable.\n" >&2
  exit 130
fi

mv "$RUN_DIR" "$ARTIFACTS_DIR/run"
rmdir "$RESULTS_DIR" 2>/dev/null || true

CELL_COUNT=$(("${#ROUTES[@]}" * "${#CONFIDENCES[@]}"))
mkdir -p "$ARTIFACTS_DIR/comparison"
for ((i = 1; i < CELL_COUNT; i++)); do
  run_logged "compare DEMA cell 0 vs cell $i" uv run pipyer compare "$ARTIFACTS_DIR/run" \
    --results-dir "$RESULTS_DIR" \
    --left-cell-index 0 \
    --right-cell-index "$i" \
    --output-dir "$ARTIFACTS_DIR/comparison/cell0-vs-cell$i"
  if [[ "$LAST_STATUS" -ne 0 ]]; then
    printf "Cell comparison failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
    exit "$LAST_STATUS"
  fi
done

RUN_ID="$(run_record_id "$ARTIFACTS_DIR/run")"
FINAL_DIR="$SCRIPT_DIR/$RUN_ID"
if [[ -e "$FINAL_DIR" ]]; then
  FINAL_DIR="$SCRIPT_DIR/$RUN_ID-$START_STAMP"
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

printf "\nArchive complete:\n%s\n" "$ARCHIVE_DIR"
printf "Run artifacts:\n%s\n" "$ARTIFACT_RUN"
