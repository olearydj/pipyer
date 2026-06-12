"""Prompt files: named placeholders bound by explicit input maps (ADR-004).

A placeholder is `{identifier}` with the same lowercase identifier pattern as
workflow names. Extraction is the dry-run's source of truth for binding checks
(both directions: unbound and unused are errors).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def extract_placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


def render_prompt(text: str, values: Mapping[str, Any]) -> str:
    """Substitute bound placeholders; everything else passes through verbatim.

    One definition with two jobs: the SAME regex that validation uses to
    extract placeholders performs the substitution, so validation and
    rendering cannot disagree. (Review finding: `str.format` crashed on
    ordinary JSON braces in prompts - `{"answer": "ok"}` - that the
    placeholder regex correctly ignored.) Literal braces never need escaping;
    non-string values render as indented JSON.
    """

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            return match.group(0)  # not a binding; literal text (validation already vetted)
        value = values[name]
        return value if isinstance(value, str) else json.dumps(value, indent=2, default=str)

    return PLACEHOLDER_RE.sub(_sub, text)


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")
