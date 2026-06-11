"""Prompt files: named placeholders bound by explicit input maps (ADR-004).

A placeholder is `{identifier}` with the same lowercase identifier pattern as
workflow names. Extraction is the dry-run's source of truth for binding checks
(both directions: unbound and unused are errors).
"""

from __future__ import annotations

import re
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def extract_placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")
