import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Helper: read from Streamlit secrets if available, else os.getenv
# ---------------------------------------------------------------------------
def _get_secret(key: str, default: str = "") -> str:
    """Try st.secrets first (Streamlit Cloud), then env vars."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except (ImportError, Exception):
        pass
    return os.getenv(key, default)


# ---------------------------------------------------------------------------
# Environment-driven settings
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = _get_secret("ANTHROPIC_API_KEY", "")
DB_PATH: str = _get_secret("SSAT_DB_PATH", str(Path(__file__).parent / "ssat_practice.db"))
MODEL: str = _get_secret("SSAT_MODEL", "claude-sonnet-4-5-20250929")
TIMER_ENABLED: bool = _get_secret("SSAT_TIMER_ENABLED", "true").lower() == "true"
QUESTIONS_PER_BATCH: int = int(_get_secret("SSAT_QUESTIONS_PER_BATCH", "25"))

# ---------------------------------------------------------------------------
# SSAT test structure constants
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionConfig:
    name: str
    question_count: int
    time_minutes: int
    question_types: tuple  # e.g. ("synonym", "analogy")


@dataclass(frozen=True)
class LevelConfig:
    level_name: str        # "elementary" | "middle"
    display_name: str      # "Elementary Level" etc.
    grade_range: tuple     # (3, 4) or (5, 7)
    sections: tuple        # tuple of SectionConfig
    score_min: int         # per-section min scaled score
    score_max: int         # per-section max scaled score
    has_penalty: bool      # wrong-answer penalty
    penalty_amount: float  # 0.0 for elementary, 0.25 for middle
    writing_time_minutes: int


ELEMENTARY_SECTIONS = (
    SectionConfig("Math", 30, 30, ("arithmetic", "geometry", "word_problem")),
    SectionConfig("Verbal", 30, 20, ("synonym", "analogy")),
    SectionConfig("Reading", 28, 30, ("reading_comprehension",)),
)

MIDDLE_SECTIONS = (
    SectionConfig("Quantitative 1", 25, 30, ("arithmetic", "algebra", "geometry")),
    SectionConfig("Reading", 40, 40, ("reading_comprehension",)),
    SectionConfig("Verbal", 60, 30, ("synonym", "analogy")),
    SectionConfig("Quantitative 2", 25, 30, ("arithmetic", "algebra", "geometry")),
)

LEVEL_CONFIGS: Dict[str, LevelConfig] = {
    "elementary": LevelConfig(
        level_name="elementary",
        display_name="Elementary Level",
        grade_range=(3, 4),
        sections=ELEMENTARY_SECTIONS,
        score_min=300,
        score_max=600,
        has_penalty=False,
        penalty_amount=0.0,
        writing_time_minutes=15,
    ),
    "middle": LevelConfig(
        level_name="middle",
        display_name="Middle Level",
        grade_range=(5, 7),
        sections=MIDDLE_SECTIONS,
        score_min=440,
        score_max=710,
        has_penalty=True,
        penalty_amount=0.25,
        writing_time_minutes=25,
    ),
}

# Mapping from question type to user-friendly display name
QUESTION_TYPE_DISPLAY = {
    "synonym": "Synonyms",
    "analogy": "Analogies",
    "arithmetic": "Arithmetic",
    "algebra": "Algebra",
    "geometry": "Geometry",
    "word_problem": "Word Problems",
    "reading_comprehension": "Reading Comprehension",
}

# Topics available for quick drills, grouped by category
DRILL_TOPICS = {
    "Math": ["arithmetic", "algebra", "geometry", "word_problem"],
    "Verbal": ["synonym", "analogy"],
    "Reading": ["reading_comprehension"],
}

# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------
MIN_POOL_SIZE = 10           # auto-replenish when unseen < this
RATE_LIMIT_SECONDS = 1.0     # min delay between API calls
MAX_RETRIES = 3              # retries on transient API errors
MAX_TOKENS = 8192            # max tokens for question generation response

# ---------------------------------------------------------------------------
# Mastery / leveling
# ---------------------------------------------------------------------------
MASTERY_PERCENTILE = 85      # need 85th percentile on all sections
MASTERY_TEST_COUNT = 3       # across the last N full tests
MASTERY_ACCURACY = 0.85      # 85% topic accuracy
MASTERY_MIN_QUESTIONS = 20   # minimum questions attempted per topic
DIFFICULTY_MIN = 1.0
DIFFICULTY_MAX = 5.0
DIFFICULTY_DEFAULT = 3.0
DIFFICULTY_UP_THRESHOLD = 0.85    # session accuracy to increase difficulty
DIFFICULTY_DOWN_THRESHOLD = 0.50  # session accuracy to decrease difficulty
DIFFICULTY_STEP = 0.5             # adjustment per session
MIN_QUESTIONS_FOR_ADJUST = 5     # min questions before adjusting

# Level-down protection
LEVEL_DOWN_PERCENTILE = 40
LEVEL_DOWN_TEST_COUNT = 2

# ---------------------------------------------------------------------------
# Quick drill
# ---------------------------------------------------------------------------
DRILL_MIN_QUESTIONS = 10
DRILL_MAX_QUESTIONS = 20
DRILL_DEFAULT_QUESTIONS = 10

# ---------------------------------------------------------------------------
# Data file paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
PERCENTILE_TABLES_PATH = DATA_DIR / "percentile_tables.json"
VOCABULARY_LISTS_PATH = DATA_DIR / "vocabulary_lists.json"
