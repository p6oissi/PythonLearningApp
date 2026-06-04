from learning_app.content import ExerciseTest
from learning_app.runner import check_code, find_block_reason, run_code


def test_run_code_captures_stdout() -> None:
    result = run_code("print('hello')")

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"


def test_check_code_passes_and_fails() -> None:
    tests = (
        ExerciseTest(name="x is two", assertion="assert m.x == 2", hint="Set x to 2."),
    )

    passing = check_code("x = 2", tests)
    failing = check_code("x = 1", tests)

    assert passing.passed is True
    assert failing.passed is False
    assert failing.tests[0].hint == "Set x to 2."


def test_runner_blocks_dangerous_imports_and_calls() -> None:
    assert "blocked" in find_block_reason("import os").lower()
    assert "blocked" in find_block_reason("value = open('x.txt')").lower()
