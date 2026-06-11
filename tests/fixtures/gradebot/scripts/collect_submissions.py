"""Collect submissions: scan the submissions directory into item objects.

Pipyer code-step convention: inputs as JSON on stdin, output as JSON on stdout.
Each item carries everything downstream steps need - path, student identity,
and the feedback destination - so no later step has to derive strings.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    inputs = json.load(sys.stdin)
    submissions_dir = Path(inputs["submissions_dir"])
    output_dir = Path(inputs["output_dir"])

    submissions = [
        {
            "path": str(path),
            "student": path.stem,
            "feedback_path": str(output_dir / f"{path.stem}.md"),
        }
        for path in sorted(submissions_dir.glob("*.py"))
    ]
    json.dump({"submissions": submissions}, sys.stdout)


if __name__ == "__main__":
    main()
