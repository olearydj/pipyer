# GradeBot T2 Local Runs

This directory holds local, gitignored GradeBot T2 run evidence.

Use `run-current.sh` to create a new archive from the current repo state:

```bash
runs/gradebot-t2/run-current.sh
```

The script:

- validates `workflows/gradebot-t2/workflow.yaml`;
- optionally performs a dry run;
- runs the live workflow against the archived T2 corpus;
- captures terminal output in `transcript.log`;
- stores the raw Pipyer run directory under `artifacts/run/`;
- snapshots the workflow tree, Git head/status/diff, and relevant Sprint 02 docs;
- writes `commands.md`, `manifest.json`, and `README.md`.

The default inputs match the Sprint 02 acceptance baseline. Override paths with
environment variables when needed:

```bash
CORPUS=/path/to/t2 \
RAW_BASELINE=runs/phase1-v2/grading_results_20260402_211734.csv \
ANNOTATIONS_FILE=/path/to/pipyer-annotations.json \
runs/gradebot-t2/run-current.sh
```

The generated archive is named from the Pipyer run id when the run record is
available.
