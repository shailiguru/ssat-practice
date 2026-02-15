"""Test session orchestration: full tests, section practice, quick drills."""

import time
from datetime import datetime
from typing import Dict, List, Optional

import config
from config import LEVEL_CONFIGS, SectionConfig, DRILL_TOPICS
from database import Database
from models import Answer, Question, SectionResult, Student, TestSession
from question_cache import QuestionCache
from timer import Timer
import scoring
import display


class TestRunner:
    def __init__(self, db: Database, cache: QuestionCache, student: Student):
        self.db = db
        self.cache = cache
        self.student = student

    # ------------------------------------------------------------------
    # Full practice test
    # ------------------------------------------------------------------

    def run_full_test(self) -> None:
        """Run a complete SSAT practice test, section by section."""
        level_config = LEVEL_CONFIGS.get(self.student.level)
        if not level_config:
            display.show_error(f"Unknown level: {self.student.level}")
            return

        display.console.print()
        display.show_info(
            f"Full {level_config.display_name} Practice Test"
        )
        display.show_info(
            f"Sections: {len(level_config.sections)} | "
            f"Total time: {sum(s.time_minutes for s in level_config.sections)} minutes"
        )
        display.console.print()

        if not display.confirm("Ready to begin?"):
            return

        # Create test session
        session = TestSession(
            student_id=self.student.id,
            level=self.student.level,
            grade=self.student.grade,
            mode="full_test",
            started_at=datetime.now().isoformat(),
        )
        session = self.db.create_session(session)

        # Get difficulty map
        difficulty_map = self._get_difficulty_map()

        section_results: List[SectionResult] = []
        all_answers: List[Answer] = []
        all_questions: List[Question] = []

        # Run writing first for middle level
        if self.student.level == "middle":
            self._run_writing_section(session)

        for i, section in enumerate(level_config.sections):
            display.clear_screen()
            display.show_section_intro(
                section.name, section.question_count, section.time_minutes
            )
            display.press_enter_to_continue()

            # Get questions for this section
            questions = self.cache.get_mixed_questions(
                self.student.id, section, self.student.level,
                difficulty_map, self.student.grade,
            )

            if not questions:
                display.show_warning(
                    f"No questions available for {section.name}. "
                    "Try generating questions first (Settings > Pre-generate)."
                )
                continue

            # Run the section
            answers = self._run_section(
                section, questions, session, instant_feedback=False
            )

            # Score the section
            result = self._score_section(
                section, answers, questions, session
            )
            section_results.append(result)
            all_answers.extend(answers)
            all_questions.extend(questions)

            display.show_section_complete(section.name)
            display.show_section_result(result, self.student.level)

            # Break between sections (except after the last one)
            if i < len(level_config.sections) - 1:
                if not display.confirm("Continue to next section?"):
                    break
                display.console.print()

        # Run writing last for elementary level
        if self.student.level == "elementary" and section_results:
            self._run_writing_section(session)

        # Finalize full test
        self._finalize_full_test(session, section_results, all_answers, all_questions)

        # Update mastery
        self._update_mastery(all_answers, all_questions)

        # Check replenishment
        self.cache.check_and_replenish(
            self.student.id, self.student.level, self.student.grade
        )

        display.press_enter_to_continue()

    # ------------------------------------------------------------------
    # Section practice
    # ------------------------------------------------------------------

    def run_section_practice(self) -> None:
        """Let the student pick a section to practice."""
        level_config = LEVEL_CONFIGS.get(self.student.level)
        if not level_config:
            display.show_error(f"Unknown level: {self.student.level}")
            return

        options = [
            f"{s.name} ({s.question_count} questions, {s.time_minutes} min)"
            for s in level_config.sections
        ]
        options.append("Back to main menu")

        choice = display.show_menu("Select Section", options)
        if choice == len(options):
            return

        section = level_config.sections[choice - 1]

        # Create session
        session = TestSession(
            student_id=self.student.id,
            level=self.student.level,
            grade=self.student.grade,
            mode="section_practice",
            started_at=datetime.now().isoformat(),
        )
        session = self.db.create_session(session)

        difficulty_map = self._get_difficulty_map()

        display.show_section_intro(
            section.name, section.question_count, section.time_minutes
        )
        display.press_enter_to_continue()

        questions = self.cache.get_mixed_questions(
            self.student.id, section, self.student.level,
            difficulty_map, self.student.grade,
        )

        if not questions:
            display.show_warning("No questions available. Generate questions first.")
            return

        answers = self._run_section(section, questions, session, instant_feedback=False)
        result = self._score_section(section, answers, questions, session)

        display.show_section_complete(section.name)
        display.show_section_result(result, self.student.level)

        # Update session
        field = scoring.map_section_name_to_score_field(section.name)
        setattr(session, f"{field}_raw", result.raw_score)
        setattr(session, f"{field}_scaled", result.scaled_score)
        setattr(session, f"{field}_percentile", result.percentile)
        session.total_scaled = result.scaled_score
        session.completed_at = datetime.now().isoformat()
        self.db.update_session(session)

        self._update_mastery(answers, questions)

        # Offer review
        wrong_answers = [a for a in answers if a.selected_answer and not a.is_correct]
        if wrong_answers:
            if display.confirm(f"Review {len(wrong_answers)} missed questions?"):
                self._review_answers(wrong_answers, questions)

        display.press_enter_to_continue()

    # ------------------------------------------------------------------
    # Quick drill
    # ------------------------------------------------------------------

    def run_quick_drill(self) -> None:
        """Quick targeted practice with instant feedback."""
        # Pick category
        categories = list(DRILL_TOPICS.keys()) + ["Mixed (all types)"]
        cat_choice = display.show_menu("Select Category", categories)

        if cat_choice <= len(DRILL_TOPICS):
            cat_name = list(DRILL_TOPICS.keys())[cat_choice - 1]
            types = DRILL_TOPICS[cat_name]

            if len(types) > 1:
                type_options = [config.QUESTION_TYPE_DISPLAY.get(t, t.title()) for t in types]
                type_options.append("Mix all")
                type_choice = display.show_menu(f"{cat_name} Topics", type_options)

                if type_choice <= len(types):
                    selected_types = [types[type_choice - 1]]
                else:
                    selected_types = types
            else:
                selected_types = types
        else:
            # Mixed
            from question_cache import LEVEL_TYPES
            selected_types = LEVEL_TYPES.get(self.student.level, ["synonym"])

        # Pick count
        count = display.prompt_int(
            "Number of questions",
            config.DRILL_MIN_QUESTIONS,
            config.DRILL_MAX_QUESTIONS,
        )

        # Optional timer
        use_timer = False
        if config.TIMER_ENABLED:
            use_timer = display.confirm("Use a timer?")

        # Create session
        session = TestSession(
            student_id=self.student.id,
            level=self.student.level,
            grade=self.student.grade,
            mode="quick_drill",
            started_at=datetime.now().isoformat(),
        )
        session = self.db.create_session(session)

        # Get questions
        difficulty_map = self._get_difficulty_map()
        questions: List[Question] = []

        per_type = max(1, count // len(selected_types))
        remainder = count - per_type * len(selected_types)

        for i, qtype in enumerate(selected_types):
            n = per_type + (1 if i < remainder else 0)
            difficulty = difficulty_map.get(qtype, 3)
            qs = self.cache.get_questions(
                self.student.id, qtype, self.student.level,
                int(difficulty), n, self.student.grade,
            )
            questions.extend(qs)

        if not questions:
            display.show_warning("No questions available. Generate questions first.")
            return

        # Truncate to requested count
        questions = questions[:count]

        # Build a fake section config for the drill
        drill_section = SectionConfig(
            name="Quick Drill",
            question_count=len(questions),
            time_minutes=count * 2 if use_timer else 0,  # ~2 min per question
            question_types=tuple(selected_types),
        )

        display.console.print()
        display.show_info(f"Starting drill: {len(questions)} questions")
        if use_timer:
            display.show_info(f"Time limit: {drill_section.time_minutes} minutes")
        display.console.print()

        start_time = time.time()

        # Run with instant feedback
        answers = self._run_section(
            drill_section, questions, session,
            instant_feedback=True, timed=use_timer,
        )

        elapsed = time.time() - start_time

        # Score
        raw, correct, wrong, skipped = scoring.calculate_raw_score(
            answers, self.student.level
        )

        # Save answers
        for a in answers:
            a.session_id = session.id
            self.db.save_answer(a)

        # Update session
        session.completed_at = datetime.now().isoformat()
        self.db.update_session(session)

        # Show summary
        topic_name = ", ".join(
            config.QUESTION_TYPE_DISPLAY.get(t, t.title()) for t in selected_types
        )
        display.show_drill_summary(correct, len(questions), topic_name, elapsed)

        # Update mastery
        self._update_mastery(answers, questions)

        display.press_enter_to_continue()

    # ------------------------------------------------------------------
    # Core question loop
    # ------------------------------------------------------------------

    def _run_section(
        self,
        section: SectionConfig,
        questions: List[Question],
        session: TestSession,
        instant_feedback: bool = False,
        timed: bool = True,
    ) -> List[Answer]:
        """Core question-by-question loop.

        Returns list of Answer objects.
        """
        answers: List[Answer] = []
        timer: Optional[Timer] = None

        if timed and section.time_minutes > 0 and config.TIMER_ENABLED:
            total_seconds = section.time_minutes * 60
            timer = Timer(total_seconds)
            timer.start()

        for i, question in enumerate(questions, 1):
            # Check timer before showing next question
            if timer and timer.is_time_up():
                display.show_warning("Time's up! Remaining questions will be skipped.")
                # Mark remaining as skipped
                for remaining_q in questions[i - 1:]:
                    answer = Answer(
                        session_id=session.id,
                        question_id=remaining_q.id,
                        student_id=self.student.id,
                        selected_answer=None,
                        is_correct=False,
                        time_spent_seconds=0,
                        answered_at=datetime.now().isoformat(),
                    )
                    answers.append(answer)
                break

            # Display question
            time_remaining = timer.get_remaining() if timer else None
            display.show_question(i, len(questions), question, time_remaining)

            # Get answer with timing
            q_start = time.time()
            selected = display.get_answer_input()
            q_elapsed = time.time() - q_start

            # Determine correctness
            is_correct = (
                selected is not None and
                selected.upper() == question.correct_answer.upper()
            )

            # Create answer record
            answer = Answer(
                session_id=session.id,
                question_id=question.id,
                student_id=self.student.id,
                selected_answer=selected,
                is_correct=is_correct if selected else False,
                time_spent_seconds=q_elapsed,
                answered_at=datetime.now().isoformat(),
            )
            answers.append(answer)

            # Instant feedback (drill mode)
            if instant_feedback:
                display.show_answer_feedback(
                    is_correct, selected, question.correct_answer,
                    question.explanation, question.choices,
                )

        if timer:
            timer.stop()

        return answers

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _score_section(
        self,
        section: SectionConfig,
        answers: List[Answer],
        questions: List[Question],
        session: TestSession,
    ) -> SectionResult:
        """Score a section and save answers to DB."""
        raw, correct, wrong, skipped = scoring.calculate_raw_score(
            answers, self.student.level
        )
        scaled = scoring.estimate_scaled_score(
            raw, section.question_count, self.student.level
        )
        percentile = scoring.lookup_percentile(
            scaled, self.student.level, section.name, self.student.grade
        )

        # Save answers
        for a in answers:
            a.session_id = session.id
            self.db.save_answer(a)

        total_time = sum(a.time_spent_seconds for a in answers)

        return SectionResult(
            section_name=section.name,
            raw_score=raw,
            scaled_score=scaled,
            percentile=percentile,
            total_questions=section.question_count,
            correct_count=correct,
            wrong_count=wrong,
            skipped_count=skipped,
            time_used_seconds=total_time,
            answers=answers,
        )

    def _finalize_full_test(
        self,
        session: TestSession,
        section_results: List[SectionResult],
        all_answers: List[Answer],
        all_questions: List[Question],
    ) -> None:
        """Compute final scores and display comprehensive report."""
        # Aggregate per-category scores for the session
        for result in section_results:
            field = scoring.map_section_name_to_score_field(result.section_name)

            current_raw = getattr(session, f"{field}_raw", None)
            if current_raw is not None and field == "quantitative":
                # Combine Quantitative 1 and 2
                setattr(session, f"{field}_raw", current_raw + result.raw_score)
                # Average the scaled scores
                current_scaled = getattr(session, f"{field}_scaled", 0) or 0
                setattr(session, f"{field}_scaled", (current_scaled + result.scaled_score) // 2)
                current_pct = getattr(session, f"{field}_percentile", 0) or 0
                setattr(session, f"{field}_percentile", (current_pct + result.percentile) // 2)
            else:
                setattr(session, f"{field}_raw", result.raw_score)
                setattr(session, f"{field}_scaled", result.scaled_score)
                setattr(session, f"{field}_percentile", result.percentile)

        # Total scaled score
        total = 0
        for field in ("verbal", "quantitative", "reading"):
            s = getattr(session, f"{field}_scaled", None)
            if s:
                total += s
        session.total_scaled = total
        session.completed_at = datetime.now().isoformat()

        self.db.update_session(session)

        # Topic breakdown
        topic_breakdown = scoring.compute_topic_breakdown(all_answers, all_questions)

        # Display report
        display.show_full_score_report(
            self.student, session, section_results, topic_breakdown
        )

    # ------------------------------------------------------------------
    # Review within test
    # ------------------------------------------------------------------

    def _review_answers(
        self, wrong_answers: List[Answer], questions: List[Question]
    ) -> None:
        """Quick review of missed questions within a test session."""
        q_map = {q.id: q for q in questions}

        for i, answer in enumerate(wrong_answers, 1):
            question = q_map.get(answer.question_id)
            if not question:
                continue

            display.show_review_question(
                i, len(wrong_answers), question, answer.selected_answer
            )
            display.press_enter_to_continue()

    # ------------------------------------------------------------------
    # Writing section helper
    # ------------------------------------------------------------------

    def _run_writing_section(self, session: TestSession) -> None:
        """Run the writing section of a full test."""
        try:
            from writing import WritingPractice
            from question_generator import QuestionGenerator
            generator = QuestionGenerator()
            wp = WritingPractice(self.db, generator, self.student)
            wp.run_timed_writing(session.id)
        except Exception as e:
            display.show_warning(f"Writing section skipped: {e}")

    # ------------------------------------------------------------------
    # Difficulty and mastery
    # ------------------------------------------------------------------

    def _get_difficulty_map(self) -> Dict[str, int]:
        """Get current difficulty level for each question type."""
        try:
            from leveling import LevelingEngine
            engine = LevelingEngine(self.db, self.student)
            return engine.get_difficulty_map()
        except Exception:
            # Default to difficulty 3 for all types
            return {}

    def _update_mastery(
        self, answers: List[Answer], questions: List[Question]
    ) -> None:
        """Update topic mastery after answering questions."""
        try:
            from leveling import LevelingEngine
            engine = LevelingEngine(self.db, self.student)
            events = engine.update_after_answers(answers, questions)
            for event in events:
                display.show_info(event)
        except Exception as e:
            pass  # Mastery update is non-critical
