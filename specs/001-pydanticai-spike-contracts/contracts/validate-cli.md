# Contract: `pipyer validate` (CLI)

The authoring loop for people and agents until the Feature 002 runner arrives (FR-021). It validates and never executes.

## Invocation

```bash
pipyer validate <workflow-file> [--json]
```

- `<workflow-file>`: path to a YAML workflow. Prompt files referenced by the workflow resolve relative to the workflow file's directory.
- `--json`: machine-readable error output (the agent authoring loop).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Workflow is valid (dry-run passes in full) |
| 1 | Validation errors found |
| 2 | Usage or I/O error (missing file, unreadable YAML, unsafe YAML constructs) |

## Output

Valid workflow (exit 0):

```text
OK <workflow-name> (schema v1, hash sha256:ab12…)
```

Invalid workflow (exit 1), human format - every error names its location:

```text
INVALID gradebot (3 errors)
  steps[1].inputs.test_output: reference to unknown step 'run_test' (did you mean 'run_tests'?)
  steps[3].config.prompt: placeholder 'rubric' is not bound by inputs
  settings.max_failure_rate: must be between 0 and 1
```

Invalid workflow with `--json` (exit 1):

```json
{
  "valid": false,
  "workflow": "gradebot",
  "schema_version": "1",
  "errors": [
    {"loc": "steps[1].inputs.test_output", "code": "unknown_step_ref", "message": "reference to unknown step 'run_test'"}
  ]
}
```

## Guarantees

1. Never executes anything: no step runs, no file writes, no network calls, no provider access. Reads only the workflow file and the prompt files it references.
2. Library parity: the CLI reports exactly the errors the library validation API reports (SC-004) - one validation implementation, two surfaces.
3. On success, the printed hash is the workflow hash over canonical bytes - the same value a run record would carry.
4. Errors are deterministic and ordered (document order), so agent retry loops see stable output.
