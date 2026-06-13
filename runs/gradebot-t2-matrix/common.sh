#!/usr/bin/env bash

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

  printf "Exit status: %s\n" "$LAST_STATUS" >> "$COMMANDS_MD"
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

run_record_id() {
  local run_dir="$1"
  uv run python - "$run_dir/run.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text()).get("run_id", "unknown-run-id"))
PY
}

copy_repo_evidence() {
  mkdir -p "$INPUTS_DIR/current-worktree" "$INPUTS_DIR/repo" "$INPUTS_DIR/source-docs"
  cp -R workflows/gradebot-t2 "$INPUTS_DIR/current-worktree/gradebot-t2"
  cp -R workflows/gradebot-t2-matrix "$INPUTS_DIR/current-worktree/gradebot-t2-matrix"
  git rev-parse HEAD > "$INPUTS_DIR/repo/git-head.txt"
  git status --short > "$INPUTS_DIR/repo/git-status-short.txt"
  git diff --stat > "$INPUTS_DIR/repo/git-diff-stat.txt"
  git diff --binary > "$INPUTS_DIR/repo/git-diff.patch"
  git ls-files --others --exclude-standard > "$INPUTS_DIR/repo/git-untracked.txt"
  copy_if_present pyproject.toml "$INPUTS_DIR/repo/pyproject.toml"
  copy_if_present uv.lock "$INPUTS_DIR/repo/uv.lock"
  copy_if_present README.md "$INPUTS_DIR/repo/README.md"
  copy_if_present docs/sprint-03/BRIEF.md "$INPUTS_DIR/source-docs/sprint-03-brief.md"
  copy_if_present docs/sprint-02/BRIEF.md "$INPUTS_DIR/source-docs/sprint-02-brief.md"
  copy_if_present specs/002-workflow-runner/acceptance-evidence.md "$INPUTS_DIR/source-docs/feature-002-acceptance-evidence.md"
  copy_if_present specs/002-workflow-runner/exit-notes.md "$INPUTS_DIR/source-docs/feature-002-exit-notes.md"
}

stage_matrix_workflows() {
  local stage_root="$1"
  shift
  mkdir -p "$stage_root/workflows"
  cp -R workflows/gradebot-t2 "$stage_root/workflows/gradebot-t2"
  cp -R workflows/gradebot-t2-matrix "$stage_root/workflows/gradebot-t2-matrix"
  uv run python - "$stage_root/workflows/gradebot-t2-matrix/workflow.yaml" "$@" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
models = list(sys.argv[2:])
if not models:
    raise SystemExit("at least one matrix model is required")
data = yaml.safe_load(path.read_text(encoding="utf-8"))
data["matrix"]["grader_model"] = models
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY
}

write_run_archive_metadata() {
  uv run python - "$ARCHIVE_DIR" "$ARTIFACT_RUN" "$START_ISO" "$CREATED_BY" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

archive = Path(sys.argv[1])
run_dir = Path(sys.argv[2])
created_at = sys.argv[3]
created_by = sys.argv[4]
run_record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
events = [
    json.loads(line)
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
counts = Counter(event["event"] for event in events)
cells = {
    event["cell_index"]: event.get("matrix") or {}
    for event in events
    if event.get("event") == "cell_started"
}
outputs_dir = run_dir / "outputs"
output_files = [path for path in outputs_dir.rglob("*") if path.is_file()] if outputs_dir.exists() else []

manifest = {
    "archive_schema": "pipyer-local-matrix-archive-v0",
    "created_at": created_at,
    "created_by": created_by,
    "workflow_name": run_record.get("workflow_name"),
    "run_id": run_record.get("run_id"),
    "workflow_hash": run_record.get("workflow_hash"),
    "local_run_dir": "artifacts/run",
    "privacy": {
        "gitignored": True,
        "may_contain_closed_course_outputs": True,
    },
    "matrix_cells": {f"cell[{index}]": params for index, params in sorted(cells.items())},
    "retained_artifacts": {
        "event_log": "artifacts/run/events.jsonl",
        "run_record": "artifacts/run/run.json",
        "checkpoint": "artifacts/run/checkpoint.json",
        "summary": "artifacts/run/summary.md",
        "outputs": "artifacts/run/outputs",
        "output_files": len(output_files),
        "transcript": "transcript.log",
        "commands": "commands.md",
    },
    "current_repo_state": {
        "head": (archive / "inputs/repo/git-head.txt").read_text(encoding="utf-8").strip(),
        "status_short_file": "inputs/repo/git-status-short.txt",
        "diff_stat_file": "inputs/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/repo/git-diff.patch",
        "untracked_file": "inputs/repo/git-untracked.txt",
        "workflow_snapshot": "inputs/current-worktree",
        "staged_workflow": "workflows/gradebot-t2-matrix/workflow.yaml",
    },
    "event_counts": dict(sorted(counts.items())),
    "final_summary": {
        "status": run_record.get("status"),
        "halt_reason": run_record.get("halt_reason"),
        "totals": run_record.get("totals"),
    },
}

comparison_root = archive / "artifacts/comparison"
if comparison_root.exists():
    comparisons = {}
    for path in sorted(comparison_root.glob("*/comparison.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        comparisons[path.parent.name] = {
            "path": path.relative_to(archive).as_posix(),
            "left": record.get("left"),
            "right": record.get("right"),
            "units": record.get("units"),
            "summaries": record.get("summaries"),
        }
    if (comparison_root / "comparison.json").is_file():
        record = json.loads((comparison_root / "comparison.json").read_text(encoding="utf-8"))
        comparisons["default"] = {
            "path": "artifacts/comparison/comparison.json",
            "left": record.get("left"),
            "right": record.get("right"),
            "units": record.get("units"),
            "summaries": record.get("summaries"),
        }
    manifest["comparisons"] = comparisons

(archive / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

readme = f"""# GradeBot T2 Matrix Run {run_record.get('run_id')}

Generated {created_at} by `{created_by}`.

## Status

- Workflow: `{run_record.get('workflow_name')}`
- Workflow hash: `{run_record.get('workflow_hash')}`
- Final status: `{run_record.get('status')}`
- Event counts: `{dict(sorted(counts.items()))}`
- Matrix cells: `{manifest['matrix_cells']}`
- Output files: `{len(output_files)}`

## Contents

- `artifacts/run/`: raw Pipyer run directory.
- `artifacts/comparison/`: `pipyer compare` artifacts, when produced.
- `commands.md`: exact commands launched by this script and exit statuses.
- `transcript.log`: captured terminal output.
- `manifest.json`: structured archive metadata.
- `inputs/current-worktree/`: GradeBot workflow source copied before staging.
- `inputs/repo/`: Git head, status, diff stat, and patch for the current repo state.

The raw Pipyer run is retained unchanged. Generated archives under `runs/` are
local and gitignored because they may contain closed-course outputs.
"""
(archive / "README.md").write_text(readme, encoding="utf-8")
PY
}
