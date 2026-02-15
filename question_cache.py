"""Question pool management, caching, and batch generation."""

from typing import Callable, Dict, List, Optional

import config
from config import LEVEL_CONFIGS, SectionConfig
from database import Database
from models import Question
from question_generator import QuestionGenerator, QuestionGenerationError


# All question types that can be generated
ALL_QUESTION_TYPES = [
    "synonym", "analogy", "arithmetic", "algebra",
    "geometry", "word_problem", "reading_comprehension",
]

# Types relevant to each level
LEVEL_TYPES = {
    "elementary": ["synonym", "analogy", "arithmetic", "geometry", "word_problem", "reading_comprehension"],
    "middle": ["synonym", "analogy", "arithmetic", "algebra", "geometry", "word_problem", "reading_comprehension"],
}

# Default no-op status callback
def _noop_status(msg: str, level: str = "info") -> None:
    pass


class QuestionCache:
    def __init__(
        self,
        db: Database,
        generator: QuestionGenerator,
        on_status: Optional[Callable[[str, str], None]] = None,
    ):
        self.db = db
        self.generator = generator
        self._on_status = on_status or _noop_status

    def get_questions(
        self,
        student_id: int,
        question_type: str,
        level: str,
        difficulty: int,
        count: int,
        grade: int = 4,
    ) -> List[Question]:
        """Get unseen questions, generating new ones if pool is insufficient."""
        # Try exact difficulty match first
        questions = self.db.get_unseen_questions(
            student_id, question_type, level, difficulty, count
        )

        if len(questions) >= count:
            return questions[:count]

        # Try any difficulty for this type
        if len(questions) < count:
            more = self.db.get_unseen_questions_any_difficulty(
                student_id, question_type, level, count - len(questions)
            )
            # Avoid duplicates
            seen_ids = {q.id for q in questions}
            for q in more:
                if q.id not in seen_ids:
                    questions.append(q)
                    seen_ids.add(q.id)

        if len(questions) >= count:
            return questions[:count]

        # Generate new questions
        try:
            if question_type == "reading_comprehension":
                needed = max(count - len(questions), 4)
                num_passages = max(1, needed // 4)
                new_questions = self.generator.generate_reading_comprehension(
                    level=level,
                    grade=grade,
                    difficulty=difficulty,
                    num_passages=num_passages,
                    questions_per_passage=4,
                )
            else:
                needed = max(count - len(questions), config.QUESTIONS_PER_BATCH)
                new_questions = self.generator.generate_questions(
                    question_type=question_type,
                    level=level,
                    grade=grade,
                    difficulty=difficulty,
                    count=needed,
                )

            # Deduplicate and save
            new_questions = self._deduplicate(new_questions)
            if new_questions:
                self.db.save_questions(new_questions)
                questions.extend(new_questions)

        except QuestionGenerationError as e:
            self._on_status(f"Could not generate new questions: {e}", "warning")

        return questions[:count]

    def get_mixed_questions(
        self,
        student_id: int,
        section: SectionConfig,
        level: str,
        difficulty_map: Dict[str, int],
        grade: int = 4,
    ) -> List[Question]:
        """Get questions for an entire section, distributing across types."""
        questions: List[Question] = []
        types = list(section.question_types)
        total = section.question_count

        if section.name == "Verbal":
            # 50/50 split: synonyms and analogies
            half = total // 2
            remainder = total - half * 2
            type_counts = {"synonym": half, "analogy": half + remainder}
        elif section.name in ("Quantitative 1", "Quantitative 2", "Math"):
            # Distribute evenly across math types
            per_type = total // len(types)
            remainder = total - per_type * len(types)
            type_counts = {t: per_type for t in types}
            # Give remainder to the first type
            type_counts[types[0]] += remainder
        elif section.name == "Reading":
            type_counts = {"reading_comprehension": total}
        else:
            # Default: even split
            per_type = total // len(types)
            remainder = total - per_type * len(types)
            type_counts = {t: per_type for t in types}
            type_counts[types[0]] += remainder

        for qtype, count in type_counts.items():
            if count <= 0:
                continue
            difficulty = difficulty_map.get(qtype, 3)
            qs = self.get_questions(
                student_id, qtype, level, int(difficulty), count, grade
            )
            questions.extend(qs)

        return questions

    def check_and_replenish(self, student_id: int, level: str, grade: int = 4) -> None:
        """Check all pools and generate if any are below threshold."""
        types = LEVEL_TYPES.get(level, ALL_QUESTION_TYPES)

        for qtype in types:
            unseen = self.db.count_unseen_questions(student_id, qtype, level)
            if unseen < config.MIN_POOL_SIZE:
                self._on_status(f"Generating more {qtype} questions...", "info")
                try:
                    if qtype == "reading_comprehension":
                        new_qs = self.generator.generate_reading_comprehension(
                            level=level, grade=grade, difficulty=3,
                            num_passages=3, questions_per_passage=4,
                        )
                    else:
                        new_qs = self.generator.generate_questions(
                            question_type=qtype, level=level, grade=grade,
                            difficulty=3, count=config.QUESTIONS_PER_BATCH,
                        )
                    new_qs = self._deduplicate(new_qs)
                    if new_qs:
                        self.db.save_questions(new_qs)
                except QuestionGenerationError as e:
                    self._on_status(f"Failed to replenish {qtype}: {e}", "warning")

    def generate_batch(self, level: str, grade: int) -> Dict[str, int]:
        """Generate a batch of questions. Returns {type: count_generated}."""
        types = LEVEL_TYPES.get(level, ALL_QUESTION_TYPES)
        results = {}

        for qtype in types:
            self._on_status(f"Generating {qtype} questions...", "info")
            try:
                if qtype == "reading_comprehension":
                    new_qs = self.generator.generate_reading_comprehension(
                        level=level, grade=grade, difficulty=3,
                        num_passages=3, questions_per_passage=4,
                    )
                else:
                    new_qs = self.generator.generate_questions(
                        question_type=qtype, level=level, grade=grade,
                        difficulty=3, count=config.QUESTIONS_PER_BATCH,
                    )
                new_qs = self._deduplicate(new_qs)
                if new_qs:
                    self.db.save_questions(new_qs)
                results[qtype] = len(new_qs)
                self._on_status(f"{qtype}: {len(new_qs)} generated", "success")
            except QuestionGenerationError as e:
                results[qtype] = 0
                self._on_status(f"{qtype}: failed ({e})", "error")

        return results

    def get_pool_stats(self, student_id: int, level: str) -> Dict[str, int]:
        """Return count of unseen questions per type."""
        types = LEVEL_TYPES.get(level, ALL_QUESTION_TYPES)
        stats = {}
        for qtype in types:
            stats[qtype] = self.db.count_unseen_questions(student_id, qtype, level)
        return stats

    def _deduplicate(self, questions: List[Question]) -> List[Question]:
        """Remove questions with duplicate stems (normalized)."""
        seen_stems = set()
        unique = []
        for q in questions:
            normalized = q.stem.strip().lower()
            if normalized not in seen_stems:
                seen_stems.add(normalized)
                unique.append(q)
        return unique
