#!/usr/bin/env bash
set -u -o pipefail

usage() {
  cat <<'USAGE'
Usage: runs/gradebot-t2-matrix/run-current.sh [options]

Runs the live GradeBot T2 matrix workflow from the current repo state and
archives the result using the Sprint 03 matrix convention.

Options:
  --yes                    Skip the initial live-spend confirmation.
  --dry-run-only           Validate and dry-run the staged workflow, then stop before live calls.
  --no-dry-run             Skip the dry-run command before the live run.
  --auto-resume            If the live run exits 130, resume automatically.
  --retry-failed-on-resume Add --retry-failed to automatic/manual resumes.
  -h, --help               Show this help.

Environment overrides:
  CORPUS            Archived T2 corpus path.
  RESULTS_DIR       Pipyer results dir used during the run.
  RAW_BASELINE      Raw v2 baseline CSV, relative to CORPUS.
  ANNOTATIONS_FILE  Annotation JSON path.
  BASELINE_MODEL    First matrix cell; default archived v2 model.
  CANDIDATE_MODEL   Second matrix cell; default current Sonnet candidate.
  EXTRA_MODELS      Additional comma-separated model cells.
  MODEL_MATRIX      Full comma-separated matrix override; takes precedence.
  BUDGET_USD        Human-visible budget note in the confirmation prompt.
USAGE
}

split_csv_models() {
  local raw="$1"
  local IFS=,
  local -a parts
  read -r -a parts <<< "$raw"
  local part
  for part in "${parts[@]}"; do
    part="${part#"${part%%[![:space:]]*}"}"
    part="${part%"${part##*[![:space:]]}"}"
    if [[ -n "$part" ]]; then
      MATRIX_MODELS+=("$part")
    fi
  done
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

BASELINE_MODEL="${BASELINE_MODEL:-anthropic:claude-sonnet-4-5-20250929}"
CANDIDATE_MODEL="${CANDIDATE_MODEL:-anthropic:claude-sonnet-4-6}"
MATRIX_MODELS=()
if [[ -n "${MODEL_MATRIX:-}" ]]; then
  split_csv_models "$MODEL_MATRIX"
else
  MATRIX_MODELS=("$BASELINE_MODEL" "$CANDIDATE_MODEL")
  if [[ -n "${EXTRA_MODELS:-}" ]]; then
    split_csv_models "$EXTRA_MODELS"
  fi
fi
if [[ "${#MATRIX_MODELS[@]}" -lt 2 ]]; then
  printf "Matrix must contain at least two model cells.\n" >&2
  exit 2
fi

CORPUS="${CORPUS:-/Volumes/Casa/au/teaching/INSY3010-PySQL/_archive/25-26.Sp/grading/t2}"
RAW_BASELINE="${RAW_BASELINE:-runs/phase1-v2/grading_results_20260402_211734.csv}"
ANNOTATIONS_FILE="${ANNOTATIONS_FILE:-$CORPUS/pipyer-annotations.json}"
BUDGET_USD="${BUDGET_USD:-not enforced by this script}"
START_STAMP="$(date -u +%Y%m%d-%H%M%S)"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PENDING_DIR="$SCRIPT_DIR/.pending-live-$START_STAMP"
RESULTS_DIR="${RESULTS_DIR:-$PENDING_DIR/.pipyer-results}"
ARTIFACTS_DIR="$PENDING_DIR/artifacts"
INPUTS_DIR="$PENDING_DIR/inputs"
COMMANDS_MD="$PENDING_DIR/commands.md"
TRANSCRIPT_LOG="$PENDING_DIR/transcript.log"
CREATED_BY="runs/gradebot-t2-matrix/run-current.sh"
WORKFLOW="$PENDING_DIR/workflows/gradebot-t2-matrix/workflow.yaml"

if [[ "$YES" -ne 1 ]]; then
  if [[ "$DRY_RUN_ONLY" -eq 1 ]]; then
    printf "This will validate and dry-run the live GradeBot T2 matrix workflow, then stop before provider calls.\n"
  else
    printf "This will run live GradeBot T2 matrix LLM grading from the current repo state.\n"
  fi
  printf "Corpus: %s\n" "$CORPUS"
  printf "Results staging dir: %s\n" "$RESULTS_DIR"
  printf "Raw baseline: %s\n" "$RAW_BASELINE"
  printf "Annotations: %s\n" "$ANNOTATIONS_FILE"
  printf "Budget note: %s\n" "$BUDGET_USD"
  printf "Matrix cells:\n"
  for i in "${!MATRIX_MODELS[@]}"; do
    printf "  cell[%s] grader_model=%s\n" "$i" "${MATRIX_MODELS[$i]}"
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

mkdir -p "$ARTIFACTS_DIR" "$INPUTS_DIR" "$RESULTS_DIR" || exit 1
if ! copy_repo_evidence; then
  printf "Failed to copy repo evidence; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi
if ! stage_matrix_workflows "$PENDING_DIR" "${MATRIX_MODELS[@]}"; then
  printf "Failed to stage the live matrix workflow; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

cat > "$COMMANDS_MD" <<EOF
# GradeBot T2 Matrix Run Commands

Generated: $START_ISO

Archive was created by \`$CREATED_BY\`.

## Environment

\`\`\`bash
cd $REPO_ROOT
CORPUS=$CORPUS
RESULTS_DIR=$RESULTS_DIR
RAW_BASELINE=$RAW_BASELINE
ANNOTATIONS_FILE=$ANNOTATIONS_FILE
BUDGET_USD=$BUDGET_USD
MATRIX_MODELS=(${MATRIX_MODELS[*]})
\`\`\`
EOF

{
  printf "GradeBot T2 matrix live run transcript\n"
  printf "Generated: %s\n" "$START_ISO"
  printf "Repo: %s\n" "$REPO_ROOT"
  printf "Workflow: %s\n" "$WORKFLOW"
  printf "Corpus: %s\n" "$CORPUS"
  printf "Matrix cells:\n"
  for i in "${!MATRIX_MODELS[@]}"; do
    printf "  cell[%s] grader_model=%s\n" "$i" "${MATRIX_MODELS[$i]}"
  done
} > "$TRANSCRIPT_LOG"

run_logged "validate staged matrix workflow" uv run pipyer validate "$WORKFLOW"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Validation failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

if [[ "$DO_DRY_RUN" -eq 1 ]]; then
  run_logged "dry-run staged matrix workflow" uv run pipyer run "$WORKFLOW" \
    --dry-run \
    --input "corpus_dir=$CORPUS" \
    --input "raw_baseline_csv=$RAW_BASELINE" \
    --input "annotations_file=$ANNOTATIONS_FILE" \
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
  uv run python - "$FINAL_DIR" "$START_ISO" "$CREATED_BY" "${MATRIX_MODELS[@]}" <<'PY'
import json
import sys
from pathlib import Path

archive = Path(sys.argv[1])
created_at = sys.argv[2]
created_by = sys.argv[3]
models = sys.argv[4:]
manifest = {
    "archive_schema": "pipyer-local-matrix-preflight-v0",
    "created_at": created_at,
    "created_by": created_by,
    "live_run_launched": False,
    "matrix_cells": {
        f"cell[{index}]": {"grader_model": model} for index, model in enumerate(models)
    },
    "retained_artifacts": {
        "commands": "commands.md",
        "transcript": "transcript.log",
        "staged_workflow": "workflows/gradebot-t2-matrix/workflow.yaml",
        "workflow_snapshot": "inputs/current-worktree",
    },
    "current_repo_state": {
        "head": (archive / "inputs/repo/git-head.txt").read_text(encoding="utf-8").strip(),
        "status_short_file": "inputs/repo/git-status-short.txt",
        "diff_stat_file": "inputs/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/repo/git-diff.patch",
        "untracked_file": "inputs/repo/git-untracked.txt",
    },
}
(archive / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(archive / "README.md").write_text(
    f"""# GradeBot T2 Matrix Preflight

Generated {created_at} by `{created_by}`.

This archive records validation and dry-run of the staged live matrix workflow.
No provider calls were launched.

- `commands.md`: exact commands and exit statuses.
- `transcript.log`: captured terminal output.
- `manifest.json`: structured preflight metadata.
- `workflows/`: staged workflow tree used for validation.
- `inputs/`: source workflow and Git-state snapshots.
""",
    encoding="utf-8",
)
PY
  printf "\nDry-run-only preflight complete:\n%s\n" "$FINAL_DIR"
  exit 0
fi

RESUME_ARGS=()
INVOCATION=1
while true; do
  CMD=(uv run pipyer run "$WORKFLOW")
  if [[ "${#RESUME_ARGS[@]}" -gt 0 ]]; then
    CMD+=("${RESUME_ARGS[@]}")
  fi
  CMD+=(
    --input "corpus_dir=$CORPUS"
    --input "raw_baseline_csv=$RAW_BASELINE"
    --input "annotations_file=$ANNOTATIONS_FILE"
    --results-dir "$RESULTS_DIR"
  )

  run_logged "live matrix run invocation $INVOCATION" "${CMD[@]}"

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

mkdir -p "$ARTIFACTS_DIR/comparison"
for i in "${!MATRIX_MODELS[@]}"; do
  if [[ "$i" == "0" ]]; then
    continue
  fi
  run_logged "compare cell 0 vs cell $i" uv run pipyer compare "$ARTIFACTS_DIR/run" \
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
  printf -- "- Comparison artifacts: \`artifacts/comparison\`\n"
} >> "$COMMANDS_MD"

mv "$PENDING_DIR" "$FINAL_DIR"
ARCHIVE_DIR="$FINAL_DIR"
ARTIFACT_RUN="$ARCHIVE_DIR/artifacts/run"
write_run_archive_metadata

printf "\nArchive complete:\n%s\n" "$ARCHIVE_DIR"
printf "Run artifacts:\n%s\n" "$ARTIFACT_RUN"
