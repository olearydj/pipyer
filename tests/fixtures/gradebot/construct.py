"""The GradeBot workflow via direct Python construction - the second authoring
surface (ADR-004). Must produce canonical bytes identical to workflow.yaml."""

from pipyer.schema.components import (
    AssertionsConfig,
    Check,
    FileReadConfig,
    FileWriteConfig,
    LlmConfig,
    PythonConfig,
    ShellConfig,
)
from pipyer.schema.workflow import (
    AssertionsStep,
    FileReadStep,
    FileWriteStep,
    InputDecl,
    LlmStep,
    ModelAlias,
    PythonStep,
    Settings,
    ShellStep,
    Workflow,
)

SUBMISSIONS = "steps.collect_submissions.output.submissions"

GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "comments": {"type": "string"},
        "feedback_markdown": {"type": "string"},
    },
    "required": ["score", "comments", "feedback_markdown"],
}


def build() -> Workflow:
    return Workflow(
        schema_version="2",
        name="gradebot_hw",
        description=(
            "Grade one assignment's submissions against a rubric, with per-student evidence."
        ),
        inputs={
            "submissions_dir": InputDecl(
                type="path",
                required=False,
                default="submissions",
                description="Directory of student .py submissions",
            ),
            "rubric_file": InputDecl(
                type="path",
                required=False,
                default="rubric.md",
                description="The rubric the grader applies verbatim",
            ),
            "output_dir": InputDecl(
                type="path",
                required=False,
                default="feedback",
                description="Where per-student feedback files land",
            ),
            "summary_file": InputDecl(
                type="path",
                required=False,
                default="grades/summary.md",
                description="Where the batch summary report lands",
            ),
        },
        models={"grader": ModelAlias(model="test", settings={})},
        steps=[
            PythonStep(
                name="collect_submissions",
                component="python",
                config=PythonConfig(script="scripts/collect_submissions.py"),
                inputs={
                    "submissions_dir": "inputs.submissions_dir",
                    "output_dir": "inputs.output_dir",
                },
            ),
            FileReadStep(
                name="read_rubric",
                component="file_read",
                config=FileReadConfig(path="inputs.rubric_file", format="text"),
            ),
            ShellStep(
                name="run_tests",
                component="shell",
                each=SUBMISSIONS,
                config=ShellConfig(
                    command=["uv", "run", "python", "scripts/run_submission_tests.py"],
                    parse_stdout="json",
                ),
                inputs={"submission_path": "item.path"},
            ),
            FileReadStep(
                name="read_submission",
                component="file_read",
                each=SUBMISSIONS,
                config=FileReadConfig(path="item.path", format="text"),
            ),
            LlmStep(
                name="grade",
                component="llm",
                each=SUBMISSIONS,
                config=LlmConfig(
                    model="grader",
                    prompt="prompts/grade_submission.md",
                    output_schema=GRADE_SCHEMA,
                    max_validation_retries=2,
                ),
                inputs={
                    "rubric": "steps.read_rubric.content",
                    "submission": "steps.read_submission.content",
                    "test_output": "steps.run_tests.stdout",
                },
            ),
            AssertionsStep(
                name="check_grades",
                component="assertions",
                each=SUBMISSIONS,
                config=AssertionsConfig(
                    checks=[
                        Check(input="score", op="gte", expected=0),
                        Check(input="score", op="lte", expected=100),
                    ]
                ),
                inputs={"score": "steps.grade.output.score"},
            ),
            FileWriteStep(
                name="write_feedback",
                component="file_write",
                each=SUBMISSIONS,
                config=FileWriteConfig(path="item.feedback_path", format="markdown"),
                inputs={"content": "steps.grade.output.feedback_markdown"},
            ),
            PythonStep(
                name="summarize",
                component="python",
                config=PythonConfig(script="scripts/summarize_grades.py"),
                inputs={
                    "submissions": SUBMISSIONS,
                    "grades": "steps.grade.output",
                    "test_results": "steps.run_tests.stdout",
                },
            ),
            FileWriteStep(
                name="write_summary",
                component="file_write",
                config=FileWriteConfig(path="inputs.summary_file", format="markdown"),
                inputs={"content": "steps.summarize.output.report_markdown"},
            ),
        ],
        settings=Settings(concurrency=2, max_failures=5, max_failure_rate=0.25),
        outputs={
            "grades": "steps.grade.output",
            "summary_stats": "steps.summarize.output.stats",
        },
    )
