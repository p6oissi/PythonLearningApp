from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExerciseTest:
    name: str
    assertion: str
    hint: str = ""


@dataclass(frozen=True)
class Exercise:
    prompt: str
    starter_code: str
    success_message: str
    tests: tuple[ExerciseTest, ...]


@dataclass(frozen=True)
class Lesson:
    id: str
    chapter: str
    title: str
    summary: str
    outcome: str
    body_markdown: str
    example_code: str
    exercise: Exercise
    hints: tuple[str, ...] = ()


REQUIRED_LESSON_FIELDS = {
    "id",
    "chapter",
    "title",
    "summary",
    "outcome",
    "body_markdown",
    "example_code",
    "exercise",
}

REQUIRED_EXERCISE_FIELDS = {
    "prompt",
    "starter_code",
    "success_message",
    "tests",
}


class LessonLoadError(ValueError):
    pass


def load_lessons(content_dir: Path) -> list[Lesson]:
    lessons: list[Lesson] = []
    for path in sorted(content_dir.glob("*.yaml")):
        lessons.extend(_load_lesson_file(path))

    seen_ids: set[str] = set()
    duplicates: set[str] = set()
    for lesson in lessons:
        if lesson.id in seen_ids:
            duplicates.add(lesson.id)
        seen_ids.add(lesson.id)
    if duplicates:
        raise LessonLoadError(f"Duplicate lesson IDs: {', '.join(sorted(duplicates))}")

    if not lessons:
        raise LessonLoadError(f"No lesson YAML files found in {content_dir}")
    return lessons


def lessons_by_chapter(lessons: list[Lesson]) -> dict[str, list[Lesson]]:
    grouped: dict[str, list[Lesson]] = {}
    for lesson in lessons:
        grouped.setdefault(lesson.chapter, []).append(lesson)
    return grouped


def _load_lesson_file(path: Path) -> list[Lesson]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("lessons"), list):
        raise LessonLoadError(f"{path} must contain a top-level 'lessons' list")

    return [_parse_lesson(item, path) for item in raw["lessons"]]


def _parse_lesson(item: Any, path: Path) -> Lesson:
    if not isinstance(item, dict):
        raise LessonLoadError(f"{path} contains a lesson that is not an object")

    missing = REQUIRED_LESSON_FIELDS - set(item)
    if missing:
        raise LessonLoadError(f"Lesson in {path} missing fields: {', '.join(sorted(missing))}")

    exercise_raw = item["exercise"]
    if not isinstance(exercise_raw, dict):
        raise LessonLoadError(f"Lesson {item.get('id')} exercise must be an object")

    missing_exercise = REQUIRED_EXERCISE_FIELDS - set(exercise_raw)
    if missing_exercise:
        raise LessonLoadError(
            f"Lesson {item.get('id')} exercise missing fields: {', '.join(sorted(missing_exercise))}"
        )

    tests_raw = exercise_raw["tests"]
    if not isinstance(tests_raw, list) or not tests_raw:
        raise LessonLoadError(f"Lesson {item.get('id')} must define at least one test")

    tests = tuple(_parse_test(test, item["id"], path) for test in tests_raw)

    hints_raw = item.get("hints", [])
    hints = tuple(str(h) for h in hints_raw) if isinstance(hints_raw, list) else ()

    return Lesson(
        id=_require_text(item, "id", path),
        chapter=_require_text(item, "chapter", path),
        title=_require_text(item, "title", path),
        summary=_require_text(item, "summary", path),
        outcome=_require_text(item, "outcome", path),
        body_markdown=_require_text(item, "body_markdown", path),
        example_code=_require_text(item, "example_code", path),
        exercise=Exercise(
            prompt=_require_text(exercise_raw, "prompt", path),
            starter_code=_require_text(exercise_raw, "starter_code", path),
            success_message=_require_text(exercise_raw, "success_message", path),
            tests=tests,
        ),
        hints=hints,
    )


def _parse_test(item: Any, lesson_id: str, path: Path) -> ExerciseTest:
    if not isinstance(item, dict):
        raise LessonLoadError(f"Lesson {lesson_id} in {path} contains a test that is not an object")
    if not item.get("name") or not item.get("assertion"):
        raise LessonLoadError(f"Lesson {lesson_id} in {path} has a test without name or assertion")
    return ExerciseTest(
        name=str(item["name"]),
        assertion=str(item["assertion"]),
        hint=str(item.get("hint", "")),
    )


def _require_text(item: dict[str, Any], field: str, path: Path) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LessonLoadError(f"{path} field '{field}' must be non-empty text")
    return value
