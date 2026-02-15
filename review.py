"""Review mode for missed questions, with retry and spaced repetition."""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database import Database
from models import Answer, Question, Student, TestSession
from question_cache import QuestionCache
import config
import display


class ReviewManager:
    def __init__(self, db: Database, cache: QuestionCache, student: Student):
        self.db = db
        self.cache = cache
        self.student = student

    def run_review(self) -> None:
        """Main review entry point."""
        while True:
            options = [
                "Review recent mistakes",
                "Review by topic (worst areas first)",
                "Retry missed questions as drill",
                "Spaced repetition review",
                "Back to main menu",
            ]
            choice = display.show_menu("Review Mode", options)

            if choice == 1:
                self.review_recent_mistakes()
            elif choice == 2:
                self.review_by_topic()
            elif choice == 3:
                self.retry_missed_as_drill()
            elif choice == 4:
                self.spaced_repetition_review()
            elif choice == 5:
                break

    def review_recent_mistakes(self, session_id: Optional[int] = None) -> None:
        """Review missed questions from the most recent session."""
        if session_id:
            wrong = self._get_wrong_from_session(session_id)
        else:
            wrong = self.db.get_wrong_answers_for_student(self.student.id, limit=20)

        if not wrong:
            display.show_info("No missed questions to review. Great job!")
            display.press_enter_to_continue()
            return

        display.console.print()
        display.show_info(f"Reviewing {len(wrong)} missed questions")
        display.console.print()

        for i, (answer, question) in enumerate(wrong, 1):
            display.show_review_question(
                i, len(wrong), question, answer.selected_answer
            )
            display.press_enter_to_continue()

        display.show_success("Review complete!")
        display.press_enter_to_continue()

    def review_by_topic(self) -> None:
        """Show topic-level mistake summary and drill weak areas."""
        wrong = self.db.get_wrong_answers_for_student(self.student.id, limit=200)

        if not wrong:
            display.show_info("No missed questions to review!")
            display.press_enter_to_continue()
            return

        # Group by topic
        topic_errors: Dict[str, int] = {}
        topic_questions: Dict[str, List[Tuple[Answer, Question]]] = {}

        for answer, question in wrong:
            topic = question.question_type
            topic_errors[topic] = topic_errors.get(topic, 0) + 1
            if topic not in topic_questions:
                topic_questions[topic] = []
            topic_questions[topic].append((answer, question))

        # Sort by error count (worst first)
        sorted_topics = sorted(topic_errors.items(), key=lambda x: -x[1])

        # Display
        from rich.table import Table
        table = Table(title="Mistakes by Topic", border_style="dim")
        table.add_column("#", justify="right", style="bold")
        table.add_column("Topic", style="bold")
        table.add_column("Errors", justify="right", style="wrong")

        for i, (topic, count) in enumerate(sorted_topics, 1):
            display_name = config.QUESTION_TYPE_DISPLAY.get(topic, topic.title())
            table.add_row(str(i), display_name, str(count))

        display.console.print(table)
        display.console.print()

        # Offer drill on worst topic
        if display.confirm("Drill your weakest topic?"):
            worst_topic = sorted_topics[0][0]
            pairs = topic_questions[worst_topic][:10]
            self._run_review_drill([q for _, q in pairs])

    def retry_missed_as_drill(self) -> None:
        """Re-attempt previously missed questions."""
        wrong = self.db.get_wrong_answers_for_student(self.student.id, limit=20)

        if not wrong:
            display.show_info("No missed questions to retry!")
            display.press_enter_to_continue()
            return

        questions = [q for _, q in wrong[:15]]
        display.show_info(f"Retrying {len(questions)} missed questions with instant feedback")
        display.press_enter_to_continue()

        self._run_review_drill(questions)

    def spaced_repetition_review(self) -> None:
        """Surface questions missed 2+ times."""
        frequently_missed = self.db.get_frequently_missed_questions(
            self.student.id, min_wrong_count=2
        )

        if not frequently_missed:
            display.show_info(
                "No frequently missed questions! "
                "Keep practicing to build your skills."
            )
            display.press_enter_to_continue()
            return

        display.show_info(
            f"Found {len(frequently_missed)} questions you've missed multiple times. "
            f"Let's work through them!"
        )
        display.console.print()

        questions = [q for q, count in frequently_missed[:15]]
        self._run_review_drill(questions)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_review_drill(self, questions: List[Question]) -> None:
        """Run a mini-drill with the given questions, with instant feedback."""
        import time as time_mod

        # Create a review session
        session = TestSession(
            student_id=self.student.id,
            level=self.student.level,
            grade=self.student.grade,
            mode="review",
            started_at=datetime.now().isoformat(),
        )
        session = self.db.create_session(session)

        correct = 0
        total = len(questions)
        start = time_mod.time()

        for i, question in enumerate(questions, 1):
            display.show_question(i, total, question)
            q_start = time_mod.time()
            selected = display.get_answer_input()
            q_elapsed = time_mod.time() - q_start

            is_correct = (
                selected is not None
                and selected.upper() == question.correct_answer.upper()
            )
            if is_correct:
                correct += 1

            display.show_answer_feedback(
                is_correct, selected, question.correct_answer,
                question.explanation, question.choices,
            )

            # Save answer
            answer = Answer(
                session_id=session.id,
                question_id=question.id,
                student_id=self.student.id,
                selected_answer=selected,
                is_correct=is_correct if selected else False,
                time_spent_seconds=q_elapsed,
                answered_at=datetime.now().isoformat(),
            )
            self.db.save_answer(answer)

        elapsed = time_mod.time() - start

        # Complete session
        session.completed_at = datetime.now().isoformat()
        self.db.update_session(session)

        display.show_drill_summary(correct, total, "Review Drill", elapsed)

    def _get_wrong_from_session(
        self, session_id: int
    ) -> List[Tuple[Answer, Question]]:
        """Get wrong answers from a specific session."""
        answers = self.db.get_answers_for_session(session_id)
        wrong_answers = [a for a in answers if a.selected_answer and not a.is_correct]

        result = []
        for a in wrong_answers:
            q = self.db.get_question(a.question_id)
            if q:
                result.append((a, q))
        return result
