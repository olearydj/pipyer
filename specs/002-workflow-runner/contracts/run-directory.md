# Contract: Run Directory Layout

One directory per run under `settings.results_dir` (CLI-overridable). Run id format: `<UTC yyyymmdd-HHMMSS>-<first 6 hex of workflow_hash>` (research R17).

```text
<results_dir>/<run_id>/
├── events.jsonl       # append-only JSONL event log - the authoritative record
├── events.jsonl.lock  # single-writer lock: {pid, started_at}; absent after clean exit
├── checkpoint.json    # atomic snapshot (temp + fsync + rename); reconstructable from log
├── run.json           # RunRecord, written when the run reaches a terminal status
├── summary.md         # derive_summary(events.jsonl) output; regenerable, byte-stable
└── outputs/           # declared outputs: relative file_write paths resolve here;
                       #   absolute paths are honored (acceptance run writes externally)
```

Invariants:

- `events.jsonl` is written by exactly one appender; events for resumed invocations append to the same file (`run_resumed` marks the boundary).
- `checkpoint.json` is never read as authority: resume replays the log and uses the checkpoint only as a consistency cross-check; mismatch is a loud error.
- A directory containing `events.jsonl` is a resumable run regardless of which other files exist; `run.json` and `summary.md` existence implies terminal status.
- No file in the run directory ever contains a secret value (provider names allowed).
- Files are UTF-8; JSONL lines use compact separators per `event_line()`.
