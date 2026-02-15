"""Adaptive difficulty tracking and mastery/level-up logic."""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import config
from config import LEVEL_CONFIGS
from database import Database
from models import Answer, Question, Student, TopicMastery
from question_cache import LEVEL_TYPES


class LevelingEngine:
    def __init__(self, db: Database, student: Student):
        self.db = db
        self.student = student

    # ------------------------------------------------------------------
    # Difficulty
    # ------------------------------------------------------------------

    def get_difficulty_for_topic(self, topic_tag: str) -> int:
        """Get current difficulty (1-5) for a given topic."""
        mastery = self.db.get_topic_mastery_for_tag(self.student.id, topic_tag)
        if mastery:
            return max(1, min(5, round(mastery.difficulty_level)))
        return round(config.DIFFICULTY_DEFAULT)

    def get_difficulty_map(self) -> Dict[str, int]:
        """Get difficulty for all topic/type combinations."""
        types = LEVEL_TYPES.get(self.student.level, [])
        result = {}
        for qtype in types:
            result[qtype] = self.get_difficulty_for_topic(qtype)
        return result

    # ------------------------------------------------------------------
    # Update after answering questions
    # ------------------------------------------------------------------

    def update_after_answers(
        self,
        answers: List[Answer],
        questions: List[Question],
    ) -> List[str]:
        """Process results and adjust difficulty. Returns event messages."""
        q_map = {q.id: q for q in questions}

        # Group answers by question type
        by_type: Dict[str, List[Tuple[Answer, Question]]] = {}
        for a in answers:
            q = q_map.get(a.question_id)
            if not q:
                continue
            topic = q.question_type
            if topic not in by_type:
                by_type[topic] = []
            by_type[topic].append((a, q))

        events = []
        for topic, pairs in by_type.items():
            event = self._update_topic(topic, pairs)
            if event:
                events.append(event)

        # Check for level mastery
        mastery_event = self._check_level_mastery()
        if mastery_event:
            events.append(mastery_event)

        return events

    def _update_topic(
        self,
        topic_tag: str,
        pairs: List[Tuple[Answer, Question]],
    ) -> Optional[str]:
        """Update mastery record for a single topic."""
        if not pairs:
            return None

        # Get or create mastery record
        mastery = self.db.get_topic_mastery_for_tag(self.student.id, topic_tag)
        if not mastery:
            mastery = TopicMastery(
                student_id=self.student.id,
                topic_tag=topic_tag,
                difficulty_level=config.DIFFICULTY_DEFAULT,
            )

        # Count this session's results
        session_correct = sum(1 for a, q in pairs if a.is_correct)
        session_total = len(pairs)
        session_accuracy = session_correct / session_total if session_total > 0 else 0

        # Update totals
        mastery.total_attempted += session_total
        mastery.total_correct += session_correct

        # Update last-50 window
        recent_answers = self.db.get_answers_for_student_topic(
            self.student.id, topic_tag, limit=50
        )
        mastery.last_50_attempted = min(len(recent_answers), 50)
        mastery.last_50_correct = sum(
            1 for a in recent_answers[:50] if a.is_correct
        )

        overall_accuracy = (
            mastery.total_correct / mastery.total_attempted
            if mastery.total_attempted > 0 else 0
        )

        # Difficulty adjustment
        event = None
        old_difficulty = mastery.difficulty_level

        if mastery.total_attempted >= config.MIN_QUESTIONS_FOR_ADJUST:
            if (
                session_accuracy >= config.DIFFICULTY_UP_THRESHOLD
                and overall_accuracy >= 0.80
            ):
                new_diff = min(
                    config.DIFFICULTY_MAX,
                    mastery.difficulty_level + config.DIFFICULTY_STEP,
                )
                if new_diff != mastery.difficulty_level:
                    mastery.difficulty_level = new_diff
                    display_name = config.QUESTION_TYPE_DISPLAY.get(
                        topic_tag, topic_tag.title()
                    )
                    event = (
                        f"Difficulty up! {display_name}: "
                        f"{old_difficulty:.1f} -> {new_diff:.1f}"
                    )

            elif (
                session_accuracy < config.DIFFICULTY_DOWN_THRESHOLD
                and overall_accuracy < 0.60
            ):
                new_diff = max(
                    config.DIFFICULTY_MIN,
                    mastery.difficulty_level - config.DIFFICULTY_STEP,
                )
                if new_diff != mastery.difficulty_level:
                    mastery.difficulty_level = new_diff
                    display_name = config.QUESTION_TYPE_DISPLAY.get(
                        topic_tag, topic_tag.title()
                    )
                    event = (
                        f"Difficulty adjusted: {display_name}: "
                        f"{old_difficulty:.1f} -> {new_diff:.1f}"
                    )

        mastery.updated_at = datetime.now().isoformat()
        self.db.upsert_topic_mastery(mastery)

        return event

    # ------------------------------------------------------------------
    # Level mastery check
    # ------------------------------------------------------------------

    def _check_level_mastery(self) -> Optional[str]:
        """Check if the student has mastered their current level."""
        # Need at least MASTERY_TEST_COUNT full tests
        sessions = self.db.get_sessions_for_student(
            self.student.id, mode="full_test", limit=config.MASTERY_TEST_COUNT
        )

        if len(sessions) < config.MASTERY_TEST_COUNT:
            return None

        recent_sessions = sessions[:config.MASTERY_TEST_COUNT]

        # Check percentiles on all sections
        all_high = True
        for s in recent_sessions:
            for field in ("verbal_percentile", "quantitative_percentile", "reading_percentile"):
                pct = getattr(s, field, None)
                if pct is None or pct < config.MASTERY_PERCENTILE:
                    all_high = False
                    break
            if not all_high:
                break

        if not all_high:
            return None

        # Check topic accuracy
        mastery_records = self.db.get_topic_mastery(self.student.id)
        for m in mastery_records:
            if m.total_attempted < config.MASTERY_MIN_QUESTIONS:
                continue
            accuracy = m.total_correct / m.total_attempted
            if accuracy < config.MASTERY_ACCURACY:
                return None

        # Mastery achieved! Determine next level
        return self._level_up()

    def _level_up(self) -> Optional[str]:
        """Advance the student to the next level."""
        current_level = self.student.level
        current_grade = self.student.grade

        if current_level == "elementary":
            if current_grade < 4:
                # Move up within elementary
                self.student.grade = current_grade + 1
                self.db.update_student(self.student)
                return (
                    f"Level Up! {self.student.name} is now practicing at "
                    f"Grade {self.student.grade} Elementary Level!"
                )
            else:
                # Transition to middle level
                self.student.level = "middle"
                self.student.grade = 5
                self.db.update_student(self.student)
                return (
                    f"Level Up! {self.student.name} has moved to "
                    f"Middle Level SSAT! Questions will be more challenging."
                )

        elif current_level == "middle":
            if current_grade < 7:
                self.student.grade = current_grade + 1
                self.db.update_student(self.student)
                return (
                    f"Level Up! {self.student.name} is now practicing at "
                    f"Grade {self.student.grade} Middle Level!"
                )
            else:
                return (
                    f"{self.student.name} has mastered the Middle Level SSAT! "
                    f"Amazing work! Continue practicing to stay sharp."
                )

        return None

    # ------------------------------------------------------------------
    # Level-down protection
    # ------------------------------------------------------------------

    def check_level_down(self) -> Optional[str]:
        """Check if the student is struggling after a level-up.

        Returns a message if level-down is suggested, None otherwise.
        """
        sessions = self.db.get_sessions_for_student(
            self.student.id, mode="full_test", limit=config.LEVEL_DOWN_TEST_COUNT
        )

        if len(sessions) < config.LEVEL_DOWN_TEST_COUNT:
            return None

        recent = sessions[:config.LEVEL_DOWN_TEST_COUNT]
        struggling = True
        for s in recent:
            for field in ("verbal_percentile", "quantitative_percentile", "reading_percentile"):
                pct = getattr(s, field, None)
                if pct is not None and pct >= config.LEVEL_DOWN_PERCENTILE:
                    struggling = False
                    break
            if not struggling:
                break

        if not struggling:
            return None

        return (
            f"It looks like the current level might be a stretch. "
            f"Consider going back for more practice."
        )

    def level_down(self) -> str:
        """Move the student back one level."""
        if self.student.level == "middle":
            if self.student.grade > 5:
                self.student.grade -= 1
            else:
                self.student.level = "elementary"
                self.student.grade = 4
        elif self.student.level == "elementary":
            if self.student.grade > 3:
                self.student.grade -= 1

        self.db.update_student(self.student)
        return (
            f"Moved back to Grade {self.student.grade} "
            f"{self.student.level.title()} Level."
        )
