#!/usr/bin/env bash
set -u -o pipefail

usage() {
  cat <<'USAGE'
Usage: runs/gradebot-t2/run-current.sh [options]

Runs the GradeBot T2 workflow from the current repo state and archives the
result using the local convention:

  runs/gradebot-t2/<run-id>/
    README.md
    commands.md
    manifest.json
    inputs/
    artifacts/run/

Options:
  --yes                    Skip the initial live-spend confirmation.
  --no-dry-run             Skip the dry-run command before the live run.
  --auto-resume            If the live run exits 130, resume automatically.
  --retry-failed-on-resume Add --retry-failed to automatic/manual resumes.
  -h, --help               Show this help.

Environment overrides:
  CORPUS            Archived T2 corpus path.
  RESULTS_DIR       Pipyer results dir used during the run.
  RAW_BASELINE      Raw v2 baseline CSV, relative to CORPUS.
  ANNOTATIONS_FILE  Annotation JSON path.

Default paths match the Sprint 02 acceptance baseline.
USAGE
}

confirm() {
  local prompt="$1"
  local answer
  printf "%s [y/N] " "$prompt"
  read -r answer
  case "$answer" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

quote_cmd() {
  local part
  for part in "$@"; do
    printf "%q " "$part"
  done
}

run_logged() {
  local title="$1"
  shift

  {
    printf "\n## %s\n\n" "$title"
    printf '```bash\n'
    quote_cmd "$@"
    printf '\n```\n\n'
  } >> "$COMMANDS_MD"

  printf "\n>>> %s\n" "$title" | tee -a "$TRANSCRIPT_LOG"
  printf "+ " | tee -a "$TRANSCRIPT_LOG"
  quote_cmd "$@" | tee -a "$TRANSCRIPT_LOG"
  printf "\n" | tee -a "$TRANSCRIPT_LOG"

  "$@" 2>&1 | tee -a "$TRANSCRIPT_LOG"
  LAST_STATUS=${PIPESTATUS[0]}

  {
    printf "Exit status: %s\n" "$LAST_STATUS"
  } >> "$COMMANDS_MD"
}

copy_if_present() {
  local src="$1"
  local dst="$2"
  if [[ -e "$src" ]]; then
    cp "$src" "$dst"
  fi
}

latest_run_dir() {
  find "$RESULTS_DIR" -mindepth 1 -maxdepth 1 -type d | sort | tail -1
}

run_record_status() {
  local run_dir="$1"
  if [[ -z "$run_dir" || ! -f "$run_dir/run.json" ]]; then
    return 1
  fi
  uv run python - "$run_dir/run.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text()).get("status", ""))
PY
}

YES=0
DO_DRY_RUN=1
AUTO_RESUME=0
RETRY_FAILED_ON_RESUME=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      YES=1
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

WORKFLOW="workflows/gradebot-t2/workflow.yaml"
CORPUS="${CORPUS:-/Volumes/Casa/au/teaching/INSY3010-PySQL/_archive/25-26.Sp/grading/t2}"
RAW_BASELINE="${RAW_BASELINE:-runs/phase1-v2/grading_results_20260402_211734.csv}"
ANNOTATIONS_FILE="${ANNOTATIONS_FILE:-$CORPUS/pipyer-annotations.json}"
START_STAMP="$(date -u +%Y%m%d-%H%M%S)"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PENDING_DIR="$SCRIPT_DIR/.pending-$START_STAMP"
RESULTS_DIR="${RESULTS_DIR:-$PENDING_DIR/.pipyer-results}"
ARTIFACTS_DIR="$PENDING_DIR/artifacts"
INPUTS_DIR="$PENDING_DIR/inputs"
COMMANDS_MD="$PENDING_DIR/commands.md"
TRANSCRIPT_LOG="$PENDING_DIR/transcript.log"

if [[ ! -f "$WORKFLOW" ]]; then
  printf "Workflow not found: %s\n" "$WORKFLOW" >&2
  exit 2
fi

if [[ "$YES" -ne 1 ]]; then
  printf "This will run live GradeBot T2 LLM grading from the current repo state.\n"
  printf "Corpus: %s\n" "$CORPUS"
  printf "Results staging dir: %s\n" "$RESULTS_DIR"
  printf "Raw baseline: %s\n" "$RAW_BASELINE"
  printf "Annotations: %s\n" "$ANNOTATIONS_FILE"
  if ! confirm "Continue"; then
    exit 130
  fi
fi

mkdir -p "$ARTIFACTS_DIR" "$INPUTS_DIR/current-worktree" "$INPUTS_DIR/repo" "$INPUTS_DIR/source-docs" "$INPUTS_DIR/workflow-snapshots" "$RESULTS_DIR"

cat > "$COMMANDS_MD" <<EOF
# GradeBot T2 Run Commands

Generated: $START_ISO

Archive was created by \`runs/gradebot-t2/run-current.sh\`.

## Environment

\`\`\`bash
cd $REPO_ROOT
CORPUS=$CORPUS
RESULTS_DIR=$RESULTS_DIR
RAW_BASELINE=$RAW_BASELINE
ANNOTATIONS_FILE=$ANNOTATIONS_FILE
\`\`\`
EOF

{
  printf "GradeBot T2 run transcript\n"
  printf "Generated: %s\n" "$START_ISO"
  printf "Repo: %s\n" "$REPO_ROOT"
  printf "Workflow: %s\n" "$WORKFLOW"
} > "$TRANSCRIPT_LOG"

cp -R workflows/gradebot-t2/. "$INPUTS_DIR/current-worktree"
git rev-parse HEAD > "$INPUTS_DIR/repo/git-head.txt"
git status --short > "$INPUTS_DIR/repo/git-status-short.txt"
git diff --stat > "$INPUTS_DIR/repo/git-diff-stat.txt"
git diff --binary > "$INPUTS_DIR/repo/git-diff.patch"
git ls-files --others --exclude-standard > "$INPUTS_DIR/repo/git-untracked.txt"
copy_if_present pyproject.toml "$INPUTS_DIR/repo/pyproject.toml"
copy_if_present uv.lock "$INPUTS_DIR/repo/uv.lock"
copy_if_present README.md "$INPUTS_DIR/repo/README.md"
copy_if_present specs/002-workflow-runner/acceptance-evidence.md "$INPUTS_DIR/source-docs/acceptance-evidence.md"
copy_if_present specs/002-workflow-runner/quickstart.md "$INPUTS_DIR/source-docs/quickstart.md"
copy_if_present specs/002-workflow-runner/exit-notes.md "$INPUTS_DIR/source-docs/exit-notes.md"
copy_if_present specs/002-workflow-runner/tasks.md "$INPUTS_DIR/source-docs/tasks.md"

HEAD_COMMIT="$(cat "$INPUTS_DIR/repo/git-head.txt")"
if git cat-file -e "$HEAD_COMMIT^{commit}" 2>/dev/null; then
  SNAPSHOT_DIR="$INPUTS_DIR/workflow-snapshots/${HEAD_COMMIT:0:8}"
  mkdir -p "$SNAPSHOT_DIR"
  git archive --format=tar "$HEAD_COMMIT" workflows/gradebot-t2 | tar -x -C "$SNAPSHOT_DIR" --strip-components=2
fi

run_logged "validate workflow" uv run pipyer validate "$WORKFLOW"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Validation failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

if [[ "$DO_DRY_RUN" -eq 1 ]]; then
  run_logged "dry-run workflow" uv run pipyer run "$WORKFLOW" \
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

  run_logged "live run invocation $INVOCATION" "${CMD[@]}"

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

mv "$RUN_DIR" "$ARTIFACTS_DIR/run"
rmdir "$RESULTS_DIR" 2>/dev/null || true

RUN_ID="$(uv run python - "$ARTIFACTS_DIR/run/run.json" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text()).get("run_id", "unknown-run-id"))
PY
)"

FINAL_DIR="$SCRIPT_DIR/$RUN_ID"
if [[ -e "$FINAL_DIR" ]]; then
  FINAL_DIR="$SCRIPT_DIR/$RUN_ID-$START_STAMP"
fi

mv "$PENDING_DIR" "$FINAL_DIR"
ARCHIVE_DIR="$FINAL_DIR"
ARTIFACT_RUN="$ARCHIVE_DIR/artifacts/run"
COMMANDS_MD="$ARCHIVE_DIR/commands.md"
TRANSCRIPT_LOG="$ARCHIVE_DIR/transcript.log"

{
  printf "\n## Archive Finalization\n\n"
  printf -- "- Final archive: \`%s\`\n" "$ARCHIVE_DIR"
  printf -- "- Pipyer run directory: \`artifacts/run\`\n"
} >> "$COMMANDS_MD"

export ARCHIVE_DIR ARTIFACT_RUN START_ISO WORKFLOW CORPUS RAW_BASELINE ANNOTATIONS_FILE RESULTS_DIR REPO_ROOT
uv run python <<'PY'
import json
import os
from collections import Counter
from pathlib import Path

archive = Path(os.environ["ARCHIVE_DIR"])
run_dir = Path(os.environ["ARTIFACT_RUN"])
run_record = json.loads((run_dir / "run.json").read_text())
events = []
with (run_dir / "events.jsonl").open() as handle:
    for line in handle:
        line = line.strip()
        if line:
            events.append(json.loads(line))

counts = Counter(event["event"] for event in events)
started = [event for event in events if event["event"] == "run_started"]
resumed = [event for event in events if event["event"] == "run_resumed"]
finished = [event for event in events if event["event"] == "run_finished"]
outputs_dir = run_dir / "outputs"
output_files = [path for path in outputs_dir.rglob("*") if path.is_file()] if outputs_dir.exists() else []
comparison_files = [path for path in (outputs_dir / "comparison").glob("*") if path.is_file()] if (outputs_dir / "comparison").exists() else []
feedback_files = [path for path in (outputs_dir / "feedback").glob("*.md") if path.is_file()] if (outputs_dir / "feedback").exists() else []
summary_agreement = run_record.get("totals", {}).get("outputs", {}).get("summary_agreement")
declared_output_paths = {}
for name, value in run_record.get("totals", {}).get("outputs", {}).items():
    if not isinstance(value, str):
        continue
    marker = f"/{run_record.get('run_id')}/"
    archive_relative = None
    if marker in value:
        archive_relative = Path("artifacts/run") / value.split(marker, 1)[1]
    elif value.startswith("outputs/"):
        archive_relative = Path("artifacts/run") / value

    if archive_relative is None:
        declared_output_paths[name] = {
            "recorded": value,
            "archive_relative": None,
            "exists": False,
        }
        continue

    declared_output_paths[name] = {
        "recorded": value,
        "archive_relative": archive_relative.as_posix(),
        "exists": (archive / archive_relative).exists(),
    }

manifest = {
    "archive_schema": "pipyer-local-run-archive-v0",
    "created_at": os.environ["START_ISO"],
    "created_by": "runs/gradebot-t2/run-current.sh",
    "workflow_name": run_record.get("workflow_name"),
    "run_id": run_record.get("run_id"),
    "workflow_hash": run_record.get("workflow_hash"),
    "local_run_dir": "artifacts/run",
    "privacy": {
        "gitignored": True,
        "contains_closed_course_outputs": True,
    },
    "retained_artifacts": {
        "event_log": "artifacts/run/events.jsonl",
        "run_record": "artifacts/run/run.json",
        "checkpoint": "artifacts/run/checkpoint.json",
        "summary": "artifacts/run/summary.md",
        "outputs": "artifacts/run/outputs",
        "comparison_files": len(comparison_files),
        "feedback_markdown_files": len(feedback_files),
        "total_output_files": len(output_files),
        "transcript": "transcript.log",
        "commands": "commands.md",
    },
    "current_repo_state": {
        "head": (archive / "inputs/repo/git-head.txt").read_text().strip(),
        "status_short_file": "inputs/repo/git-status-short.txt",
        "diff_stat_file": "inputs/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/repo/git-diff.patch",
        "untracked_file": "inputs/repo/git-untracked.txt",
        "workflow_snapshot": "inputs/current-worktree",
    },
    "input_config": {
        "workflow": os.environ["WORKFLOW"],
        "corpus_dir": os.environ["CORPUS"],
        "raw_baseline_csv": os.environ["RAW_BASELINE"],
        "annotations_file": os.environ["ANNOTATIONS_FILE"],
        "results_dir_used_during_run": os.environ["RESULTS_DIR"],
        "config_snapshot": run_record.get("config_snapshot"),
    },
    "event_counts": dict(sorted(counts.items())),
    "logical_run_window": {
        "started_at": started[0].get("started_at") if started else None,
        "finished_at": finished[-1].get("finished_at") if finished else None,
    },
    "invocations": [
        {
            "started_at": start.get("started_at"),
            "git_commit": start.get("git_commit"),
            "config_hash": start.get("config_snapshot", {}).get("config_hash"),
            "results_dir": start.get("config_snapshot", {}).get("results_dir"),
        }
        for start in started
    ],
    "resumes": [
        {
            "at": event.get("at"),
            "resumed_from_status": event.get("resumed_from_status"),
            "failed_not_retried": len(event.get("failed_not_retried", [])),
            "failed_retried": len(event.get("failed_retried", [])),
            "lock_reclaimed": event.get("lock_reclaimed"),
        }
        for event in resumed
    ],
    "final_summary": {
        "status": run_record.get("status"),
        "totals": run_record.get("totals"),
        "summary_agreement": summary_agreement,
    },
    "declared_output_paths": declared_output_paths,
}

(archive / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

readme = f"""# GradeBot T2 Run {run_record.get('run_id')}

Generated {os.environ['START_ISO']} by `runs/gradebot-t2/run-current.sh`.

## Status

- Workflow: `{run_record.get('workflow_name')}`
- Workflow hash: `{run_record.get('workflow_hash')}`
- Final status: `{run_record.get('status')}`
- Started: `{manifest['logical_run_window']['started_at']}`
- Finished: `{manifest['logical_run_window']['finished_at']}`
- Event counts: `{dict(sorted(counts.items()))}`
- Output files: `{len(output_files)}`

## Contents

- `artifacts/run/`: raw Pipyer run directory.
- `commands.md`: exact commands launched by this script and exit statuses.
- `transcript.log`: captured terminal output from validation, dry-run, and run commands.
- `manifest.json`: structured summary of the archive.
- `inputs/current-worktree/`: workflow tree copied before the run.
- `inputs/repo/`: Git head, status, diff stat, and patch for the current repo state.
- `inputs/source-docs/`: Feature 002 source docs copied as context.

## Declared Output Paths

The raw Pipyer run record is preserved unchanged in `artifacts/run/`. File
outputs recorded there may still point at the temporary staging directory used
during execution. Archive-stable paths are recorded in `manifest.json` under
`declared_output_paths`.

## Notes

This archive is local and gitignored. It may contain closed-course outputs and
student identifiers through retained run artifacts.
"""
(archive / "README.md").write_text(readme)
PY

printf "\nArchive complete:\n%s\n" "$ARCHIVE_DIR"
printf "Run artifacts:\n%s\n" "$ARTIFACT_RUN"
