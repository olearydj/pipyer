"""Dotted-path reference grammar (data-model.md).

A string in a mapping position is a Ref iff it FULLY matches the grammar.
Root-prefixed strings that fail the full match are errors, never silent
literals (clarification 2026-06-10; analysis finding A1/U-rule pinned the
full-match decision).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

NAMED_ROOTS = ("inputs", "steps", "matrix", "models")
BARE_ROOTS = ("item", "index")
REF_ROOTS = NAMED_ROOTS + BARE_ROOTS

_SEGMENT = r"(?:[A-Za-z_][A-Za-z0-9_]*|\d+)"
_SEGMENTS = rf"{_SEGMENT}(?:\.{_SEGMENT})*"
_FULL_RE = re.compile(
    rf"^(?:(?P<named>{'|'.join(NAMED_ROOTS)})\.(?P<named_rest>{_SEGMENTS})"
    rf"|(?P<bare>{'|'.join(BARE_ROOTS)})(?:\.(?P<bare_rest>{_SEGMENTS}))?)$"
)
_INTENT_RE = re.compile(rf"^({'|'.join(REF_ROOTS)})(\.|$)")

ESCAPE_HATCH = (
    "begins with a reserved reference root but does not fully match the reference "
    "grammar root(.segment)*; if a literal value is intended, declare it as a "
    "workflow input with a default and reference it instead"
)


class Kind(Enum):
    REF = "ref"
    LITERAL = "literal"
    ERROR = "error"


@dataclass(frozen=True)
class Ref:
    root: str
    segments: tuple[str, ...]

    def __str__(self) -> str:
        return ".".join((self.root, *self.segments))


def classify(value: object) -> tuple[Kind, Ref | None]:
    """Classify a mapping-position value: Ref, literal, or error.

    Non-strings are always literals. Strings without a reserved-root prefix are
    literals. Root-prefixed strings must fully match the grammar or they are
    errors pointing at the declare-an-input escape hatch.
    """
    if not isinstance(value, str) or not _INTENT_RE.match(value):
        return Kind.LITERAL, None
    match = _FULL_RE.match(value)
    if not match:
        return Kind.ERROR, None
    if match.group("named"):
        return Kind.REF, Ref(match.group("named"), tuple(match.group("named_rest").split(".")))
    rest = match.group("bare_rest")
    return Kind.REF, Ref(match.group("bare"), tuple(rest.split(".")) if rest else ())


def parse(value: object) -> Ref | None:
    """Return the Ref when `value` fully matches the grammar, else None."""
    kind, ref = classify(value)
    return ref if kind is Kind.REF else None
