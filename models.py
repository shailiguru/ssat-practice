from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class TestLevel(str, Enum):
    ELEMENTARY = "elementary"
    MIDDLE = "middle"


class QuestionType(str, Enum):
    SYNONYM = "synonym"
    ANALOGY = "analogy"
    ARITHMETIC = "arithmetic"
    ALGEBRA = "algebra"
    GEOMETRY = "geometry"
    WORD_PROBLEM = "word_problem"
    READING_COMPREHENSION = "reading_comprehension"


class SessionMode(str, Enum):
    FULL_TEST = "full_test"
    SECTION_PRACTICE = "section_practice"
    QUICK_DRILL = "quick_drill"
    REVIEW = "review"


@dataclass
class Student:
    id: Optional[int] = None
    name: str = ""
    grade: int = 4
    level: str = "elementary"
    created_at: Optional[str] = None


@dataclass
class Question:
    id: Optional[int] = None
    level: str = "elementary"
    question_type: str = "synonym"
    topic: str = ""
    difficulty: int = 3
    stem: str = ""
    passage: Optional[str] = None
    choices: Dict[str, str] = field(default_factory=dict)  # {"A": "text", ...}
    correct_answer: str = ""  # "A", "B", "C", "D", or "E"
    explanation: str = ""
    generated_at: Optional[str] = None
    batch_id: Optional[str] = None


@dataclass
class Answer:
    id: Optional[int] = None
    session_id: Optional[int] = None
    question_id: Optional[int] = None
    student_id: Optional[int] = None
    selected_answer: Optional[str] = None  # None = skipped
    is_correct: Optional[bool] = None
    time_spent_seconds: float = 0.0
    answered_at: Optional[str] = None


@dataclass
class SectionResult:
    """Scores for a single section within a test."""
    section_name: str = ""
    raw_score: float = 0.0
    scaled_score: int = 0
    percentile: int = 0
    total_questions: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    skipped_count: int = 0
    time_used_seconds: float = 0.0
    answers: List[Answer] = field(default_factory=list)


@dataclass
class TestSession:
    id: Optional[int] = None
    student_id: Optional[int] = None
    level: str = "elementary"
    grade: int = 4
    mode: str = "full_test"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # Per-section scores (stored as JSON in DB)
    verbal_raw: Optional[float] = None
    verbal_scaled: Optional[int] = None
    quantitative_raw: Optional[float] = None
    quantitative_scaled: Optional[int] = None
    reading_raw: Optional[float] = None
    reading_scaled: Optional[int] = None
    total_scaled: Optional[int] = None
    verbal_percentile: Optional[int] = None
    quantitative_percentile: Optional[int] = None
    reading_percentile: Optional[int] = None


@dataclass
class TopicMastery:
    student_id: Optional[int] = None
    topic_tag: str = ""
    difficulty_level: float = 3.0
    total_attempted: int = 0
    total_correct: int = 0
    last_50_attempted: int = 0
    last_50_correct: int = 0
    updated_at: Optional[str] = None


@dataclass
class WritingSample:
    id: Optional[int] = None
    student_id: Optional[int] = None
    session_id: Optional[int] = None
    prompt: str = ""
    response: str = ""
    feedback: Optional[str] = None
    created_at: Optional[str] = None
