#!/usr/bin/env bash
set -u -o pipefail

usage() {
  cat <<'USAGE'
Usage: runs/gradebot-t2-matrix/compare-existing.sh [options]

Creates a zero-spend comparison archive from two existing Pipyer run directories.

Options:
  -h, --help  Show this help.

Environment overrides:
  LEFT_RUN     Left run directory. Defaults to the first retained GradeBot T2 archive.
  RIGHT_RUN    Right run directory. Defaults to the later retained GradeBot T2 archive.
  STABILITY    1 marks the comparison as a stability comparison; default 1.
  PRINT_JSON   1 also prints comparison JSON to stdout/transcript; default 0.
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
PENDING_DIR="$SCRIPT_DIR/.pending-compare-$START_STAMP"
ARTIFACTS_DIR="$PENDING_DIR/artifacts"
INPUTS_DIR="$PENDING_DIR/inputs"
COMMANDS_MD="$PENDING_DIR/commands.md"
TRANSCRIPT_LOG="$PENDING_DIR/transcript.log"
CREATED_BY="runs/gradebot-t2-matrix/compare-existing.sh"

LEFT_RUN="${LEFT_RUN:-$REPO_ROOT/runs/gradebot-t2/20260611-210517-6a8fb0/artifacts/run}"
RIGHT_RUN="${RIGHT_RUN:-$REPO_ROOT/runs/gradebot-t2/20260613-123418-6a8fb0/artifacts/run}"
STABILITY="${STABILITY:-1}"
PRINT_JSON="${PRINT_JSON:-0}"

if [[ ! -f "$LEFT_RUN/events.jsonl" ]]; then
  printf "Left run not found: %s\n" "$LEFT_RUN" >&2
  exit 2
fi
if [[ ! -f "$RIGHT_RUN/events.jsonl" ]]; then
  printf "Right run not found: %s\n" "$RIGHT_RUN" >&2
  exit 2
fi

mkdir -p "$ARTIFACTS_DIR/comparison" "$INPUTS_DIR" || exit 1
if ! copy_repo_evidence; then
  printf "Failed to copy repo evidence; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit 1
fi

cat > "$COMMANDS_MD" <<EOF
# GradeBot T2 Existing-Run Comparison Commands

Generated: $START_ISO

Archive was created by \`$CREATED_BY\`.

## Environment

\`\`\`bash
cd $REPO_ROOT
LEFT_RUN=$LEFT_RUN
RIGHT_RUN=$RIGHT_RUN
STABILITY=$STABILITY
PRINT_JSON=$PRINT_JSON
\`\`\`
EOF

{
  printf "GradeBot T2 existing-run comparison transcript\n"
  printf "Generated: %s\n" "$START_ISO"
  printf "Repo: %s\n" "$REPO_ROOT"
  printf "Left: %s\n" "$LEFT_RUN"
  printf "Right: %s\n" "$RIGHT_RUN"
} > "$TRANSCRIPT_LOG"

COMPARE_CMD=(uv run pipyer compare "$LEFT_RUN" "$RIGHT_RUN" --results-dir "$REPO_ROOT/runs" --output-dir "$ARTIFACTS_DIR/comparison")
if [[ "$STABILITY" == "1" ]]; then
  COMPARE_CMD+=(--stability)
fi
if [[ "$PRINT_JSON" == "1" ]]; then
  COMPARE_CMD+=(--json)
fi

run_logged "compare retained GradeBot T2 runs" "${COMPARE_CMD[@]}"
if [[ "$LAST_STATUS" -ne 0 ]]; then
  printf "Comparison failed; partial archive remains at %s\n" "$PENDING_DIR" >&2
  exit "$LAST_STATUS"
fi

LEFT_ID="$(run_record_id "$LEFT_RUN")"
RIGHT_ID="$(run_record_id "$RIGHT_RUN")"
FINAL_DIR="$SCRIPT_DIR/compare-$LEFT_ID-vs-$RIGHT_ID-$START_STAMP"
if [[ -e "$FINAL_DIR" ]]; then
  FINAL_DIR="$SCRIPT_DIR/compare-$LEFT_ID-vs-$RIGHT_ID-$START_STAMP-2"
fi

{
  printf "\n## Archive Finalization\n\n"
  printf -- "- Final archive: \`%s\`\n" "$FINAL_DIR"
  printf -- "- Comparison artifacts: \`artifacts/comparison\`\n"
} >> "$COMMANDS_MD"

mv "$PENDING_DIR" "$FINAL_DIR"
ARCHIVE_DIR="$FINAL_DIR"

uv run python - "$ARCHIVE_DIR" "$START_ISO" "$CREATED_BY" "$LEFT_RUN" "$RIGHT_RUN" <<'PY'
import json
import sys
from pathlib import Path

archive = Path(sys.argv[1])
created_at = sys.argv[2]
created_by = sys.argv[3]
left_run = sys.argv[4]
right_run = sys.argv[5]
comparison_path = archive / "artifacts/comparison/comparison.json"
record = json.loads(comparison_path.read_text(encoding="utf-8"))

manifest = {
    "archive_schema": "pipyer-local-comparison-archive-v0",
    "created_at": created_at,
    "created_by": created_by,
    "left_run": left_run,
    "right_run": right_run,
    "comparison": {
        "json": "artifacts/comparison/comparison.json",
        "markdown": "artifacts/comparison/comparison.md",
        "mode": record.get("mode"),
        "left": record.get("left"),
        "right": record.get("right"),
        "units": record.get("units"),
        "summaries": record.get("summaries"),
        "cost": record.get("cost"),
    },
    "current_repo_state": {
        "head": (archive / "inputs/repo/git-head.txt").read_text(encoding="utf-8").strip(),
        "status_short_file": "inputs/repo/git-status-short.txt",
        "diff_stat_file": "inputs/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/repo/git-diff.patch",
        "untracked_file": "inputs/repo/git-untracked.txt",
    },
    "privacy": {
        "gitignored": True,
        "may_contain_closed_course_outputs": True,
    },
}
(archive / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

readme = f"""# GradeBot T2 Comparison

Generated {created_at} by `{created_by}`.

## Compared Runs

- Left: `{left_run}`
- Right: `{right_run}`
- Mode: `{record.get('mode')}`

## Results

- Same units: `{record.get('units', {}).get('same')}`
- Different units: `{record.get('units', {}).get('different')}`
- Only left: `{len(record.get('units', {}).get('only_left') or [])}`
- Only right: `{len(record.get('units', {}).get('only_right') or [])}`

Artifacts:

- `artifacts/comparison/comparison.md`
- `artifacts/comparison/comparison.json`
- `commands.md`
- `transcript.log`
- `manifest.json`
"""
(archive / "README.md").write_text(readme, encoding="utf-8")
PY

printf "\nComparison archive complete:\n%s\n" "$ARCHIVE_DIR"
