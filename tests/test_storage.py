from pathlib import Path

from learning_app.storage import ProgressStore


def test_storage_migrates_and_persists_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "progress.sqlite"
    store = ProgressStore(db_path)

    store.save_display_name("Ada")
    store.record_attempt(
        lesson_id="py-001-values-variables",
        code="x = 1",
        passed=True,
        stdout="ok",
        stderr="",
    )

    reopened = ProgressStore(db_path)
    progress = reopened.get_lesson_progress("py-001-values-variables")

    assert reopened.get_display_name() == "Ada"
    assert progress.completed is True
    assert progress.attempts == 1
    assert reopened.recent_attempts()[0].lesson_id == "py-001-values-variables"


def test_storage_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "progress.sqlite"

    ProgressStore(db_path)
    ProgressStore(db_path)

    assert db_path.exists()
