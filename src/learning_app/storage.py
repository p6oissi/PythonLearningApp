from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


APP_DATA_ENV = "LEARNING_APP_DATA_DIR"
DEFAULT_PROFILE_ID = 1


@dataclass(frozen=True)
class LessonProgress:
    lesson_id: str
    completed: bool
    completed_at: str | None
    last_code: str
    attempts: int


@dataclass(frozen=True)
class Attempt:
    lesson_id: str
    passed: bool
    created_at: str
    stdout: str
    stderr: str


def default_db_path() -> Path:
    data_dir = Path(os.environ.get(APP_DATA_ENV, "data"))
    return data_dir / "progress.sqlite"


class ProgressStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def get_display_name(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM learner_profile WHERE id = ?",
                (DEFAULT_PROFILE_ID,),
            ).fetchone()
        return row["display_name"] if row else "Learner"

    def save_display_name(self, display_name: str) -> None:
        cleaned = display_name.strip() or "Learner"
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learner_profile (id, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (DEFAULT_PROFILE_ID, cleaned, now, now),
            )

    def get_progress(self) -> dict[str, LessonProgress]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT lesson_id, completed, completed_at, last_code, attempts
                FROM lesson_progress
                """
            ).fetchall()
        return {
            row["lesson_id"]: LessonProgress(
                lesson_id=row["lesson_id"],
                completed=bool(row["completed"]),
                completed_at=row["completed_at"],
                last_code=row["last_code"] or "",
                attempts=int(row["attempts"] or 0),
            )
            for row in rows
        }

    def get_lesson_progress(self, lesson_id: str) -> LessonProgress:
        return self.get_progress().get(
            lesson_id,
            LessonProgress(
                lesson_id=lesson_id,
                completed=False,
                completed_at=None,
                last_code="",
                attempts=0,
            ),
        )

    def save_code(self, lesson_id: str, code: str) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lesson_progress (lesson_id, completed, completed_at, last_code, attempts, updated_at)
                VALUES (?, 0, NULL, ?, 0, ?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    last_code = excluded.last_code,
                    updated_at = excluded.updated_at
                """,
                (lesson_id, code, now),
            )

    def record_attempt(
        self,
        lesson_id: str,
        code: str,
        passed: bool,
        stdout: str,
        stderr: str,
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO exercise_attempts (lesson_id, passed, code, stdout, stderr, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (lesson_id, int(passed), code, stdout, stderr, now),
            )
            conn.execute(
                """
                INSERT INTO lesson_progress (lesson_id, completed, completed_at, last_code, attempts, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    completed = CASE
                        WHEN excluded.completed = 1 THEN 1
                        ELSE lesson_progress.completed
                    END,
                    completed_at = CASE
                        WHEN excluded.completed = 1 THEN excluded.completed_at
                        ELSE lesson_progress.completed_at
                    END,
                    last_code = excluded.last_code,
                    attempts = lesson_progress.attempts + 1,
                    updated_at = excluded.updated_at
                """,
                (lesson_id, int(passed), now if passed else None, code, now),
            )

    def recent_attempts(self, limit: int = 5) -> list[Attempt]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT lesson_id, passed, stdout, stderr, created_at
                FROM exercise_attempts
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            Attempt(
                lesson_id=row["lesson_id"],
                passed=bool(row["passed"]),
                stdout=row["stdout"] or "",
                stderr=row["stderr"] or "",
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learner_profile (
                    id INTEGER PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lesson_progress (
                    lesson_id TEXT PRIMARY KEY,
                    completed INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT,
                    last_code TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exercise_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                VALUES (1, ?)
                """,
                (utc_now(),),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
