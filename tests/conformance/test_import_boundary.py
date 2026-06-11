"""The permanent wrapper-drift guard (R10).

The contract modules must never import the LLM substrate. Scoped to exactly the
contract modules - not all of src/pipyer/ - so Feature 002's llm component (which
legitimately imports pydantic_ai) strengthens this suite instead of weakening it.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pipyer"

# The guarded contract surface, exactly as scoped in research.md R10.
CONTRACT_PATHS = [
    SRC / "schema",
    SRC / "records",
    SRC / "canonical.py",
    SRC / "validation.py",
]

FORBIDDEN_PREFIX = "pydantic_ai"


def _python_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.py"))


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_contract_modules_do_not_import_the_substrate():
    offenders: list[str] = []
    checked = 0
    for root in CONTRACT_PATHS:
        assert root.exists(), f"contract module missing: {root}"
        for file in _python_files(root):
            checked += 1
            for module in _imported_modules(file.read_text(encoding="utf-8")):
                if module == FORBIDDEN_PREFIX or module.startswith(FORBIDDEN_PREFIX + "."):
                    offenders.append(f"{file.relative_to(SRC.parent.parent)}: imports {module}")
    assert checked > 0
    assert not offenders, "substrate import inside contract modules:\n" + "\n".join(offenders)
