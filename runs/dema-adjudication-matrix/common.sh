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

check_dema_lock() {
  local lock_file="$REPO_ROOT/workflows/dema-adjudication-matrix/dema.lock.json"
  uv run python - "$lock_file" "$DEMA_REPO" "${ALLOW_DEMA_DRIFT:-0}" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

lock_path = Path(sys.argv[1])
repo = Path(sys.argv[2])
allow_drift = sys.argv[3].strip().lower() in {"1", "true", "yes", "y"}

lock = json.loads(lock_path.read_text(encoding="utf-8"))
expected = str(lock["commit"])
clean_required = bool(lock.get("clean_required", True))

def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()

actual = git("rev-parse", "HEAD")
dirty = git("status", "--porcelain", "--untracked-files=all")
problems = []
if actual != expected:
    problems.append(f"commit mismatch: expected {expected}, actual {actual}")
if clean_required and dirty:
    problems.append("worktree is not clean")

if problems:
    print("DEMA lock check failed:")
    print(f"  repo: {repo}")
    print(f"  lock: {lock_path}")
    for problem in problems:
        print(f"  - {problem}")
    if dirty:
        print("  dirty status:")
        for line in dirty.splitlines():
            print(f"    {line}")
    if allow_drift:
        print("ALLOW_DEMA_DRIFT is set; continuing despite DEMA lock check failure.")
    else:
        print("Set ALLOW_DEMA_DRIFT=1 only for intentional drift experiments.")
        raise SystemExit(2)
else:
    print(f"DEMA lock check OK: {actual}")
PY
}

check_provider_env() {
  uv run python - "$DEMA_REPO/router.yaml" "$ROUTES_JOINED" <<'PY'
import sys
from pathlib import Path

import yaml

from pipyer.secrets import SecretResolutionError, resolve_secret

router_path = Path(sys.argv[1])
routes = [part for part in sys.argv[2].split(",") if part]
data = yaml.safe_load(router_path.read_text(encoding="utf-8")) or {}
aliases = data.get("model_aliases") or {}
per_alias = data.get("per_alias_params") or {}

def infer_provider(target: str | None) -> str:
    if not target:
        return "unknown"
    if target.startswith("openai/"):
        return "openai"
    if target.startswith("anthropic/"):
        return "anthropic"
    if target.startswith("ollama/"):
        return "ollama"
    return "unknown"

provider_env = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
failures: list[tuple[str, str, str, str]] = []
checked: list[tuple[str, str, str | None, str | None]] = []
resolved: set[str] = set()
for route in routes:
    target = aliases.get(route)
    overrides = per_alias.get(route) or {}
    provider = str(overrides.get("provider_kind") or infer_provider(str(target) if target else None))
    env_name = provider_env.get(provider)
    source = None
    if env_name:
        try:
            _secret, source = resolve_secret(env_name, provider="1password")
            resolved.add(env_name)
        except SecretResolutionError as error:
            failures.append((route, provider, env_name, str(error)))
    checked.append((route, provider, env_name, source))

if failures:
    print("DEMA 1Password credential check failed:")
    for route, provider, env_name, error in failures:
        print(f"  - {route} resolves to provider {provider}; could not resolve {env_name}: {error}")
    print("Set PIPYER_<KEY>_OP_REFERENCE for each required key, or change ROUTE_MATRIX.")
    raise SystemExit(2)

print("DEMA 1Password credential check OK:")
for route, provider, env_name, source in checked:
    if env_name and env_name in resolved:
        print(f"  - {route}: {provider} via {env_name} from {source}")
    else:
        print(f"  - {route}: {provider} needs no checked API key")
PY
}

copy_repo_evidence() {
  mkdir -p "$INPUTS_DIR/current-worktree" "$INPUTS_DIR/repo" "$INPUTS_DIR/source-docs"
  cp -R workflows/dema-adjudication-matrix "$INPUTS_DIR/current-worktree/dema-adjudication-matrix"
  git rev-parse HEAD > "$INPUTS_DIR/repo/git-head.txt"
  git status --short > "$INPUTS_DIR/repo/git-status-short.txt"
  git diff --stat > "$INPUTS_DIR/repo/git-diff-stat.txt"
  git diff --binary > "$INPUTS_DIR/repo/git-diff.patch"
  git ls-files --others --exclude-standard > "$INPUTS_DIR/repo/git-untracked.txt"
  copy_if_present pyproject.toml "$INPUTS_DIR/repo/pyproject.toml"
  copy_if_present uv.lock "$INPUTS_DIR/repo/uv.lock"
  copy_if_present README.md "$INPUTS_DIR/repo/README.md"
  copy_if_present docs/sprint-03/BRIEF.md "$INPUTS_DIR/source-docs/sprint-03-brief.md"
}

copy_dema_evidence() {
  mkdir -p "$INPUTS_DIR/dema/repo" "$INPUTS_DIR/dema/data"
  git -C "$DEMA_REPO" rev-parse HEAD > "$INPUTS_DIR/dema/repo/git-head.txt"
  git -C "$DEMA_REPO" status --short > "$INPUTS_DIR/dema/repo/git-status-short.txt"
  git -C "$DEMA_REPO" diff --stat > "$INPUTS_DIR/dema/repo/git-diff-stat.txt"
  git -C "$DEMA_REPO" diff --binary > "$INPUTS_DIR/dema/repo/git-diff.patch"
  git -C "$DEMA_REPO" ls-files --others --exclude-standard > "$INPUTS_DIR/dema/repo/git-untracked.txt"
  copy_if_present "$DEMA_REPO/pyproject.toml" "$INPUTS_DIR/dema/repo/pyproject.toml"
  copy_if_present "$DEMA_REPO/uv.lock" "$INPUTS_DIR/dema/repo/uv.lock"
  copy_if_present "$DEMA_REPO/router.yaml" "$INPUTS_DIR/dema/repo/router.yaml"
  copy_if_present "$DEMA_REPO/data/elements.csv" "$INPUTS_DIR/dema/data/elements.csv"
  copy_if_present "$DEMA_REPO/data/vessels.csv" "$INPUTS_DIR/dema/data/vessels.csv"
  copy_if_present "$DEMA_REPO/data/relations.csv" "$INPUTS_DIR/dema/data/relations.csv"
}

split_csv_routes() {
  local raw="$1"
  local IFS=,
  local -a parts
  read -r -a parts <<< "$raw"
  local part
  for part in "${parts[@]}"; do
    part="${part#"${part%%[![:space:]]*}"}"
    part="${part%"${part##*[![:space:]]}"}"
    if [[ -n "$part" ]]; then
      ROUTES+=("$part")
    fi
  done
}

split_csv_confidences() {
  local raw="$1"
  local IFS=,
  local -a parts
  read -r -a parts <<< "$raw"
  local part
  for part in "${parts[@]}"; do
    part="${part#"${part%%[![:space:]]*}"}"
    part="${part%"${part##*[![:space:]]}"}"
    if [[ -n "$part" ]]; then
      CONFIDENCES+=("$part")
    fi
  done
}

stage_dema_workflow() {
  local stage_root="$1"
  shift
  mkdir -p "$stage_root/workflows"
  cp -R workflows/dema-adjudication-matrix "$stage_root/workflows/dema-adjudication-matrix"
  uv run python - "$stage_root/workflows/dema-adjudication-matrix/workflow.yaml" "$ROUTES_JOINED" "$CONFIDENCES_JOINED" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
routes = [part for part in sys.argv[2].split(",") if part]
confidences = [float(part) for part in sys.argv[3].split(",") if part]
if not routes:
    raise SystemExit("at least one DEMA route is required")
if not confidences:
    raise SystemExit("at least one confidence threshold is required")
data = yaml.safe_load(path.read_text(encoding="utf-8"))
data["matrix"]["adjudicator_route"] = routes
data["matrix"]["confidence_threshold"] = confidences
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY
}

write_dema_archive_metadata() {
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
eval_metrics = {}
for event in events:
    if event.get("event") != "step_result":
        continue
    if event.get("step") != "evaluate" or event.get("status") != "success":
        continue
    cell_index = event.get("cell_index")
    output = event.get("output") or {}
    stdout = output.get("stdout") or {}
    eval_metrics[f"cell[{cell_index}]"] = stdout.get("metrics") or {}

dema_root = archive / "artifacts/dema"
dema_files = [path for path in dema_root.rglob("*") if path.is_file()] if dema_root.exists() else []
output_files = [
    path for path in (run_dir / "outputs").rglob("*") if path.is_file()
] if (run_dir / "outputs").exists() else []

manifest = {
    "archive_schema": "pipyer-dema-matrix-archive-v0",
    "created_at": created_at,
    "created_by": created_by,
    "workflow_name": run_record.get("workflow_name"),
    "run_id": run_record.get("run_id"),
    "workflow_hash": run_record.get("workflow_hash"),
    "local_run_dir": "artifacts/run",
    "matrix_cells": {f"cell[{index}]": params for index, params in sorted(cells.items())},
    "eval_metrics": eval_metrics,
    "retained_artifacts": {
        "event_log": "artifacts/run/events.jsonl",
        "run_record": "artifacts/run/run.json",
        "checkpoint": "artifacts/run/checkpoint.json",
        "summary": "artifacts/run/summary.md",
        "pipyer_outputs": "artifacts/run/outputs",
        "pipyer_output_files": len(output_files),
        "dema_outputs": "artifacts/dema",
        "dema_output_files": len(dema_files),
        "transcript": "transcript.log",
        "commands": "commands.md",
    },
    "current_repo_state": {
        "head": (archive / "inputs/repo/git-head.txt").read_text(encoding="utf-8").strip(),
        "status_short_file": "inputs/repo/git-status-short.txt",
        "diff_stat_file": "inputs/repo/git-diff-stat.txt",
        "diff_patch_file": "inputs/repo/git-diff.patch",
        "untracked_file": "inputs/repo/git-untracked.txt",
        "workflow_snapshot": "inputs/current-worktree/dema-adjudication-matrix",
        "staged_workflow": "workflows/dema-adjudication-matrix/workflow.yaml",
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
    "event_counts": dict(sorted(counts.items())),
    "final_summary": {
        "status": run_record.get("status"),
        "halt_reason": run_record.get("halt_reason"),
        "totals": run_record.get("totals"),
    },
}
lock_path = archive / "inputs/current-worktree/dema-adjudication-matrix/dema.lock.json"
if lock_path.exists():
    try:
        manifest["dema_lock"] = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        manifest["dema_lock"] = {"path": "inputs/current-worktree/dema-adjudication-matrix/dema.lock.json"}

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

readme = f"""# DEMA Adjudication Matrix Run {run_record.get('run_id')}

Generated {created_at} by `{created_by}`.

## Status

- Workflow: `{run_record.get('workflow_name')}`
- Workflow hash: `{run_record.get('workflow_hash')}`
- Final status: `{run_record.get('status')}`
- Event counts: `{dict(sorted(counts.items()))}`
- Matrix cells: `{manifest['matrix_cells']}`
- DEMA artifact files: `{len(dema_files)}`

## Contents

- `artifacts/run/`: raw Pipyer run directory.
- `artifacts/dema/`: DEMA CLI outputs produced by workflow shell steps.
- `artifacts/comparison/`: `pipyer compare` artifacts, when produced.
- `commands.md`: exact commands launched by this script and exit statuses.
- `transcript.log`: captured terminal output.
- `manifest.json`: structured archive metadata.
- `inputs/current-worktree/`: Pipyer workflow source copied before staging.
- `inputs/dema/`: DEMA repo state and input snapshots.
- `inputs/repo/`: Pipyer Git head, status, diff stat, and patch.

The raw Pipyer run is retained unchanged. Generated archives under `runs/` are
local and gitignored.
"""
(archive / "README.md").write_text(readme, encoding="utf-8")
PY
}
