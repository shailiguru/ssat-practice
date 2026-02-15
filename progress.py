"""Analytics dashboard, score trends, and recommendations."""

from typing import Dict, List

from database import Database
from models import Student, TestSession, TopicMastery
import config
import display


class ProgressTracker:
    def __init__(self, db: Database, student: Student):
        self.db = db
        self.student = student

    def show_dashboard(self) -> None:
        """Main dashboard entry point."""
        stats = self.db.get_student_stats(self.student.id)
        sessions = self.db.get_sessions_for_student(self.student.id, limit=20)
        mastery = self.db.get_topic_mastery(self.student.id)

        display.show_progress_dashboard(self.student, stats, sessions, mastery)

        # Recommendations
        recommendations = self.get_recommendations(stats, sessions, mastery)
        if recommendations:
            display.console.print()
            display.console.print("  [bold]Recommendations:[/bold]")
            for rec in recommendations:
                display.console.print(f"  - {rec}")
            display.console.print()

    def get_recommendations(
        self,
        stats: Dict,
        sessions: List[TestSession],
        mastery: List[TopicMastery],
    ) -> List[str]:
        """Generate rule-based study recommendations."""
        recs = []

        if stats["total_answers"] == 0:
            recs.append("Take your first practice test to see where you stand!")
            return recs

        if stats["full_tests"] == 0:
            recs.append("Try a full practice test to get a complete score report.")

        # Find weak topics
        weak_topics = []
        needs_work_topics = []
        for m in mastery:
            if m.total_attempted < 5:
                continue
            accuracy = m.total_correct / m.total_attempted if m.total_attempted > 0 else 0
            display_name = config.QUESTION_TYPE_DISPLAY.get(m.topic_tag, m.topic_tag.title())
            if accuracy < 0.60:
                weak_topics.append(display_name)
            elif accuracy < 0.85:
                needs_work_topics.append(display_name)

        if weak_topics:
            recs.append(f"Focus on: {', '.join(weak_topics)} - try quick drills to build skills.")
        if needs_work_topics:
            recs.append(f"Keep practicing: {', '.join(needs_work_topics)} - you're getting closer to mastery!")

        # Score trend
        full_tests = [s for s in sessions if s.mode == "full_test" and s.total_scaled]
        if len(full_tests) >= 2:
            recent = full_tests[0].total_scaled
            previous = full_tests[1].total_scaled
            if recent > previous:
                recs.append(f"Your scores are trending up! (+{recent - previous} points)")
            elif recent < previous:
                recs.append("Scores dipped slightly. Focus on weak areas with targeted drills.")

        # Strong topics
        strong_topics = []
        for m in mastery:
            if m.total_attempted < 10:
                continue
            accuracy = m.total_correct / m.total_attempted
            if accuracy >= 0.85:
                display_name = config.QUESTION_TYPE_DISPLAY.get(m.topic_tag, m.topic_tag.title())
                strong_topics.append(display_name)

        if strong_topics:
            recs.append(f"Great mastery in: {', '.join(strong_topics)}!")

        if not recs:
            recs.append("Keep practicing regularly - consistency is key!")

        return recs
