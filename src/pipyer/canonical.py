"""The canonical serialization: one definition, three jobs (R7).

Deterministic JSON over the validated model - UTF-8, sorted keys, compact
separators, defaults materialized, schema_version included. Dual-surface
equality (SC-003) is byte equality of this serialization; the workflow hash is
SHA-256 over exactly these bytes; resume matching (Feature 002) compares the
same hash. A schema-version bump changes these bytes by design, ending hash
continuity at the version boundary.
"""

from __future__ import annotations

import hashlib
import json

from pipyer.schema.workflow import Workflow


def canonical_bytes(workflow: Workflow) -> bytes:
    data = workflow.model_dump(mode="json")  # materializes defaults; never exclude_unset
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def workflow_hash(workflow: Workflow) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(workflow)).hexdigest()
