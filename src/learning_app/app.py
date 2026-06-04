from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from learning_app.content import Lesson, lessons_by_chapter, load_lessons
from learning_app.runner import check_code, run_code
from learning_app.storage import ProgressStore


DEFAULT_CONTENT_DIR = Path(os.environ.get("LEARNING_APP_CONTENT_DIR", "content/lessons"))
XP_PER_LESSON = 100


def main() -> None:
    st.set_page_config(
        page_title="Python Foundations Lab",
        page_icon="🐍",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_styles()

    store = ProgressStore()
    lessons = load_lessons(DEFAULT_CONTENT_DIR)
    progress = store.get_progress()
    lesson_map = {lesson.id: lesson for lesson in lessons}

    # Default to first incomplete lesson on first load
    if "current_lesson_id" not in st.session_state:
        first_incomplete = next(
            (l for l in lessons if not (progress.get(l.id) and progress[l.id].completed)),
            lessons[0],
        )
        st.session_state["current_lesson_id"] = first_incomplete.id

    # Sidebar may update current_lesson_id when a nav button is clicked
    with st.sidebar:
        _render_sidebar(lessons, progress, store)

    # Read current lesson AFTER sidebar (nav buttons update session state in-pass)
    current_id = st.session_state.get("current_lesson_id", lessons[0].id)
    selected_lesson = lesson_map.get(current_id, lessons[0])

    _render_dashboard(lessons, progress, store)
    st.divider()
    _render_lesson(selected_lesson, store)


def _render_sidebar(lessons: list[Lesson], progress: dict, store: ProgressStore) -> None:
    st.markdown("### 🐍 Python Foundations Lab")

    display_name = st.text_input(
        "name",
        value=store.get_display_name(),
        max_chars=80,
        label_visibility="collapsed",
        placeholder="Your name...",
    )
    if st.button("Save name", use_container_width=True):
        store.save_display_name(display_name)
        st.rerun()

    completed_count = sum(
        1 for l in lessons if progress.get(l.id) and progress[l.id].completed
    )
    xp = completed_count * XP_PER_LESSON
    st.markdown(
        f"<div class='xp-bar'>⚡ <b>{xp} XP</b>&nbsp;&nbsp;·&nbsp;&nbsp;"
        f"{completed_count}/{len(lessons)} complete</div>",
        unsafe_allow_html=True,
    )

    st.divider()

    grouped = lessons_by_chapter(lessons)
    current_id = st.session_state.get("current_lesson_id", "")

    for chapter, chapter_lessons in grouped.items():
        chapter_done = sum(
            1 for l in chapter_lessons if progress.get(l.id) and progress[l.id].completed
        )
        chapter_total = len(chapter_lessons)

        st.markdown(f"<div class='chapter-header'>{chapter}</div>", unsafe_allow_html=True)
        st.progress(chapter_done / chapter_total if chapter_total else 0)

        for lesson in chapter_lessons:
            done = bool(progress.get(lesson.id) and progress[lesson.id].completed)
            is_current = lesson.id == current_id
            icon = "✓" if done else "○"
            prefix = "▶  " if is_current else "    "
            label = f"{prefix}{icon}  {lesson.title}"

            if st.button(label, key=f"nav_{lesson.id}", use_container_width=True):
                st.session_state["current_lesson_id"] = lesson.id


def _render_dashboard(lessons: list[Lesson], progress: dict, store: ProgressStore) -> None:
    completed = [l for l in lessons if progress.get(l.id) and progress[l.id].completed]
    next_lesson = next(
        (l for l in lessons if not (progress.get(l.id) and progress[l.id].completed)),
        lessons[-1],
    )
    total_attempts = sum(p.attempts for p in progress.values())
    recent = store.recent_attempts(limit=5)

    c1, c2, c3 = st.columns(3)
    c1.metric("Completed", f"{len(completed)} / {len(lessons)}")
    c2.metric("XP Earned", f"⚡ {len(completed) * XP_PER_LESSON}")
    c3.metric("Total Attempts", total_attempts)

    st.info(f"**Next up:** {next_lesson.title} — {next_lesson.summary}")

    if recent:
        with st.expander("Recent attempts", expanded=False):
            for attempt in recent:
                status = "✓ passed" if attempt.passed else "✗ needs work"
                st.write(f"{attempt.created_at}: `{attempt.lesson_id}` {status}")


def _render_lesson(lesson: Lesson, store: ProgressStore) -> None:
    lesson_progress = store.get_lesson_progress(lesson.id)

    # Track how many hints are currently unlocked for this lesson
    hints_key = f"hints_shown_{lesson.id}"
    if hints_key not in st.session_state:
        st.session_state[hints_key] = min(lesson_progress.attempts, len(lesson.hints))

    # Header row
    col_title, col_status = st.columns([6, 1])
    with col_title:
        st.header(lesson.title)
        st.caption(f"{lesson.chapter}  ·  {lesson.summary}")
    with col_status:
        if lesson_progress.completed:
            st.success("✓ Complete")

    # What you'll build
    st.info(f"**🎯 What you'll build:** {lesson.outcome}")

    # Lesson body
    st.markdown(lesson.body_markdown)

    # Example
    st.subheader("Example")
    st.code(lesson.example_code, language="python")

    # Exercise
    st.subheader("Exercise")
    with st.container(border=True):
        st.markdown(lesson.exercise.prompt)

    # Code editor + hints side-by-side
    col_code, col_hints = st.columns([3, 1])

    with col_code:
        editor_key = f"code_{lesson.id}"
        initial_code = lesson_progress.last_code or lesson.exercise.starter_code
        code = st.text_area(
            "Your code (press Tab to indent)",
            value=initial_code,
            height=380,
            key=editor_key,
        )
        btn_run, btn_check, _ = st.columns([1, 1, 4])
        run_clicked = btn_run.button("▷  Run", use_container_width=True)
        check_clicked = btn_check.button("✓  Check", type="primary", use_container_width=True)

    with col_hints:
        _render_hints(lesson, hints_key)

    # Results (below both columns)
    if run_clicked:
        store.save_code(lesson.id, code)
        with st.spinner("Running your code..."):
            result = run_code(code)
        _render_run_result(result.stdout, result.stderr, result.exit_code, result.timed_out)

    if check_clicked:
        with st.spinner("Checking your solution..."):
            result = check_code(code, lesson.exercise.tests)

        stderr = result.block_reason if result.blocked else result.stderr
        store.record_attempt(lesson.id, code, result.passed, result.stdout, stderr)

        if not result.passed:
            current_unlocked = st.session_state.get(hints_key, 0)
            if current_unlocked < len(lesson.hints):
                st.session_state[hints_key] = current_unlocked + 1

        _render_check_result(result, lesson.exercise.success_message)

        if result.passed:
            if not lesson_progress.completed:
                st.balloons()
            st.rerun()


def _render_hints(lesson: Lesson, hints_key: str) -> None:
    st.markdown("**💡 Hints**")
    unlocked = st.session_state.get(hints_key, 0)

    if not lesson.hints:
        return

    if unlocked == 0:
        st.caption("Hints unlock after each failed attempt. Give it your best shot first!")
        return

    for i in range(unlocked):
        with st.expander(f"Hint {i + 1} of {len(lesson.hints)}", expanded=(i == unlocked - 1)):
            st.write(lesson.hints[i])

    if unlocked < len(lesson.hints):
        remaining = len(lesson.hints) - unlocked
        st.caption(f"{remaining} more hint{'s' if remaining > 1 else ''} available if needed.")


def _render_run_result(stdout: str, stderr: str, exit_code: int, timed_out: bool) -> None:
    st.subheader("Output")
    if stdout:
        st.code(stdout, language="text")
    if stderr:
        st.error(stderr)
    if timed_out:
        st.warning("Your code ran for too long and was stopped (5 second limit).")
    if not stdout and not stderr and not timed_out:
        st.caption("No output. Did you forget a `print()`?")
    st.caption(f"Exit code: {exit_code}")


def _render_check_result(result, success_message: str) -> None:
    st.subheader("Check Results")
    if result.blocked:
        st.error(f"⛔ {result.block_reason}")
        return

    if result.stdout:
        st.code(result.stdout, language="text")
    if result.stderr:
        st.error(result.stderr)
    if result.timed_out:
        st.warning("The check timed out after 5 seconds.")

    for test in result.tests:
        if test.passed:
            st.success(f"✓  {test.name}")
        else:
            st.error(f"✗  {test.name}: {test.message}")
            if test.hint:
                st.info(f"💡 {test.hint}")

    if result.passed:
        st.success(f"🎉 {success_message}")


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
        /* ── Code editor ────────────────────────────────────────── */
        .stTextArea textarea {
            font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
            font-size: 0.92rem;
            line-height: 1.5;
        }

        /* ── Sidebar: nav buttons ───────────────────────────────── */
        [data-testid="stSidebar"] div[data-testid="stButton"] > button {
            text-align: left !important;
            justify-content: flex-start !important;
            background: transparent !important;
            border: none !important;
            font-size: 0.83rem !important;
            padding: 0.18rem 0.5rem !important;
            white-space: pre-wrap !important;
            color: var(--text-color) !important;
            border-radius: 4px !important;
            font-family: ui-monospace, "SFMono-Regular", Consolas, monospace !important;
            box-shadow: none !important;
            line-height: 1.6 !important;
        }
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
            background: rgba(99, 102, 241, 0.12) !important;
            color: #818cf8 !important;
        }

        /* ── Sidebar: chapter headers ───────────────────────────── */
        .chapter-header {
            font-size: 0.67rem !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.11em !important;
            color: #888 !important;
            margin: 0.85rem 0 0.1rem 0.4rem !important;
            padding: 0 !important;
        }

        /* ── Sidebar: XP bar ────────────────────────────────────── */
        .xp-bar {
            font-size: 0.87rem;
            color: #a5b4fc;
            margin: 0.25rem 0 0 0.4rem;
        }

        /* ── Code blocks ────────────────────────────────────────── */
        .stCodeBlock {
            border-radius: 6px;
        }
        </style>

        <script>
        (function () {
            function enableTab(ta) {
                if (ta._tabReady) return;
                ta._tabReady = true;
                ta.addEventListener('keydown', function (e) {
                    if (e.key !== 'Tab') return;
                    e.preventDefault();
                    var start = this.selectionStart;
                    var end = this.selectionEnd;
                    var newVal = this.value.substring(0, start) + '    ' + this.value.substring(end);
                    var setter = Object.getOwnPropertyDescriptor(
                        HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    setter.call(this, newVal);
                    this.dispatchEvent(new Event('input', { bubbles: true }));
                    this.selectionStart = this.selectionEnd = start + 4;
                });
            }

            function applyAll() {
                document.querySelectorAll('textarea').forEach(enableTab);
            }

            applyAll();
            new MutationObserver(applyAll).observe(document.body, {
                childList: true,
                subtree: true,
            });
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
