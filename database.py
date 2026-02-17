import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from models import (
    Answer,
    Question,
    Student,
    TestSession,
    TopicMastery,
    WritingSample,
)

SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        grade INTEGER NOT NULL,
        level TEXT NOT NULL DEFAULT 'elementary',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS test_sessions (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id),
        level TEXT NOT NULL,
        grade INTEGER NOT NULL DEFAULT 4,
        mode TEXT NOT NULL DEFAULT 'full_test',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        verbal_raw REAL,
        verbal_scaled INTEGER,
        quantitative_raw REAL,
        quantitative_scaled INTEGER,
        reading_raw REAL,
        reading_scaled INTEGER,
        total_scaled INTEGER,
        verbal_percentile INTEGER,
        quantitative_percentile INTEGER,
        reading_percentile INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS questions (
        id SERIAL PRIMARY KEY,
        level TEXT NOT NULL,
        question_type TEXT NOT NULL,
        topic TEXT NOT NULL DEFAULT '',
        difficulty INTEGER DEFAULT 3,
        stem TEXT NOT NULL,
        passage TEXT,
        choices TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        explanation TEXT DEFAULT '',
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        batch_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS answers (
        id SERIAL PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES test_sessions(id),
        question_id INTEGER NOT NULL REFERENCES questions(id),
        student_id INTEGER NOT NULL REFERENCES students(id),
        selected_answer TEXT,
        is_correct BOOLEAN,
        time_spent_seconds REAL DEFAULT 0,
        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS topic_mastery (
        student_id INTEGER NOT NULL REFERENCES students(id),
        topic_tag TEXT NOT NULL,
        difficulty_level REAL DEFAULT 3.0,
        total_attempted INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        last_50_attempted INTEGER DEFAULT 0,
        last_50_correct INTEGER DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (student_id, topic_tag)
    )""",
    """CREATE TABLE IF NOT EXISTS writing_samples (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id),
        session_id INTEGER REFERENCES test_sessions(id),
        prompt TEXT NOT NULL,
        response TEXT DEFAULT '',
        feedback TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]


class Database:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = psycopg2.connect(db_url)
        self.conn.autocommit = False

    def initialize(self) -> None:
        cur = self.conn.cursor()
        for stmt in SCHEMA_STATEMENTS:
            cur.execute(stmt)
        self.conn.commit()
        cur.close()

    def close(self) -> None:
        self.conn.close()

    def _cursor(self):
        """Return a RealDictCursor for dict-like row access."""
        return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ------------------------------------------------------------------
    # Students
    # ------------------------------------------------------------------
    def create_student(self, name: str, grade: int, level: str) -> Student:
        cur = self._cursor()
        cur.execute(
            "INSERT INTO students (name, grade, level) VALUES (%s, %s, %s) RETURNING id",
            (name, grade, level),
        )
        row = cur.fetchone()
        self.conn.commit()
        cur.close()
        return Student(
            id=row["id"],
            name=name,
            grade=grade,
            level=level,
            created_at=datetime.now().isoformat(),
        )

    def get_student(self, student_id: int) -> Optional[Student]:
        cur = self._cursor()
        cur.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return self._row_to_student(row)

    def list_students(self) -> List[Student]:
        cur = self._cursor()
        cur.execute("SELECT * FROM students ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_student(r) for r in rows]

    def update_student(self, student: Student) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE students SET name=%s, grade=%s, level=%s WHERE id=%s",
            (student.name, student.grade, student.level, student.id),
        )
        self.conn.commit()
        cur.close()

    def _row_to_student(self, row: dict) -> Student:
        return Student(
            id=row["id"],
            name=row["name"],
            grade=row["grade"],
            level=row["level"],
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )

    # ------------------------------------------------------------------
    # Questions
    # ------------------------------------------------------------------
    def save_questions(self, questions: List[Question]) -> List[Question]:
        saved = []
        cur = self._cursor()
        for q in questions:
            choices_json = json.dumps(q.choices)
            cur.execute(
                """INSERT INTO questions
                   (level, question_type, topic, difficulty, stem, passage,
                    choices, correct_answer, explanation, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    q.level, q.question_type, q.topic, q.difficulty,
                    q.stem, q.passage, choices_json, q.correct_answer,
                    q.explanation, q.batch_id,
                ),
            )
            row = cur.fetchone()
            q.id = row["id"]
            saved.append(q)
        self.conn.commit()
        cur.close()
        return saved

    def get_question(self, question_id: int) -> Optional[Question]:
        cur = self._cursor()
        cur.execute("SELECT * FROM questions WHERE id = %s", (question_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return self._row_to_question(row)

    def get_unseen_questions(
        self,
        student_id: int,
        question_type: str,
        level: str,
        difficulty: int,
        limit: int = 25,
    ) -> List[Question]:
        cur = self._cursor()
        cur.execute(
            """SELECT q.* FROM questions q
               WHERE q.question_type = %s
                 AND q.level = %s
                 AND q.difficulty = %s
                 AND q.id NOT IN (
                     SELECT question_id FROM answers WHERE student_id = %s
                 )
               ORDER BY RANDOM()
               LIMIT %s""",
            (question_type, level, difficulty, student_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_question(r) for r in rows]

    def get_unseen_questions_any_difficulty(
        self,
        student_id: int,
        question_type: str,
        level: str,
        limit: int = 25,
    ) -> List[Question]:
        cur = self._cursor()
        cur.execute(
            """SELECT q.* FROM questions q
               WHERE q.question_type = %s
                 AND q.level = %s
                 AND q.id NOT IN (
                     SELECT question_id FROM answers WHERE student_id = %s
                 )
               ORDER BY RANDOM()
               LIMIT %s""",
            (question_type, level, student_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_question(r) for r in rows]

    def count_unseen_questions(
        self, student_id: int, question_type: str, level: str
    ) -> int:
        cur = self._cursor()
        cur.execute(
            """SELECT COUNT(*) as cnt FROM questions q
               WHERE q.question_type = %s
                 AND q.level = %s
                 AND q.id NOT IN (
                     SELECT question_id FROM answers WHERE student_id = %s
                 )""",
            (question_type, level, student_id),
        )
        row = cur.fetchone()
        cur.close()
        return row["cnt"] if row else 0

    def get_questions_by_ids(self, ids: List[int]) -> List[Question]:
        if not ids:
            return []
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM questions WHERE id = ANY(%s)", (ids,)
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_question(r) for r in rows]

    def get_all_stems(self) -> List[str]:
        """Return all question stems for deduplication."""
        cur = self._cursor()
        cur.execute("SELECT stem FROM questions")
        rows = cur.fetchall()
        cur.close()
        return [r["stem"] for r in rows]

    def _row_to_question(self, row: dict) -> Question:
        choices = row["choices"]
        if isinstance(choices, str):
            choices = json.loads(choices)
        return Question(
            id=row["id"],
            level=row["level"],
            question_type=row["question_type"],
            topic=row["topic"],
            difficulty=row["difficulty"],
            stem=row["stem"],
            passage=row["passage"],
            choices=choices,
            correct_answer=row["correct_answer"],
            explanation=row["explanation"],
            generated_at=str(row["generated_at"]) if row["generated_at"] else None,
            batch_id=row["batch_id"],
        )

    # ------------------------------------------------------------------
    # Test Sessions
    # ------------------------------------------------------------------
    def create_session(self, session: TestSession) -> TestSession:
        cur = self._cursor()
        cur.execute(
            """INSERT INTO test_sessions
               (student_id, level, grade, mode, started_at)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id""",
            (
                session.student_id,
                session.level,
                session.grade,
                session.mode,
                session.started_at or datetime.now().isoformat(),
            ),
        )
        row = cur.fetchone()
        self.conn.commit()
        session.id = row["id"]
        cur.close()
        return session

    def update_session(self, session: TestSession) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """UPDATE test_sessions SET
               completed_at=%s, verbal_raw=%s, verbal_scaled=%s,
               quantitative_raw=%s, quantitative_scaled=%s,
               reading_raw=%s, reading_scaled=%s,
               total_scaled=%s,
               verbal_percentile=%s, quantitative_percentile=%s,
               reading_percentile=%s
               WHERE id=%s""",
            (
                session.completed_at,
                session.verbal_raw, session.verbal_scaled,
                session.quantitative_raw, session.quantitative_scaled,
                session.reading_raw, session.reading_scaled,
                session.total_scaled,
                session.verbal_percentile, session.quantitative_percentile,
                session.reading_percentile,
                session.id,
            ),
        )
        self.conn.commit()
        cur.close()

    def get_sessions_for_student(
        self, student_id: int, mode: Optional[str] = None, limit: int = 20
    ) -> List[TestSession]:
        cur = self._cursor()
        if mode:
            cur.execute(
                """SELECT * FROM test_sessions
                   WHERE student_id = %s AND mode = %s
                   ORDER BY started_at DESC LIMIT %s""",
                (student_id, mode, limit),
            )
        else:
            cur.execute(
                """SELECT * FROM test_sessions
                   WHERE student_id = %s
                   ORDER BY started_at DESC LIMIT %s""",
                (student_id, limit),
            )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_session(r) for r in rows]

    def _row_to_session(self, row: dict) -> TestSession:
        return TestSession(
            id=row["id"],
            student_id=row["student_id"],
            level=row["level"],
            grade=row["grade"],
            mode=row["mode"],
            started_at=str(row["started_at"]) if row["started_at"] else None,
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
            verbal_raw=row["verbal_raw"],
            verbal_scaled=row["verbal_scaled"],
            quantitative_raw=row["quantitative_raw"],
            quantitative_scaled=row["quantitative_scaled"],
            reading_raw=row["reading_raw"],
            reading_scaled=row["reading_scaled"],
            total_scaled=row["total_scaled"],
            verbal_percentile=row["verbal_percentile"],
            quantitative_percentile=row["quantitative_percentile"],
            reading_percentile=row["reading_percentile"],
        )

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------
    def save_answer(self, answer: Answer) -> Answer:
        cur = self._cursor()
        cur.execute(
            """INSERT INTO answers
               (session_id, question_id, student_id, selected_answer,
                is_correct, time_spent_seconds, answered_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                answer.session_id, answer.question_id, answer.student_id,
                answer.selected_answer,
                bool(answer.is_correct) if answer.is_correct is not None else None,
                answer.time_spent_seconds,
                answer.answered_at or datetime.now().isoformat(),
            ),
        )
        row = cur.fetchone()
        self.conn.commit()
        answer.id = row["id"]
        cur.close()
        return answer

    def save_answers(self, answers: List[Answer]) -> List[Answer]:
        for a in answers:
            self.save_answer(a)
        return answers

    def get_answers_for_session(self, session_id: int) -> List[Answer]:
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM answers WHERE session_id = %s ORDER BY id",
            (session_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_answer(r) for r in rows]

    def get_wrong_answers_for_student(
        self, student_id: int, limit: int = 50
    ) -> List[Tuple[Answer, Question]]:
        cur = self._cursor()
        cur.execute(
            """SELECT a.id, a.session_id, a.question_id, a.student_id,
                      a.selected_answer, a.is_correct, a.time_spent_seconds,
                      a.answered_at,
                      q.level as q_level, q.question_type as q_type,
                      q.topic as q_topic, q.difficulty as q_difficulty,
                      q.stem as q_stem, q.passage as q_passage,
                      q.choices as q_choices, q.correct_answer as q_correct,
                      q.explanation as q_explanation,
                      q.generated_at as q_generated_at, q.batch_id as q_batch_id
               FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = %s AND a.is_correct = FALSE
               ORDER BY a.answered_at DESC
               LIMIT %s""",
            (student_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        results = []
        for r in rows:
            answer = self._row_to_answer(r)
            choices = r["q_choices"]
            if isinstance(choices, str):
                choices = json.loads(choices)
            question = Question(
                id=r["question_id"],
                level=r["q_level"],
                question_type=r["q_type"],
                topic=r["q_topic"],
                difficulty=r["q_difficulty"],
                stem=r["q_stem"],
                passage=r["q_passage"],
                choices=choices,
                correct_answer=r["q_correct"],
                explanation=r["q_explanation"],
                generated_at=str(r["q_generated_at"]) if r["q_generated_at"] else None,
                batch_id=r["q_batch_id"],
            )
            results.append((answer, question))
        return results

    def get_frequently_missed_questions(
        self, student_id: int, min_wrong_count: int = 2
    ) -> List[Tuple[Question, int]]:
        cur = self._cursor()
        cur.execute(
            """SELECT q.*, COUNT(*) as wrong_count
               FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = %s AND a.is_correct = FALSE
               GROUP BY q.id, q.level, q.question_type, q.topic, q.difficulty,
                        q.stem, q.passage, q.choices, q.correct_answer,
                        q.explanation, q.generated_at, q.batch_id
               HAVING COUNT(*) >= %s
               ORDER BY COUNT(*) DESC""",
            (student_id, min_wrong_count),
        )
        rows = cur.fetchall()
        cur.close()
        results = []
        for r in rows:
            q = self._row_to_question(r)
            results.append((q, r["wrong_count"]))
        return results

    def get_answers_for_student_topic(
        self, student_id: int, topic_tag: str, limit: int = 50
    ) -> List[Answer]:
        cur = self._cursor()
        cur.execute(
            """SELECT a.* FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = %s
                 AND (q.question_type = %s OR q.topic = %s)
               ORDER BY a.answered_at DESC
               LIMIT %s""",
            (student_id, topic_tag, topic_tag, limit),
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_answer(r) for r in rows]

    def _row_to_answer(self, row: dict) -> Answer:
        return Answer(
            id=row["id"],
            session_id=row["session_id"],
            question_id=row["question_id"],
            student_id=row["student_id"],
            selected_answer=row["selected_answer"],
            is_correct=bool(row["is_correct"]) if row["is_correct"] is not None else None,
            time_spent_seconds=row["time_spent_seconds"] or 0.0,
            answered_at=str(row["answered_at"]) if row["answered_at"] else None,
        )

    # ------------------------------------------------------------------
    # Topic Mastery
    # ------------------------------------------------------------------
    def upsert_topic_mastery(self, mastery: TopicMastery) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO topic_mastery
               (student_id, topic_tag, difficulty_level,
                total_attempted, total_correct,
                last_50_attempted, last_50_correct, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT(student_id, topic_tag) DO UPDATE SET
                 difficulty_level = EXCLUDED.difficulty_level,
                 total_attempted = EXCLUDED.total_attempted,
                 total_correct = EXCLUDED.total_correct,
                 last_50_attempted = EXCLUDED.last_50_attempted,
                 last_50_correct = EXCLUDED.last_50_correct,
                 updated_at = EXCLUDED.updated_at""",
            (
                mastery.student_id, mastery.topic_tag,
                mastery.difficulty_level,
                mastery.total_attempted, mastery.total_correct,
                mastery.last_50_attempted, mastery.last_50_correct,
                mastery.updated_at or datetime.now().isoformat(),
            ),
        )
        self.conn.commit()
        cur.close()

    def get_topic_mastery(self, student_id: int) -> List[TopicMastery]:
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM topic_mastery WHERE student_id = %s ORDER BY topic_tag",
            (student_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_mastery(r) for r in rows]

    def get_topic_mastery_for_tag(
        self, student_id: int, topic_tag: str
    ) -> Optional[TopicMastery]:
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM topic_mastery WHERE student_id = %s AND topic_tag = %s",
            (student_id, topic_tag),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return self._row_to_mastery(row)

    def _row_to_mastery(self, row: dict) -> TopicMastery:
        return TopicMastery(
            student_id=row["student_id"],
            topic_tag=row["topic_tag"],
            difficulty_level=row["difficulty_level"],
            total_attempted=row["total_attempted"],
            total_correct=row["total_correct"],
            last_50_attempted=row["last_50_attempted"],
            last_50_correct=row["last_50_correct"],
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    # ------------------------------------------------------------------
    # Writing Samples
    # ------------------------------------------------------------------
    def save_writing_sample(self, sample: WritingSample) -> WritingSample:
        cur = self._cursor()
        cur.execute(
            """INSERT INTO writing_samples
               (student_id, session_id, prompt, response, feedback)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id""",
            (
                sample.student_id, sample.session_id,
                sample.prompt, sample.response, sample.feedback,
            ),
        )
        row = cur.fetchone()
        self.conn.commit()
        sample.id = row["id"]
        cur.close()
        return sample

    def get_writing_samples(
        self, student_id: int, limit: int = 10
    ) -> List[WritingSample]:
        cur = self._cursor()
        cur.execute(
            """SELECT * FROM writing_samples
               WHERE student_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (student_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        return [self._row_to_writing(r) for r in rows]

    def _row_to_writing(self, row: dict) -> WritingSample:
        return WritingSample(
            id=row["id"],
            student_id=row["student_id"],
            session_id=row["session_id"],
            prompt=row["prompt"],
            response=row["response"],
            feedback=row["feedback"],
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------
    def get_student_stats(self, student_id: int) -> Dict:
        cur = self._cursor()

        cur.execute(
            "SELECT COUNT(*) as cnt FROM test_sessions WHERE student_id = %s AND mode = 'full_test'",
            (student_id,),
        )
        full_tests = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) as cnt FROM test_sessions WHERE student_id = %s AND mode = 'section_practice'",
            (student_id,),
        )
        section_practices = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) as cnt FROM test_sessions WHERE student_id = %s AND mode = 'quick_drill'",
            (student_id,),
        )
        drills = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) as cnt FROM answers WHERE student_id = %s",
            (student_id,),
        )
        total_answers = cur.fetchone()["cnt"]

        cur.close()
        return {
            "full_tests": full_tests,
            "section_practices": section_practices,
            "drills": drills,
            "total_answers": total_answers,
        }

    def get_daily_activity(self, student_id: int, days: int = 30) -> List[Dict]:
        """Get per-day activity: questions answered, correct, accuracy, time spent."""
        cur = self._cursor()
        cur.execute(
            """SELECT DATE(a.answered_at) as day,
                      COUNT(*) as total,
                      SUM(CASE WHEN a.is_correct = TRUE THEN 1 ELSE 0 END) as correct,
                      SUM(CASE WHEN a.selected_answer IS NULL THEN 1 ELSE 0 END) as skipped,
                      SUM(a.time_spent_seconds) as total_time
               FROM answers a
               WHERE a.student_id = %s
                 AND a.answered_at >= CURRENT_DATE - make_interval(days => %s)
               GROUP BY DATE(a.answered_at)
               ORDER BY day""",
            (student_id, days),
        )
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "day": str(r["day"]),
                "total": r["total"],
                "correct": r["correct"],
                "skipped": r["skipped"],
                "wrong": r["total"] - r["correct"] - r["skipped"],
                "total_time": r["total_time"] or 0,
            }
            for r in rows
        ]

    def get_daily_activity_by_topic(self, student_id: int, days: int = 30) -> List[Dict]:
        """Get per-day, per-topic breakdown."""
        cur = self._cursor()
        cur.execute(
            """SELECT DATE(a.answered_at) as day,
                      q.question_type as topic,
                      COUNT(*) as total,
                      SUM(CASE WHEN a.is_correct = TRUE THEN 1 ELSE 0 END) as correct
               FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = %s
                 AND a.answered_at >= CURRENT_DATE - make_interval(days => %s)
               GROUP BY DATE(a.answered_at), q.question_type
               ORDER BY day, topic""",
            (student_id, days),
        )
        rows = cur.fetchall()
        cur.close()
        return [
            {"day": str(r["day"]), "topic": r["topic"], "total": r["total"], "correct": r["correct"]}
            for r in rows
        ]

    def get_streak_data(self, student_id: int) -> Dict:
        """Calculate current streak (consecutive days with activity) and longest streak."""
        cur = self._cursor()
        cur.execute(
            """SELECT DISTINCT DATE(answered_at) as day
               FROM answers
               WHERE student_id = %s
               ORDER BY day DESC""",
            (student_id,),
        )
        rows = cur.fetchall()
        cur.close()
        if not rows:
            return {"current_streak": 0, "longest_streak": 0, "total_days": 0}

        from datetime import date, timedelta
        days_active = [r["day"] if isinstance(r["day"], date) else date.fromisoformat(str(r["day"])) for r in rows]
        total_days = len(days_active)

        # Current streak (from today backwards)
        today = date.today()
        current_streak = 0
        check = today
        for d in days_active:
            if d == check or d == check - timedelta(days=1):
                current_streak += 1
                check = d - timedelta(days=1)
            else:
                break

        # Longest streak
        longest = 1
        current = 1
        for i in range(1, len(days_active)):
            if days_active[i - 1] - days_active[i] == timedelta(days=1):
                current += 1
                longest = max(longest, current)
            else:
                current = 1

        return {
            "current_streak": current_streak,
            "longest_streak": max(longest, current_streak),
            "total_days": total_days,
        }

    # ------------------------------------------------------------------
    # Reset helper (used by settings page)
    # ------------------------------------------------------------------
    def reset_student_progress(self, student_id: int) -> None:
        """Delete all progress data for a student."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM answers WHERE student_id = %s", (student_id,))
        cur.execute("DELETE FROM test_sessions WHERE student_id = %s", (student_id,))
        cur.execute("DELETE FROM topic_mastery WHERE student_id = %s", (student_id,))
        cur.execute("DELETE FROM writing_samples WHERE student_id = %s", (student_id,))
        self.conn.commit()
        cur.close()
