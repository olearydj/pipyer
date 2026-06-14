from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKFLOW_DIR = Path.cwd()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: dema_stage.py triage|adjudicate|cluster|evaluate")
    stage = sys.argv[1]
    inputs = json.loads(sys.stdin.read() or "{}")
    if stage == "triage":
        emit(run_triage(inputs))
    elif stage == "adjudicate":
        emit(run_adjudicate(inputs))
    elif stage == "cluster":
        emit(run_cluster(inputs))
    elif stage == "evaluate":
        emit(run_evaluate(inputs))
    else:
        raise SystemExit(f"unknown DEMA stage: {stage}")


def run_triage(inputs: dict[str, Any]) -> dict[str, Any]:
    dema_repo = repo_path(inputs)
    cell_dir = output_cell_dir(inputs)
    pairs_path = cell_dir / "candidate_pairs.jsonl"
    log_path = cell_dir / "logs" / "triage.jsonl"
    cmd = dema_cmd(dema_repo, log_path) + [
        "triage",
        "pairs",
        "--elements",
        str(dema_input_path(inputs["elements_csv"], dema_repo)),
        "--vessels",
        str(dema_input_path(inputs["vessels_csv"], dema_repo)),
        "--relations",
        str(dema_input_path(inputs["relations_csv"], dema_repo)),
        "--out",
        str(pairs_path),
        "--t-string",
        str(inputs["triage_t_string"]),
        "--t-embed",
        str(inputs["triage_t_embed"]),
        "--use-embed",
        str(inputs["triage_use_embed"]),
        "--top-k",
        str(inputs["triage_top_k"]),
        "--max-pairs",
        str(inputs["max_pairs"]),
        "--seed",
        str(inputs["seed"]),
    ]
    cmd.append("--match-semantic" if bool(inputs["match_semantic"]) else "--no-match-semantic")
    proc = run(cmd, cwd=dema_repo)
    return stage_record(
        "triage",
        inputs,
        cmd,
        proc,
        {
            "pairs_path": str(pairs_path),
            "log_path": str(log_path),
            "pair_count": count_jsonl(pairs_path),
            "artifacts": artifact_map(cell_dir),
        },
    )


def run_adjudicate(inputs: dict[str, Any]) -> dict[str, Any]:
    dema_repo = repo_path(inputs)
    cell_dir = output_cell_dir(inputs)
    route = str(inputs["adjudicator_route"])
    confidence = str(inputs["confidence_threshold"])
    decisions_path = cell_dir / f"decisions.{slug(route)}.threshold-{slug(confidence)}.jsonl"
    review_path = cell_dir / "decision_journal.jsonl"
    log_path = cell_dir / "logs" / "adjudicate.jsonl"
    cmd = dema_cmd(dema_repo, log_path) + [
        "adjudicate",
        "run",
        "--pairs",
        str(Path(inputs["pairs_path"])),
        "--model",
        route,
        "--out",
        str(decisions_path),
        "--review-journal",
        str(review_path),
        "--confidence-threshold",
        confidence,
        "--seed",
        str(inputs["seed"]),
    ]
    proc = run(cmd, cwd=dema_repo)
    pair_count = count_jsonl(Path(inputs["pairs_path"]))
    decision_count = count_jsonl(decisions_path)
    record = stage_record(
        "adjudicate",
        inputs,
        cmd,
        proc,
        {
            "decisions_path": str(decisions_path),
            "review_journal_path": str(review_path),
            "log_path": str(log_path),
            "pair_count": pair_count,
            "decision_count": decision_count,
            "review_count": count_jsonl(review_path),
            "artifacts": artifact_map(cell_dir),
        },
    )
    if decision_count != pair_count:
        record["validation_error"] = (
            f"DEMA adjudicate wrote {decision_count} decisions for {pair_count} input pairs"
        )
        emit(record)
        print(record["validation_error"], file=sys.stderr)
        raise SystemExit(1)
    return record


def run_cluster(inputs: dict[str, Any]) -> dict[str, Any]:
    dema_repo = repo_path(inputs)
    cell_dir = output_cell_dir(inputs)
    clusters_path = cell_dir / "alias_clusters.json"
    alias_map_path = cell_dir / "alias_map.csv"
    journal_path = cell_dir / "cluster_journal.jsonl"
    next_pairs_path = cell_dir / "next_pairs.jsonl"
    log_path = cell_dir / "logs" / "cluster.jsonl"
    cmd = dema_cmd(dema_repo, log_path) + [
        "cluster",
        "build",
        "--stage",
        "element",
        "--decisions",
        str(Path(inputs["decisions_path"])),
        "--pairs",
        str(Path(inputs["pairs_path"])),
        "--clusters",
        str(clusters_path),
        "--alias-map",
        str(alias_map_path),
        "--journal",
        str(journal_path),
        "--next-pairs",
        str(next_pairs_path),
        "--next-k",
        str(inputs["cluster_next_k"]),
        "--tau-merge",
        str(inputs["cluster_tau_merge"]),
        "--tau-keep",
        str(inputs["cluster_tau_keep"]),
        "--tau-cross-vessel",
        str(inputs["cluster_tau_cross_vessel"]),
        "--alpha-actor",
        str(inputs["cluster_alpha_actor"]),
        "--delta-row",
        str(inputs["cluster_delta_row"]),
    ]
    proc = run(cmd, cwd=dema_repo)
    return stage_record(
        "cluster",
        inputs,
        cmd,
        proc,
        {
            "clusters_path": str(clusters_path),
            "alias_map_path": str(alias_map_path),
            "journal_path": str(journal_path),
            "next_pairs_path": str(next_pairs_path),
            "log_path": str(log_path),
            "cluster_count": cluster_count(clusters_path),
            "journal_count": count_jsonl(journal_path),
            "next_pair_count": count_jsonl(next_pairs_path),
            "artifacts": artifact_map(cell_dir),
        },
    )


def run_evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    dema_repo = repo_path(inputs)
    cell_dir = output_cell_dir(inputs)
    report_path = cell_dir / "eval_report.md"
    metrics_db_path = cell_dir / "metrics.sqlite"
    log_path = cell_dir / "logs" / "eval.jsonl"
    cmd = dema_cmd(dema_repo, log_path) + [
        "eval",
        "compare",
        "--gold",
        str(workflow_input_path(inputs["gold_pairs"])),
        "--runs",
        str(Path(inputs["decisions_path"])),
        "--report",
        str(report_path),
        "--metrics-db",
        str(metrics_db_path),
        "--confidence-threshold",
        str(inputs["confidence_threshold"]),
        "--logs",
        str(Path(inputs["adjudicate_log_path"])),
        "--pairs",
        str(Path(inputs["pairs_path"])),
    ]
    proc = run(cmd, cwd=dema_repo)
    metrics = read_eval_metrics(metrics_db_path)
    return stage_record(
        "evaluate",
        inputs,
        cmd,
        proc,
        {
            "report_path": str(report_path),
            "metrics_db_path": str(metrics_db_path),
            "log_path": str(log_path),
            "metrics": metrics,
            "artifacts": artifact_map(cell_dir),
        },
    )


def repo_path(inputs: dict[str, Any]) -> Path:
    path = Path(str(inputs["dema_repo"])).expanduser()
    return path if path.is_absolute() else (WORKFLOW_DIR / path).resolve()


def workflow_input_path(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (WORKFLOW_DIR / path).resolve()


def dema_input_path(value: Any, dema_repo: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (dema_repo / path).resolve()


def output_cell_dir(inputs: dict[str, Any]) -> Path:
    root = Path(str(inputs["output_root"])).expanduser()
    if not root.is_absolute():
        root = (WORKFLOW_DIR / root).resolve()
    route = str(inputs["adjudicator_route"])
    confidence = str(inputs["confidence_threshold"])
    cell_dir = root / f"route-{slug(route)}__confidence-{slug(confidence)}"
    (cell_dir / "logs").mkdir(parents=True, exist_ok=True)
    return cell_dir


def dema_cmd(dema_repo: Path, log_path: Path) -> list[str]:
    return [
        "uv",
        "--no-config",
        "run",
        "--locked",
        "--project",
        str(dema_repo),
        "dema-llm",
        "--log-path",
        str(log_path),
    ]


def run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=os.environ.copy())
    if proc.returncode != 0:
        if proc.stdout:
            sys.stderr.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc


def stage_record(
    stage: str,
    inputs: dict[str, Any],
    cmd: list[str],
    proc: subprocess.CompletedProcess[str],
    extra: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "stage": stage,
        "matrix": {
            "adjudicator_route": inputs.get("adjudicator_route"),
            "confidence_threshold": inputs.get("confidence_threshold"),
        },
        "command": cmd,
        "stdout_text": proc.stdout,
        "stderr_text": proc.stderr,
        "exit_code": proc.returncode,
    }
    record.update(extra)
    return record


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, sort_keys=True, separators=(",", ":")))


def slug(value: Any) -> str:
    text = str(value).strip().lower()
    text = text.replace(".", "p")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "value"


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def cluster_count(path: Path) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("clusters", "alias_clusters"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)
    return 0


def artifact_map(cell_dir: Path) -> dict[str, str]:
    files = sorted(path for path in cell_dir.rglob("*") if path.is_file())
    return {
        path.relative_to(cell_dir).as_posix(): sha256(path)
        for path in files
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_eval_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT route, model_name, model_version, threshold, n_total, n_gold,
                   n_eval, tp, fp, tn, fn, precision, recall, coverage,
                   abstain_rate, latency_p50, latency_p95, cost_total,
                   cost_per_tp
            FROM runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else {}


if __name__ == "__main__":
    main()
