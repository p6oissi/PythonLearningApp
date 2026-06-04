from pathlib import Path

from learning_app.content import load_lessons


def test_load_lessons_validates_curriculum() -> None:
    lessons = load_lessons(Path("content/lessons"))

    assert len(lessons) == 16
    assert len({lesson.id for lesson in lessons}) == len(lessons)
    assert lessons[0].id == "py-001-values-variables"
    assert all(lesson.exercise.tests for lesson in lessons)
    assert all(isinstance(lesson.hints, tuple) for lesson in lessons)
