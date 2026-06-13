# Local Run Archive

This directory is a local evidence archive for Pipyer runs. It is intentionally
gitignored because run artifacts can contain closed-course data, student
identifiers, provider outputs, and other material that must not enter the repo.

Suggested layout:

```text
runs/
  <workflow-name>/
    <run-id>/
      README.md          # human summary and provenance
      commands.md        # exact or reconstructed commands
      manifest.json      # machine-readable archive metadata
      inputs/            # workflow/config/doc snapshots used to reconstruct
      artifacts/run/     # copied Pipyer run directory: events, run.json, outputs
```

For reproducibility, keep the raw Pipyer run directory intact under
`artifacts/run/` and put any command reconstruction beside it rather than
editing the retained event log.
