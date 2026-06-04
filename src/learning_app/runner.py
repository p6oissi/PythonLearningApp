from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from learning_app.content import ExerciseTest


FORBIDDEN_IMPORTS = {
    "ctypes",
    "multiprocessing",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
}

FORBIDDEN_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
}


@dataclass(frozen=True)
class TestResult:
    name: str
    passed: bool
    message: str = ""
    hint: str = ""


@dataclass(frozen=True)
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


@dataclass(frozen=True)
class CheckResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    blocked: bool
    block_reason: str
    tests: tuple[TestResult, ...]

    @property
    def passed(self) -> bool:
        return not self.blocked and bool(self.tests) and all(test.passed for test in self.tests)


def run_code(source: str, timeout_seconds: int = 5) -> RunResult:
    block_reason = find_block_reason(source)
    if block_reason:
        return RunResult(stdout="", stderr=block_reason, exit_code=1)

    with tempfile.TemporaryDirectory() as temp_dir:
        solution_path = Path(temp_dir) / "learner_solution.py"
        solution_path.write_text(source, encoding="utf-8")
        return _run_subprocess([sys.executable, str(solution_path)], timeout_seconds)


def check_code(source: str, tests: tuple[ExerciseTest, ...], timeout_seconds: int = 5) -> CheckResult:
    block_reason = find_block_reason(source)
    if block_reason:
        return CheckResult(
            stdout="",
            stderr="",
            exit_code=1,
            timed_out=False,
            blocked=True,
            block_reason=block_reason,
            tests=(),
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        solution_path = Path(temp_dir) / "learner_solution.py"
        harness_path = Path(temp_dir) / "check_solution.py"
        solution_path.write_text(source, encoding="utf-8")
        harness_path.write_text(_build_harness(solution_path, tests), encoding="utf-8")

        run = _run_subprocess([sys.executable, str(harness_path)], timeout_seconds)
        parsed_tests = _parse_test_results(run.stdout)
        visible_stdout = _remove_result_line(run.stdout)
        return CheckResult(
            stdout=visible_stdout,
            stderr=run.stderr,
            exit_code=run.exit_code,
            timed_out=run.timed_out,
            blocked=False,
            block_reason="",
            tests=parsed_tests,
        )


def find_block_reason(source: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    return f"Import '{root}' is blocked in this local learning runner."
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                return f"Import '{root}' is blocked in this local learning runner."
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALLS:
                return f"Call '{call_name}' is blocked in this local learning runner."
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _run_subprocess(command: list[str], timeout_seconds: int) -> RunResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return RunResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nTimed out after {timeout_seconds} seconds.",
            exit_code=124,
            timed_out=True,
        )


def _build_harness(solution_path: Path, tests: tuple[ExerciseTest, ...]) -> str:
    test_payload = [
        {"name": test.name, "assertion": test.assertion, "hint": test.hint}
        for test in tests
    ]
    return f"""
import contextlib
import importlib.util
import io
import json
import math
import statistics
import traceback

RESULT_PREFIX = "__LEARNING_APP_RESULT__"
solution_path = {str(solution_path)!r}
test_payload = {test_payload!r}
results = []
captured_stdout = io.StringIO()

try:
    spec = importlib.util.spec_from_file_location("learner_solution", solution_path)
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(captured_stdout):
        spec.loader.exec_module(module)
except Exception as exc:
    print(captured_stdout.getvalue(), end="")
    results.append({{
        "name": "Import and run solution",
        "passed": False,
        "message": traceback.format_exc(limit=6),
        "hint": "Fix the error raised while Python loads your code."
    }})
else:
    print(captured_stdout.getvalue(), end="")
    for test in test_payload:
        try:
            exec(test["assertion"], {{"m": module, "math": math, "statistics": statistics}}, {{}})
            results.append({{
                "name": test["name"],
                "passed": True,
                "message": "",
                "hint": test.get("hint", "")
            }})
        except AssertionError as exc:
            results.append({{
                "name": test["name"],
                "passed": False,
                "message": str(exc) or "Assertion failed.",
                "hint": test.get("hint", "")
            }})
        except Exception:
            results.append({{
                "name": test["name"],
                "passed": False,
                "message": traceback.format_exc(limit=4),
                "hint": test.get("hint", "")
            }})

print(RESULT_PREFIX + json.dumps(results))
"""


def _parse_test_results(stdout: str) -> tuple[TestResult, ...]:
    for line in reversed(stdout.splitlines()):
        if line.startswith("__LEARNING_APP_RESULT__"):
            payload = line.removeprefix("__LEARNING_APP_RESULT__")
            raw_results = json.loads(payload)
            return tuple(
                TestResult(
                    name=str(item.get("name", "")),
                    passed=bool(item.get("passed", False)),
                    message=str(item.get("message", "")),
                    hint=str(item.get("hint", "")),
                )
                for item in raw_results
            )
    return (
        TestResult(
            name="Check runner",
            passed=False,
            message="The check runner did not return structured results.",
            hint="Check for syntax errors or unexpected process output.",
        ),
    )


def _remove_result_line(stdout: str) -> str:
    return "\n".join(
        line for line in stdout.splitlines() if not line.startswith("__LEARNING_APP_RESULT__")
    )
