"""Badge definitions and check logic for gamification."""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class BadgeDef:
    name: str
    description: str
    icon: str
    check: Callable[[Dict], bool]


def _check_first_steps(stats: Dict) -> bool:
    return stats.get("total_answers", 0) >= 1


def _check_streak_3(stats: Dict) -> bool:
    return stats.get("streak", 0) >= 3


def _check_streak_7(stats: Dict) -> bool:
    return stats.get("streak", 0) >= 7


def _check_streak_14(stats: Dict) -> bool:
    return stats.get("streak", 0) >= 14


def _check_century(stats: Dict) -> bool:
    return stats.get("total_answers", 0) >= 100


def _check_500_club(stats: Dict) -> bool:
    return stats.get("total_answers", 0) >= 500


def _check_math_whiz(stats: Dict) -> bool:
    math_topics = stats.get("topic_accuracy", {})
    for topic in ["arithmetic", "algebra", "geometry", "word_problem"]:
        acc = math_topics.get(topic, {})
        if acc.get("total", 0) >= 20 and acc.get("accuracy", 0) >= 0.85:
            return True
    return False


def _check_word_master(stats: Dict) -> bool:
    topics = stats.get("topic_accuracy", {})
    for topic in ["synonym", "analogy"]:
        acc = topics.get(topic, {})
        if acc.get("total", 0) >= 20 and acc.get("accuracy", 0) >= 0.85:
            return True
    return False


def _check_speed_demon(stats: Dict) -> bool:
    return stats.get("mini_test_time_to_spare", 0) >= 120


def _check_perfect_10(stats: Dict) -> bool:
    return stats.get("mini_test_perfect", False)


def _check_double_checker(stats: Dict) -> bool:
    return stats.get("total_changed_answers", 0) >= 5


BADGE_DEFINITIONS: List[BadgeDef] = [
    BadgeDef("First Steps", "Complete your first practice session", "🎯", _check_first_steps),
    BadgeDef("3-Day Streak", "Practice 3 days in a row", "🔥", _check_streak_3),
    BadgeDef("Week Warrior", "Practice 7 days in a row", "⚡", _check_streak_7),
    BadgeDef("Two-Week Titan", "Practice 14 days in a row", "💪", _check_streak_14),
    BadgeDef("Century Club", "Answer 100 questions", "💯", _check_century),
    BadgeDef("500 Club", "Answer 500 questions", "🏆", _check_500_club),
    BadgeDef("Math Whiz", "85%+ accuracy on 20+ math questions", "🔢", _check_math_whiz),
    BadgeDef("Word Master", "85%+ accuracy on 20+ verbal questions", "📚", _check_word_master),
    BadgeDef("Speed Demon", "Finish a mini test with 2+ minutes to spare", "⏱️", _check_speed_demon),
    BadgeDef("Perfect 10", "Score 10/10 on a mini test", "🌟", _check_perfect_10),
    BadgeDef("Double Checker", "Change 5+ answers after being nudged", "🔍", _check_double_checker),
]


def check_new_badges(stats: Dict, existing_badge_names: List[str]) -> List[BadgeDef]:
    """Check all badge definitions and return any newly earned badges."""
    new_badges = []
    for badge in BADGE_DEFINITIONS:
        if badge.name not in existing_badge_names:
            if badge.check(stats):
                new_badges.append(badge)
    return new_badges
