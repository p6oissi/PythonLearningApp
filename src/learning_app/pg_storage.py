from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extensions

from learning_app.storage import Attempt, LessonProgress, utc_now


class ProgressStore:
    def __init__(self, user_id: str, dsn: str, db_path=None) -> None:
        self._user_id = user_id
        self._dsn = dsn
        self._migrate()

    @contextmanager
    def _connect(self) -> Generator[psycopg2.extensions.connection, None, None]:
        conn = psycopg2.connect(self._dsn, sslmode="require")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_display_name(self) -> str:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT display_name FROM learner_profile WHERE user_id = %s",
                    (self._user_id,),
                )
                row = cur.fetchone()
        return row[0] if row else "Learner"

    def save_display_name(self, display_name: str) -> None:
        cleaned = display_name.strip() or "Learner"
        now = utc_now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learner_profile (user_id, display_name, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        updated_at   = EXCLUDED.updated_at
                    """,
                    (self._user_id, cleaned, now, now),
                )

    def get_progress(self) -> dict[str, LessonProgress]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT lesson_id, completed, completed_at, last_code, attempts
                    FROM lesson_progress
                    WHERE user_id = %s
                    """,
                    (self._user_id,),
                )
                rows = cur.fetchall()
        return {
            row[0]: LessonProgress(
                lesson_id=row[0],
                completed=bool(row[1]),
                completed_at=row[2],
                last_code=row[3] or "",
                attempts=int(row[4] or 0),
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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lesson_progress
                        (user_id, lesson_id, completed, completed_at, last_code, attempts, updated_at)
                    VALUES (%s, %s, FALSE, NULL, %s, 0, %s)
                    ON CONFLICT (user_id, lesson_id) DO UPDATE SET
                        last_code  = EXCLUDED.last_code,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (self._user_id, lesson_id, code, now),
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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO exercise_attempts
                        (user_id, lesson_id, passed, code, stdout, stderr, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (self._user_id, lesson_id, passed, code, stdout, stderr, now),
                )
                cur.execute(
                    """
                    INSERT INTO lesson_progress
                        (user_id, lesson_id, completed, completed_at, last_code, attempts, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 1, %s)
                    ON CONFLICT (user_id, lesson_id) DO UPDATE SET
                        completed    = CASE
                                         WHEN EXCLUDED.completed THEN TRUE
                                         ELSE lesson_progress.completed
                                       END,
                        completed_at = CASE
                                         WHEN EXCLUDED.completed THEN EXCLUDED.completed_at
                                         ELSE lesson_progress.completed_at
                                       END,
                        last_code    = EXCLUDED.last_code,
                        attempts     = lesson_progress.attempts + 1,
                        updated_at   = EXCLUDED.updated_at
                    """,
                    (self._user_id, lesson_id, passed, now if passed else None, code, now),
                )

    def recent_attempts(self, limit: int = 5) -> list[Attempt]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT lesson_id, passed, stdout, stderr, created_at
                    FROM exercise_attempts
                    WHERE user_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (self._user_id, limit),
                )
                rows = cur.fetchall()
        return [
            Attempt(
                lesson_id=row[0],
                passed=bool(row[1]),
                stdout=row[2] or "",
                stderr=row[3] or "",
                created_at=row[4],
            )
            for row in rows
        ]

    def _migrate(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version    INTEGER NOT NULL PRIMARY KEY,
                        applied_at TEXT    NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS learner_profile (
                        user_id      TEXT NOT NULL PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        created_at   TEXT NOT NULL,
                        updated_at   TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS lesson_progress (
                        user_id      TEXT    NOT NULL,
                        lesson_id    TEXT    NOT NULL,
                        completed    BOOLEAN NOT NULL DEFAULT FALSE,
                        completed_at TEXT,
                        last_code    TEXT    NOT NULL DEFAULT '',
                        attempts     INTEGER NOT NULL DEFAULT 0,
                        updated_at   TEXT    NOT NULL,
                        PRIMARY KEY (user_id, lesson_id)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS exercise_attempts (
                        id         BIGSERIAL PRIMARY KEY,
                        user_id    TEXT    NOT NULL,
                        lesson_id  TEXT    NOT NULL,
                        passed     BOOLEAN NOT NULL,
                        code       TEXT    NOT NULL,
                        stdout     TEXT    NOT NULL DEFAULT '',
                        stderr     TEXT    NOT NULL DEFAULT '',
                        created_at TEXT    NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS ea_user_created
                        ON exercise_attempts (user_id, created_at DESC, id DESC)
                """)
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, applied_at)
                    VALUES (%s, %s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (1, utc_now()),
                )
