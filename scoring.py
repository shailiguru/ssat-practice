"""Scoring engine: raw scores, scaled scores, percentile estimation."""

import json
from typing import Dict, List, Optional, Tuple

import config
from config import LEVEL_CONFIGS
from models import Answer, Question


def calculate_raw_score(answers: List[Answer], level: str) -> Tuple[float, int, int, int]:
    """Calculate raw score from a list of answers.

    Returns: (raw_score, correct_count, wrong_count, skipped_count)
    """
    level_config = LEVEL_CONFIGS.get(level)
    has_penalty = level_config.has_penalty if level_config else False
    penalty = level_config.penalty_amount if level_config else 0.0

    correct = sum(1 for a in answers if a.is_correct)
    wrong = sum(1 for a in answers if a.selected_answer is not None and not a.is_correct)
    skipped = sum(1 for a in answers if a.selected_answer is None)

    raw = correct
    if has_penalty:
        raw -= wrong * penalty

    return max(0.0, raw), correct, wrong, skipped


def estimate_scaled_score(
    raw_score: float,
    total_questions: int,
    level: str,
) -> int:
    """Linear interpolation from raw score to scaled score.

    Elementary: 300-600 per section
    Middle: 440-710 per section
    """
    level_config = LEVEL_CONFIGS.get(level)
    if not level_config:
        return 0

    score_min = level_config.score_min
    score_max = level_config.score_max

    if total_questions <= 0:
        return score_min

    fraction = raw_score / total_questions
    fraction = max(0.0, min(1.0, fraction))

    scaled = score_min + fraction * (score_max - score_min)
    return round(scaled)


def lookup_percentile(
    scaled_score: int,
    level: str,
    section_name: str,
    grade: int,
) -> int:
    """Look up estimated percentile from tables.

    Uses linear interpolation between table entries.
    """
    try:
        with open(config.PERCENTILE_TABLES_PATH) as f:
            tables = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _fallback_percentile(scaled_score, level)

    level_data = tables.get(level, {})
    section_data = level_data.get(section_name, {})
    grade_data = section_data.get(str(grade), [])

    if not grade_data:
        # Try adjacent grades
        for g in range(grade - 1, grade + 2):
            grade_data = section_data.get(str(g), [])
            if grade_data:
                break

    if not grade_data:
        return _fallback_percentile(scaled_score, level)

    # grade_data is a list of [score, percentile] pairs, sorted by score
    # Interpolate
    if scaled_score <= grade_data[0][0]:
        return grade_data[0][1]
    if scaled_score >= grade_data[-1][0]:
        return grade_data[-1][1]

    for i in range(len(grade_data) - 1):
        s1, p1 = grade_data[i]
        s2, p2 = grade_data[i + 1]
        if s1 <= scaled_score <= s2:
            if s2 == s1:
                return p1
            fraction = (scaled_score - s1) / (s2 - s1)
            return round(p1 + fraction * (p2 - p1))

    return grade_data[-1][1]


def _fallback_percentile(scaled_score: int, level: str) -> int:
    """Simple fallback percentile estimation when tables aren't available."""
    level_config = LEVEL_CONFIGS.get(level)
    if not level_config:
        return 50
    score_min = level_config.score_min
    score_max = level_config.score_max
    if score_max == score_min:
        return 50
    fraction = (scaled_score - score_min) / (score_max - score_min)
    return max(1, min(99, round(fraction * 98 + 1)))


def compute_topic_breakdown(
    answers: List[Answer],
    questions: List[Question],
) -> Dict[str, Dict]:
    """Compute per-topic accuracy breakdown.

    Returns: {
        "synonym": {"correct": 12, "total": 15, "accuracy": 0.80},
        "arithmetic": {"correct": 8, "total": 10, "accuracy": 0.80},
        ...
    }
    """
    # Build question lookup
    q_map = {q.id: q for q in questions}

    topic_stats: Dict[str, Dict] = {}
    for a in answers:
        q = q_map.get(a.question_id)
        if not q:
            continue
        topic = q.question_type
        if topic not in topic_stats:
            topic_stats[topic] = {"correct": 0, "total": 0, "accuracy": 0.0}

        topic_stats[topic]["total"] += 1
        if a.is_correct:
            topic_stats[topic]["correct"] += 1

    for stats in topic_stats.values():
        if stats["total"] > 0:
            stats["accuracy"] = stats["correct"] / stats["total"]

    return topic_stats


def map_section_name_to_score_field(section_name: str) -> str:
    """Map section name to the TestSession field prefix.

    'Verbal' -> 'verbal'
    'Quantitative 1' or 'Quantitative 2' or 'Math' -> 'quantitative'
    'Reading' -> 'reading'
    """
    name_lower = section_name.lower()
    if "verbal" in name_lower:
        return "verbal"
    if "quant" in name_lower or "math" in name_lower:
        return "quantitative"
    if "reading" in name_lower:
        return "reading"
    return "verbal"
