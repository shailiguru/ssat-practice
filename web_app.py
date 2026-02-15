#!/usr/bin/env python3
"""SSAT Practice Test — Streamlit Web Application."""

import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import streamlit as st

# Backend imports (unchanged modules)
import config
from config import LEVEL_CONFIGS, DRILL_TOPICS, QUESTION_TYPE_DISPLAY
from database import Database
from models import Answer, Question, SectionResult, Student, TestSession, TopicMastery, WritingSample
from question_generator import QuestionGenerator, QuestionGenerationError
from question_cache import QuestionCache, LEVEL_TYPES
from scoring import (
    calculate_raw_score, estimate_scaled_score, lookup_percentile,
    compute_topic_breakdown, map_section_name_to_score_field,
)
from leveling import LevelingEngine
from progress import ProgressTracker
from writing import ELEMENTARY_PROMPTS, MIDDLE_PROMPTS


# =====================================================================
# Section 1: Page Config & Initialization
# =====================================================================

st.set_page_config(
    page_title="SSAT Practice Test",
    page_icon="pencil2",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database once per session
if "db" not in st.session_state:
    db = Database()
    db.initialize()
    st.session_state.db = db

if "page" not in st.session_state:
    st.session_state.page = "home"

if "student" not in st.session_state:
    st.session_state.student = None


def get_db() -> Database:
    return st.session_state.db


# =====================================================================
# Section 2: Timer Helpers (replaces timer.py)
# =====================================================================

def get_time_remaining() -> Optional[int]:
    start = st.session_state.get("test_section_start_time")
    limit = st.session_state.get("test_section_time_limit", 0)
    if start is None or limit <= 0:
        return None
    elapsed = time.time() - start
    return max(0, int(limit - elapsed))


def is_time_up() -> bool:
    r = get_time_remaining()
    return r is not None and r <= 0


def format_time(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# =====================================================================
# Section 3: Helper Functions
# =====================================================================

def reset_test_state():
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("test_") or k.startswith("q_")]
    for k in keys_to_remove:
        del st.session_state[k]


def get_cache() -> QuestionCache:
    return QuestionCache(get_db(), QuestionGenerator())


def get_leveling() -> LevelingEngine:
    return LevelingEngine(get_db(), st.session_state.student)


def render_question(q_num: int, total: int, question: Question) -> Optional[str]:
    """Render a question and return the selected answer letter or None."""
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Question {q_num} of {total}")
    with col2:
        remaining = get_time_remaining()
        if remaining is not None:
            st.metric("Time Left", format_time(remaining))

    # Reading passage
    if question.passage:
        with st.expander("Reading Passage", expanded=True):
            st.write(question.passage)

    # Question stem
    st.markdown(f"**{question.stem}**")

    # Answer choices as radio
    choices = []
    choice_map = {}
    for letter in ["A", "B", "C", "D", "E"]:
        if letter in question.choices:
            label = f"{letter}) {question.choices[letter]}"
            choices.append(label)
            choice_map[label] = letter

    if not choices:
        st.warning("No answer choices available for this question.")
        return None

    selected_label = st.radio(
        "Select your answer:",
        choices,
        index=None,
        key=f"q_{q_num}_{question.id}",
    )

    return choice_map.get(selected_label) if selected_label else None


def record_answer(question: Question, selected: Optional[str]) -> Answer:
    student = st.session_state.student
    session = st.session_state.test_session
    q_start = st.session_state.get("test_q_start_time", time.time())

    is_correct = (
        selected is not None
        and selected.upper() == question.correct_answer.upper()
    )

    answer = Answer(
        session_id=session.id,
        question_id=question.id,
        student_id=student.id,
        selected_answer=selected,
        is_correct=is_correct if selected else False,
        time_spent_seconds=time.time() - q_start,
        answered_at=datetime.now().isoformat(),
    )
    return answer


def skip_remaining_questions():
    questions = st.session_state.test_questions
    idx = st.session_state.test_index
    student = st.session_state.student
    session = st.session_state.test_session

    for q in questions[idx:]:
        answer = Answer(
            session_id=session.id,
            question_id=q.id,
            student_id=student.id,
            selected_answer=None,
            is_correct=False,
            time_spent_seconds=0,
            answered_at=datetime.now().isoformat(),
        )
        st.session_state.test_answers.append(answer)


def render_section_result(result: SectionResult):
    cols = st.columns(4)
    with cols[0]:
        st.metric("Raw Score", f"{result.raw_score:.1f}/{result.total_questions}")
    with cols[1]:
        st.metric("Scaled Score", result.scaled_score)
    with cols[2]:
        st.metric("Est. Percentile", f"{result.percentile}%")
    with cols[3]:
        acc = result.correct_count / result.total_questions if result.total_questions > 0 else 0
        st.metric("Accuracy", f"{acc:.0%}")

    c1, c2, c3 = st.columns(3)
    c1.success(f"Correct: {result.correct_count}")
    c2.error(f"Incorrect: {result.wrong_count}")
    c3.info(f"Skipped: {result.skipped_count}")


def score_current_section() -> SectionResult:
    student = st.session_state.student
    sections = st.session_state.test_sections
    idx = st.session_state.test_section_idx
    section = sections[idx]
    answers = st.session_state.test_answers
    questions = st.session_state.test_questions
    session = st.session_state.test_session
    db = get_db()

    raw, correct, wrong, skipped = calculate_raw_score(answers, student.level)
    scaled = estimate_scaled_score(raw, section.question_count, student.level)
    percentile = lookup_percentile(scaled, student.level, section.name, student.grade)

    for a in answers:
        a.session_id = session.id
        db.save_answer(a)

    total_time = sum(a.time_spent_seconds for a in answers)

    return SectionResult(
        section_name=section.name,
        raw_score=raw, scaled_score=scaled, percentile=percentile,
        total_questions=section.question_count,
        correct_count=correct, wrong_count=wrong, skipped_count=skipped,
        time_used_seconds=total_time, answers=list(answers),
    )


# =====================================================================
# Section 4: Sidebar Navigation
# =====================================================================

def render_sidebar():
    with st.sidebar:
        st.title("SSAT Practice")
        st.caption("Personalized SSAT Prep")

        if st.session_state.student:
            s = st.session_state.student
            st.info(f"**{s.name}** | Grade {s.grade} | {s.level.title()}")
            st.divider()

            if st.button("Practice Test (Full)", use_container_width=True, key="nav_full"):
                reset_test_state()
                st.session_state.page = "full_test"
                st.rerun()
            if st.button("Section Practice", use_container_width=True, key="nav_section"):
                reset_test_state()
                st.session_state.page = "section_practice"
                st.rerun()
            if st.button("Quick Drill", use_container_width=True, key="nav_drill"):
                reset_test_state()
                st.session_state.page = "quick_drill"
                st.rerun()
            if st.button("Review Missed", use_container_width=True, key="nav_review"):
                st.session_state.page = "review"
                st.rerun()
            if st.button("Writing Practice", use_container_width=True, key="nav_writing"):
                st.session_state.page = "writing"
                st.rerun()
            if st.button("Progress & Scores", use_container_width=True, key="nav_progress"):
                st.session_state.page = "progress"
                st.rerun()

            st.divider()
            if st.button("Switch Profile", use_container_width=True, key="nav_switch"):
                st.session_state.student = None
                st.session_state.page = "profile"
                st.rerun()
            if st.button("Settings", use_container_width=True, key="nav_settings"):
                st.session_state.page = "settings"
                st.rerun()
        else:
            st.warning("No profile selected")


# =====================================================================
# Section 5: Profile Page
# =====================================================================

def page_profile():
    st.header("Select or Create Profile")
    db = get_db()
    students = db.list_students()

    if students:
        st.subheader("Existing Profiles")
        for s in students:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{s.name}** — Grade {s.grade}, {s.level.title()} Level")
            with col2:
                if st.button("Select", key=f"sel_{s.id}"):
                    st.session_state.student = s
                    st.session_state.page = "home"
                    st.rerun()

    st.divider()
    st.subheader("Create New Profile")
    with st.form("new_profile"):
        name = st.text_input("Student's name")
        grade = st.number_input("Current grade", min_value=3, max_value=8, value=4)
        submitted = st.form_submit_button("Create Profile")

        if submitted and name.strip():
            level = "elementary" if grade <= 4 else "middle"
            student = db.create_student(name.strip(), int(grade), level)
            st.session_state.student = student
            st.session_state.page = "home"
            st.rerun()
        elif submitted:
            st.error("Please enter a name.")


# =====================================================================
# Section 6: Home Page
# =====================================================================

def page_home():
    s = st.session_state.student
    st.header("SSAT Practice Test")
    st.markdown("**Personalized SSAT Prep for Success**")
    st.write(f"Welcome, **{s.name}**! Use the sidebar to start practicing.")

    level_config = LEVEL_CONFIGS.get(s.level)
    if level_config:
        st.info(f"**{level_config.display_name}** | "
                f"Sections: {', '.join(sec.name for sec in level_config.sections)} | "
                f"Score range: {level_config.score_min}-{level_config.score_max} per section")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Quick Start**")
        st.write("Try a **Quick Drill** to warm up on a specific topic.")
    with col2:
        st.markdown("**Build Endurance**")
        st.write("Use **Section Practice** to practice full timed sections.")
    with col3:
        st.markdown("**Full Simulation**")
        st.write("Take a **Full Practice Test** to simulate the real SSAT.")


# =====================================================================
# Section 7: Quick Drill
# =====================================================================

def page_quick_drill():
    student = st.session_state.student
    phase = st.session_state.get("test_phase", "setup")

    if phase == "setup":
        _drill_setup()
    elif phase == "question":
        _drill_question()
    elif phase == "feedback":
        _drill_feedback()
    elif phase == "complete":
        _drill_complete()


def _drill_setup():
    student = st.session_state.student
    st.header("Quick Drill")

    categories = list(DRILL_TOPICS.keys()) + ["Mixed (all types)"]
    cat = st.selectbox("Category", categories)

    if cat == "Mixed (all types)":
        selected_types = LEVEL_TYPES.get(student.level, ["synonym"])
    else:
        topic_options = DRILL_TOPICS[cat]
        if len(topic_options) > 1:
            display_options = [QUESTION_TYPE_DISPLAY.get(t, t.title()) for t in topic_options] + ["Mix all"]
            picked = st.selectbox("Topic", display_options)
            if picked == "Mix all":
                selected_types = topic_options
            else:
                idx = display_options.index(picked)
                selected_types = [topic_options[idx]]
        else:
            selected_types = topic_options

    count = st.slider("Number of questions", config.DRILL_MIN_QUESTIONS, config.DRILL_MAX_QUESTIONS, config.DRILL_DEFAULT_QUESTIONS)
    use_timer = st.checkbox("Use timer", value=False)

    if st.button("Start Drill", type="primary"):
        cache = get_cache()
        engine = get_leveling()
        difficulty_map = engine.get_difficulty_map()

        questions: List[Question] = []
        per_type = max(1, count // len(selected_types))
        remainder = count - per_type * len(selected_types)

        with st.spinner("Loading questions..."):
            for i, qtype in enumerate(selected_types):
                n = per_type + (1 if i < remainder else 0)
                diff = difficulty_map.get(qtype, 3)
                qs = cache.get_questions(student.id, qtype, student.level, int(diff), n, student.grade)
                questions.extend(qs)

        if not questions:
            st.error("No questions available. Go to Settings > Pre-generate questions first.")
            return

        questions = questions[:count]

        session = TestSession(
            student_id=student.id, level=student.level, grade=student.grade,
            mode="quick_drill", started_at=datetime.now().isoformat(),
        )
        session = get_db().create_session(session)

        from config import SectionConfig
        st.session_state.test_session = session
        st.session_state.test_questions = questions
        st.session_state.test_answers = []
        st.session_state.test_index = 0
        st.session_state.test_instant_feedback = True
        st.session_state.test_drill_types = selected_types
        st.session_state.test_drill_start = time.time()
        st.session_state.test_section_start_time = time.time() if use_timer else None
        st.session_state.test_section_time_limit = count * 120 if use_timer else 0
        st.session_state.test_sections = [SectionConfig("Quick Drill", count, 0, tuple(selected_types))]
        st.session_state.test_section_idx = 0
        st.session_state.test_phase = "question"
        st.session_state.test_q_start_time = time.time()
        st.rerun()


def _drill_question():
    questions = st.session_state.test_questions
    idx = st.session_state.test_index

    if is_time_up():
        st.warning("Time's up!")
        skip_remaining_questions()
        st.session_state.test_phase = "complete"
        st.rerun()
        return

    if idx >= len(questions):
        st.session_state.test_phase = "complete"
        st.rerun()
        return

    question = questions[idx]
    st.session_state.test_q_start_time = st.session_state.get("test_q_start_time", time.time())

    selected = render_question(idx + 1, len(questions), question)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Submit Answer", type="primary", key=f"submit_{idx}"):
            answer = record_answer(question, selected)
            st.session_state.test_answers.append(answer)
            st.session_state.test_last_answer = answer
            st.session_state.test_last_question = question
            st.session_state.test_phase = "feedback"
            st.rerun()
    with col2:
        if st.button("Skip", key=f"skip_{idx}"):
            answer = record_answer(question, None)
            st.session_state.test_answers.append(answer)
            st.session_state.test_last_answer = answer
            st.session_state.test_last_question = question
            st.session_state.test_phase = "feedback"
            st.rerun()


def _drill_feedback():
    answer = st.session_state.test_last_answer
    question = st.session_state.test_last_question

    st.markdown(f"**{question.stem}**")

    if answer.selected_answer is None:
        st.info("Skipped")
    elif answer.is_correct:
        st.success(f"Correct! The answer is **{question.correct_answer}) {question.choices.get(question.correct_answer, '')}**")
    else:
        st.error(f"Incorrect. You chose **{answer.selected_answer}**. "
                 f"The correct answer is **{question.correct_answer}) {question.choices.get(question.correct_answer, '')}**")

    if question.explanation:
        st.caption(question.explanation)

    if st.button("Next Question", type="primary"):
        st.session_state.test_index += 1
        st.session_state.test_q_start_time = time.time()
        st.session_state.test_phase = "question"
        st.rerun()


def _drill_complete():
    answers = st.session_state.test_answers
    questions = st.session_state.test_questions
    student = st.session_state.student
    session = st.session_state.test_session
    elapsed = time.time() - st.session_state.get("test_drill_start", time.time())

    raw, correct, wrong, skipped = calculate_raw_score(answers, student.level)

    session.completed_at = datetime.now().isoformat()
    get_db().update_session(session)

    # Update mastery
    try:
        engine = get_leveling()
        events = engine.update_after_answers(answers, questions)
    except Exception:
        events = []

    st.header("Quick Drill Complete!")

    accuracy = correct / len(questions) if questions else 0
    if accuracy >= 0.85:
        st.success("Excellent work!")
    elif accuracy >= 0.60:
        st.info("Good effort! Keep practicing.")
    else:
        st.warning("Keep working at it — you'll improve!")

    cols = st.columns(3)
    cols[0].metric("Score", f"{correct}/{len(questions)} ({accuracy:.0%})")
    cols[1].metric("Time", format_time(int(elapsed)))
    cols[2].metric("Skipped", skipped)

    for event in events:
        st.success(event)

    if st.button("Back to Home", type="primary"):
        reset_test_state()
        st.session_state.page = "home"
        st.rerun()


# =====================================================================
# Section 8: Full Test
# =====================================================================

def page_full_test():
    phase = st.session_state.get("test_phase", "setup")

    if phase == "setup":
        _fulltest_setup()
    elif phase == "section_intro":
        _fulltest_section_intro()
    elif phase == "question":
        _fulltest_question()
    elif phase == "section_complete":
        _fulltest_section_complete()
    elif phase == "test_complete":
        _fulltest_complete()


def _fulltest_setup():
    student = st.session_state.student
    level_config = LEVEL_CONFIGS.get(student.level)
    if not level_config:
        st.error(f"Unknown level: {student.level}")
        return

    st.header(f"Full {level_config.display_name} Practice Test")
    total_time = sum(s.time_minutes for s in level_config.sections)
    st.write(f"**{len(level_config.sections)} sections** | **{total_time} minutes** total")

    for sec in level_config.sections:
        st.write(f"- {sec.name}: {sec.question_count} questions, {sec.time_minutes} min")

    if st.button("Begin Test", type="primary"):
        session = TestSession(
            student_id=student.id, level=student.level, grade=student.grade,
            mode="full_test", started_at=datetime.now().isoformat(),
        )
        session = get_db().create_session(session)

        st.session_state.test_session = session
        st.session_state.test_sections = list(level_config.sections)
        st.session_state.test_section_idx = 0
        st.session_state.test_section_results = []
        st.session_state.test_all_answers = []
        st.session_state.test_all_questions = []
        st.session_state.test_phase = "section_intro"
        st.rerun()


def _fulltest_section_intro():
    sections = st.session_state.test_sections
    idx = st.session_state.test_section_idx

    if idx >= len(sections):
        st.session_state.test_phase = "test_complete"
        st.rerun()
        return

    section = sections[idx]
    st.header(f"Section {idx + 1}: {section.name}")
    st.write(f"**{section.question_count} questions** | **{section.time_minutes} minutes**")
    st.info("Select A-E for each question. Click Skip to move on.")

    if st.button("Start Section", type="primary"):
        student = st.session_state.student
        cache = get_cache()
        engine = get_leveling()
        difficulty_map = engine.get_difficulty_map()

        with st.spinner("Loading questions..."):
            questions = cache.get_mixed_questions(
                student.id, section, student.level, difficulty_map, student.grade
            )

        if not questions:
            st.error("No questions available. Generate questions in Settings first.")
            return

        st.session_state.test_questions = questions
        st.session_state.test_answers = []
        st.session_state.test_index = 0
        st.session_state.test_section_start_time = time.time()
        st.session_state.test_section_time_limit = section.time_minutes * 60
        st.session_state.test_instant_feedback = False
        st.session_state.test_q_start_time = time.time()
        st.session_state.test_phase = "question"
        st.rerun()


def _fulltest_question():
    questions = st.session_state.test_questions
    idx = st.session_state.test_index

    if is_time_up():
        st.warning("Time's up! Remaining questions will be marked as skipped.")
        skip_remaining_questions()
        st.session_state.test_phase = "section_complete"
        st.rerun()
        return

    if idx >= len(questions):
        st.session_state.test_phase = "section_complete"
        st.rerun()
        return

    question = questions[idx]
    st.session_state.test_q_start_time = st.session_state.get("test_q_start_time", time.time())

    selected = render_question(idx + 1, len(questions), question)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Submit Answer", type="primary", key=f"ft_submit_{idx}"):
            answer = record_answer(question, selected)
            st.session_state.test_answers.append(answer)
            st.session_state.test_index += 1
            st.session_state.test_q_start_time = time.time()
            st.rerun()
    with col2:
        if st.button("Skip", key=f"ft_skip_{idx}"):
            answer = record_answer(question, None)
            st.session_state.test_answers.append(answer)
            st.session_state.test_index += 1
            st.session_state.test_q_start_time = time.time()
            st.rerun()


def _fulltest_section_complete():
    result = score_current_section()
    st.session_state.test_section_results.append(result)
    st.session_state.test_all_answers.extend(st.session_state.test_answers)
    st.session_state.test_all_questions.extend(st.session_state.test_questions)

    section = st.session_state.test_sections[st.session_state.test_section_idx]
    st.header(f"Section Complete: {section.name}")
    render_section_result(result)

    next_idx = st.session_state.test_section_idx + 1
    if next_idx < len(st.session_state.test_sections):
        if st.button("Continue to Next Section", type="primary"):
            st.session_state.test_section_idx = next_idx
            st.session_state.test_phase = "section_intro"
            st.rerun()
    else:
        if st.button("View Full Score Report", type="primary"):
            st.session_state.test_phase = "test_complete"
            st.rerun()


def _fulltest_complete():
    db = get_db()
    student = st.session_state.student
    session = st.session_state.test_session
    section_results = st.session_state.test_section_results
    all_answers = st.session_state.test_all_answers
    all_questions = st.session_state.test_all_questions

    # Aggregate scores
    for result in section_results:
        field = map_section_name_to_score_field(result.section_name)
        current_raw = getattr(session, f"{field}_raw", None)
        if current_raw is not None and field == "quantitative":
            setattr(session, f"{field}_raw", current_raw + result.raw_score)
            current_scaled = getattr(session, f"{field}_scaled", 0) or 0
            setattr(session, f"{field}_scaled", (current_scaled + result.scaled_score) // 2)
            current_pct = getattr(session, f"{field}_percentile", 0) or 0
            setattr(session, f"{field}_percentile", (current_pct + result.percentile) // 2)
        else:
            setattr(session, f"{field}_raw", result.raw_score)
            setattr(session, f"{field}_scaled", result.scaled_score)
            setattr(session, f"{field}_percentile", result.percentile)

    total = sum(getattr(session, f"{f}_scaled", 0) or 0 for f in ("verbal", "quantitative", "reading"))
    session.total_scaled = total
    session.completed_at = datetime.now().isoformat()
    db.update_session(session)

    # Update mastery
    try:
        engine = get_leveling()
        events = engine.update_after_answers(all_answers, all_questions)
    except Exception:
        events = []

    topic_breakdown = compute_topic_breakdown(all_answers, all_questions)

    # Render report
    st.header("SSAT Practice Test — Score Report")
    level_config = LEVEL_CONFIGS.get(session.level)
    st.subheader(f"{student.name} — Grade {student.grade} — {level_config.display_name if level_config else session.level}")

    import pandas as pd
    rows = [{"Section": r.section_name, "Raw": f"{r.raw_score:.1f}/{r.total_questions}",
             "Scaled": r.scaled_score, "Est. %ile": f"{r.percentile}%"} for r in section_results]
    st.table(pd.DataFrame(rows))

    st.metric("Total Scaled Score", total)

    total_correct = sum(r.correct_count for r in section_results)
    total_wrong = sum(r.wrong_count for r in section_results)
    total_skipped = sum(r.skipped_count for r in section_results)
    total_q = sum(r.total_questions for r in section_results)
    st.write(f"Questions: {total_correct + total_wrong}/{total_q} answered | "
             f"Correct: **{total_correct}** | Incorrect: **{total_wrong}** | Skipped: **{total_skipped}**")

    if topic_breakdown:
        st.subheader("Topic Breakdown")
        for topic, data in sorted(topic_breakdown.items()):
            acc = data.get("accuracy", 0)
            name = QUESTION_TYPE_DISPLAY.get(topic, topic.title())
            if acc >= 0.85:
                st.success(f"**{name}**: {acc:.0%}")
            elif acc >= 0.60:
                st.warning(f"**{name}**: {acc:.0%}")
            else:
                st.error(f"**{name}**: {acc:.0%}")

    for event in events:
        st.success(event)

    if st.button("Back to Home", type="primary"):
        reset_test_state()
        st.session_state.page = "home"
        st.rerun()


# =====================================================================
# Section 9: Section Practice
# =====================================================================

def page_section_practice():
    phase = st.session_state.get("test_phase", "setup")

    if phase == "setup":
        _section_setup()
    elif phase == "section_intro":
        _fulltest_section_intro()
    elif phase == "question":
        _fulltest_question()
    elif phase == "section_complete":
        _section_practice_complete()


def _section_setup():
    student = st.session_state.student
    level_config = LEVEL_CONFIGS.get(student.level)
    if not level_config:
        st.error(f"Unknown level: {student.level}")
        return

    st.header("Section Practice")
    section_names = [f"{s.name} ({s.question_count} questions, {s.time_minutes} min)" for s in level_config.sections]
    choice = st.selectbox("Choose a section", section_names)
    idx = section_names.index(choice)
    section = level_config.sections[idx]

    if st.button("Start Section", type="primary"):
        session = TestSession(
            student_id=student.id, level=student.level, grade=student.grade,
            mode="section_practice", started_at=datetime.now().isoformat(),
        )
        session = get_db().create_session(session)

        st.session_state.test_session = session
        st.session_state.test_sections = [section]
        st.session_state.test_section_idx = 0
        st.session_state.test_section_results = []
        st.session_state.test_all_answers = []
        st.session_state.test_all_questions = []
        st.session_state.test_phase = "section_intro"
        st.rerun()


def _section_practice_complete():
    result = score_current_section()
    student = st.session_state.student
    session = st.session_state.test_session

    section = st.session_state.test_sections[0]
    field = map_section_name_to_score_field(section.name)
    setattr(session, f"{field}_raw", result.raw_score)
    setattr(session, f"{field}_scaled", result.scaled_score)
    setattr(session, f"{field}_percentile", result.percentile)
    session.total_scaled = result.scaled_score
    session.completed_at = datetime.now().isoformat()
    get_db().update_session(session)

    # Update mastery
    try:
        engine = get_leveling()
        engine.update_after_answers(st.session_state.test_answers, st.session_state.test_questions)
    except Exception:
        pass

    st.header(f"Section Complete: {section.name}")
    render_section_result(result)

    if st.button("Back to Home", type="primary"):
        reset_test_state()
        st.session_state.page = "home"
        st.rerun()


# =====================================================================
# Section 10: Review
# =====================================================================

def page_review():
    student = st.session_state.student
    db = get_db()

    st.header("Review Missed Questions")

    tab1, tab2, tab3 = st.tabs(["Recent Mistakes", "By Topic", "Frequently Missed"])

    with tab1:
        wrong = db.get_wrong_answers_for_student(student.id, limit=20)
        if not wrong:
            st.success("No missed questions! Great job!")
        else:
            st.write(f"Showing {len(wrong)} recent mistakes:")
            for i, (answer, question) in enumerate(wrong, 1):
                with st.expander(f"Q{i}: {question.stem[:80]}..."):
                    if question.passage:
                        st.caption(question.passage[:200] + "...")
                    st.markdown(f"**{question.stem}**")
                    for letter in ["A", "B", "C", "D", "E"]:
                        if letter in question.choices:
                            prefix = ""
                            if letter == question.correct_answer:
                                prefix = "**correct** "
                            elif letter == answer.selected_answer:
                                prefix = "~~your answer~~ "
                            st.write(f"{letter}) {prefix}{question.choices[letter]}")
                    if answer.selected_answer:
                        st.error(f"You chose: {answer.selected_answer}")
                    else:
                        st.info("You skipped this question.")
                    st.success(f"Correct answer: {question.correct_answer}) {question.choices.get(question.correct_answer, '')}")
                    if question.explanation:
                        st.caption(f"Explanation: {question.explanation}")

    with tab2:
        wrong_all = db.get_wrong_answers_for_student(student.id, limit=200)
        if not wrong_all:
            st.success("No mistakes to analyze!")
        else:
            topic_errors: Dict[str, int] = {}
            for answer, question in wrong_all:
                topic = question.question_type
                topic_errors[topic] = topic_errors.get(topic, 0) + 1

            import pandas as pd
            df = pd.DataFrame([
                {"Topic": QUESTION_TYPE_DISPLAY.get(t, t.title()), "Errors": c}
                for t, c in sorted(topic_errors.items(), key=lambda x: -x[1])
            ])
            st.bar_chart(df.set_index("Topic"))
            st.table(df)

    with tab3:
        freq = db.get_frequently_missed_questions(student.id, min_wrong_count=2)
        if not freq:
            st.success("No frequently missed questions!")
        else:
            st.write(f"Questions you've missed 2+ times ({len(freq)} total):")
            for i, (question, wrong_count) in enumerate(freq, 1):
                with st.expander(f"Missed {wrong_count}x: {question.stem[:80]}..."):
                    st.markdown(f"**{question.stem}**")
                    for letter in ["A", "B", "C", "D", "E"]:
                        if letter in question.choices:
                            st.write(f"{letter}) {question.choices[letter]}")
                    st.success(f"Correct: {question.correct_answer}) {question.choices.get(question.correct_answer, '')}")
                    if question.explanation:
                        st.caption(question.explanation)


# =====================================================================
# Section 11: Writing Practice
# =====================================================================

def page_writing():
    student = st.session_state.student
    db = get_db()
    phase = st.session_state.get("writing_phase", "menu")

    if phase == "menu":
        st.header("Writing Practice")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("New Writing Prompt", type="primary", use_container_width=True):
                prompts = ELEMENTARY_PROMPTS if student.level == "elementary" else MIDDLE_PROMPTS
                st.session_state.writing_prompt = random.choice(prompts)
                st.session_state.writing_phase = "writing"
                st.session_state.writing_start_time = time.time()
                st.rerun()
        with col2:
            if st.button("View Past Submissions", use_container_width=True):
                st.session_state.writing_phase = "view_past"
                st.rerun()

    elif phase == "writing":
        ptype, prompt_text = st.session_state.writing_prompt
        level_config = LEVEL_CONFIGS.get(student.level)
        time_min = level_config.writing_time_minutes if level_config else 15

        st.header("Writing Prompt")
        st.info(prompt_text)
        elapsed = time.time() - st.session_state.writing_start_time
        st.caption(f"Time elapsed: {format_time(int(elapsed))} | Recommended: {time_min} minutes")

        response = st.text_area("Write your response:", height=400, key="writing_response")

        if st.button("Submit for Feedback", type="primary"):
            if response.strip():
                with st.spinner("Getting AI feedback on your writing..."):
                    try:
                        gen = QuestionGenerator()
                        feedback = gen.generate_writing_feedback(prompt_text, response, student.level, student.grade)
                    except Exception as e:
                        feedback = f"Great effort! Your writing has been saved. (Feedback unavailable: {e})"

                sample = WritingSample(
                    student_id=student.id, prompt=prompt_text,
                    response=response, feedback=feedback,
                )
                db.save_writing_sample(sample)
                st.session_state.writing_feedback = feedback
                st.session_state.writing_phase = "feedback"
                st.rerun()
            else:
                st.warning("Please write something before submitting.")

        if st.button("Back"):
            st.session_state.writing_phase = "menu"
            st.rerun()

    elif phase == "feedback":
        st.header("Writing Feedback")
        st.markdown(st.session_state.writing_feedback)
        st.success("Your writing has been saved!")
        if st.button("Back to Writing Menu", type="primary"):
            st.session_state.writing_phase = "menu"
            st.rerun()

    elif phase == "view_past":
        samples = db.get_writing_samples(student.id, limit=10)
        st.header("Past Writing Samples")
        if not samples:
            st.info("No writing samples yet. Try writing one!")
        else:
            for s in samples:
                date = s.created_at[:10] if s.created_at else "?"
                with st.expander(f"{date} — {s.prompt[:60]}..."):
                    st.markdown(f"**Prompt:** {s.prompt}")
                    st.markdown(f"**Your Response:**\n\n{s.response}")
                    if s.feedback:
                        st.markdown(f"**Feedback:**\n\n{s.feedback}")

        if st.button("Back to Writing Menu"):
            st.session_state.writing_phase = "menu"
            st.rerun()


# =====================================================================
# Section 12: Progress Dashboard
# =====================================================================

def page_progress():
    student = st.session_state.student
    db = get_db()

    st.header(f"Progress Report — {student.name}")
    st.caption(f"Grade {student.grade} | {student.level.title()} Level")

    stats = db.get_student_stats(student.id)
    sessions = db.get_sessions_for_student(student.id, limit=20)
    mastery = db.get_topic_mastery(student.id)

    # Stats cards
    cols = st.columns(4)
    cols[0].metric("Full Tests", stats["full_tests"])
    cols[1].metric("Section Practices", stats["section_practices"])
    cols[2].metric("Drills", stats["drills"])
    cols[3].metric("Total Questions", f"{stats['total_answers']:,}")

    # Score trend
    full_tests = [s for s in sessions if s.mode == "full_test" and s.total_scaled]
    if full_tests:
        st.subheader("Score Trend")
        import pandas as pd
        df = pd.DataFrame([
            {"Date": s.started_at[:10] if s.started_at else "?", "Score": s.total_scaled}
            for s in reversed(full_tests)
        ])
        st.line_chart(df.set_index("Date"))

    # Topic mastery
    active_mastery = [m for m in mastery if m.total_attempted > 0]
    if active_mastery:
        st.subheader("Topic Mastery")
        import pandas as pd
        rows = []
        for m in active_mastery:
            acc = m.total_correct / m.total_attempted
            name = QUESTION_TYPE_DISPLAY.get(m.topic_tag, m.topic_tag.title())
            status = "Strong" if acc >= 0.85 else ("Needs Work" if acc >= 0.60 else "Weak")
            rows.append({"Topic": name, "Accuracy": f"{acc:.0%}", "Attempted": m.total_attempted,
                         "Difficulty": f"{m.difficulty_level:.1f}", "Status": status})
        st.table(pd.DataFrame(rows))

    # Recommendations
    tracker = ProgressTracker(db, student)
    recs = tracker.get_recommendations(stats, sessions, mastery)
    if recs:
        st.subheader("Recommendations")
        for r in recs:
            st.write(f"- {r}")


# =====================================================================
# Section 13: Settings
# =====================================================================

def page_settings():
    student = st.session_state.student
    db = get_db()

    st.header("Settings")

    # Timer
    timer_on = st.toggle("Timer Enabled", value=config.TIMER_ENABLED)
    config.TIMER_ENABLED = timer_on

    st.divider()

    # Grade
    st.subheader("Adjust Grade Level")
    new_grade = st.number_input("Grade", min_value=3, max_value=8, value=student.grade)
    if int(new_grade) != student.grade:
        student.grade = int(new_grade)
        student.level = "elementary" if new_grade <= 4 else "middle"
        db.update_student(student)
        st.success(f"Updated to Grade {new_grade} ({student.level.title()} Level)")

    st.divider()

    # Question pool
    st.subheader("Question Pool")
    if st.button("View Pool Stats"):
        cache = get_cache()
        pool_stats = cache.get_pool_stats(student.id, student.level)
        for qtype, count in sorted(pool_stats.items()):
            name = QUESTION_TYPE_DISPLAY.get(qtype, qtype.title())
            if count >= 10:
                st.success(f"**{name}**: {count} available")
            elif count >= 5:
                st.warning(f"**{name}**: {count} available")
            else:
                st.error(f"**{name}**: {count} available")

    if st.button("Pre-generate Question Pool"):
        cache = get_cache()
        types = LEVEL_TYPES.get(student.level, [])
        progress_bar = st.progress(0, text="Starting generation...")

        for i, qtype in enumerate(types):
            progress_bar.progress((i) / len(types), text=f"Generating {qtype}...")
            try:
                gen = QuestionGenerator()
                if qtype == "reading_comprehension":
                    new_qs = gen.generate_reading_comprehension(
                        level=student.level, grade=student.grade, difficulty=3,
                        num_passages=3, questions_per_passage=4,
                    )
                else:
                    new_qs = gen.generate_questions(
                        question_type=qtype, level=student.level, grade=student.grade,
                        difficulty=3, count=config.QUESTIONS_PER_BATCH,
                    )
                if new_qs:
                    db.save_questions(new_qs)
                    st.write(f"{QUESTION_TYPE_DISPLAY.get(qtype, qtype)}: {len(new_qs)} generated")
            except Exception as e:
                st.warning(f"{qtype}: failed ({e})")
            progress_bar.progress((i + 1) / len(types))

        progress_bar.progress(1.0, text="Done!")
        st.success("Batch generation complete!")

    st.divider()

    # Reset
    st.subheader("Reset Progress")
    st.warning("This will permanently delete all test history and mastery data for this student.")
    if st.button("Reset All Progress", type="secondary"):
        st.session_state.confirm_reset = True

    if st.session_state.get("confirm_reset"):
        st.error("Are you absolutely sure? This cannot be undone.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, Delete Everything", type="primary"):
                db.conn.execute("DELETE FROM answers WHERE student_id = ?", (student.id,))
                db.conn.execute("DELETE FROM test_sessions WHERE student_id = ?", (student.id,))
                db.conn.execute("DELETE FROM topic_mastery WHERE student_id = ?", (student.id,))
                db.conn.execute("DELETE FROM writing_samples WHERE student_id = ?", (student.id,))
                db.conn.commit()
                st.session_state.confirm_reset = False
                st.success("Progress has been reset.")
                st.rerun()
        with col2:
            if st.button("Cancel"):
                st.session_state.confirm_reset = False
                st.rerun()


# =====================================================================
# Section 14: Main Router
# =====================================================================

def main():
    render_sidebar()

    if st.session_state.student is None:
        page_profile()
        return

    page = st.session_state.page

    routes = {
        "home": page_home,
        "profile": page_profile,
        "full_test": page_full_test,
        "section_practice": page_section_practice,
        "quick_drill": page_quick_drill,
        "review": page_review,
        "writing": page_writing,
        "progress": page_progress,
        "settings": page_settings,
    }

    handler = routes.get(page, page_home)
    handler()


if __name__ == "__main__":
    main()
