import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from config import DB_PATH
from models import (
    Answer,
    Question,
    Student,
    TestSession,
    TopicMastery,
    WritingSample,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    grade INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT 'elementary',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
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
    reading_percentile INTEGER,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    selected_answer TEXT,
    is_correct INTEGER,
    time_spent_seconds REAL DEFAULT 0,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES test_sessions(id),
    FOREIGN KEY (question_id) REFERENCES questions(id),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS topic_mastery (
    student_id INTEGER NOT NULL,
    topic_tag TEXT NOT NULL,
    difficulty_level REAL DEFAULT 3.0,
    total_attempted INTEGER DEFAULT 0,
    total_correct INTEGER DEFAULT 0,
    last_50_attempted INTEGER DEFAULT 0,
    last_50_correct INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, topic_tag),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS writing_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    session_id INTEGER,
    prompt TEXT NOT NULL,
    response TEXT DEFAULT '',
    feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (session_id) REFERENCES test_sessions(id)
);
"""


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass  # WAL not supported on all filesystems
        self.conn.execute("PRAGMA foreign_keys=ON")

    def initialize(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # Students
    # ------------------------------------------------------------------
    def create_student(self, name: str, grade: int, level: str) -> Student:
        cur = self.conn.execute(
            "INSERT INTO students (name, grade, level) VALUES (?, ?, ?)",
            (name, grade, level),
        )
        self.conn.commit()
        return Student(
            id=cur.lastrowid,
            name=name,
            grade=grade,
            level=level,
            created_at=datetime.now().isoformat(),
        )

    def get_student(self, student_id: int) -> Optional[Student]:
        row = self.conn.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_student(row)

    def list_students(self) -> List[Student]:
        rows = self.conn.execute(
            "SELECT * FROM students ORDER BY name"
        ).fetchall()
        return [self._row_to_student(r) for r in rows]

    def update_student(self, student: Student) -> None:
        self.conn.execute(
            "UPDATE students SET name=?, grade=?, level=? WHERE id=?",
            (student.name, student.grade, student.level, student.id),
        )
        self.conn.commit()

    def _row_to_student(self, row: sqlite3.Row) -> Student:
        return Student(
            id=row["id"],
            name=row["name"],
            grade=row["grade"],
            level=row["level"],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Questions
    # ------------------------------------------------------------------
    def save_questions(self, questions: List[Question]) -> List[Question]:
        saved = []
        for q in questions:
            choices_json = json.dumps(q.choices)
            cur = self.conn.execute(
                """INSERT INTO questions
                   (level, question_type, topic, difficulty, stem, passage,
                    choices, correct_answer, explanation, batch_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    q.level, q.question_type, q.topic, q.difficulty,
                    q.stem, q.passage, choices_json, q.correct_answer,
                    q.explanation, q.batch_id,
                ),
            )
            q.id = cur.lastrowid
            saved.append(q)
        self.conn.commit()
        return saved

    def get_question(self, question_id: int) -> Optional[Question]:
        row = self.conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
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
        rows = self.conn.execute(
            """SELECT q.* FROM questions q
               WHERE q.question_type = ?
                 AND q.level = ?
                 AND q.difficulty = ?
                 AND q.id NOT IN (
                     SELECT question_id FROM answers WHERE student_id = ?
                 )
               ORDER BY RANDOM()
               LIMIT ?""",
            (question_type, level, difficulty, student_id, limit),
        ).fetchall()
        return [self._row_to_question(r) for r in rows]

    def get_unseen_questions_any_difficulty(
        self,
        student_id: int,
        question_type: str,
        level: str,
        limit: int = 25,
    ) -> List[Question]:
        rows = self.conn.execute(
            """SELECT q.* FROM questions q
               WHERE q.question_type = ?
                 AND q.level = ?
                 AND q.id NOT IN (
                     SELECT question_id FROM answers WHERE student_id = ?
                 )
               ORDER BY RANDOM()
               LIMIT ?""",
            (question_type, level, student_id, limit),
        ).fetchall()
        return [self._row_to_question(r) for r in rows]

    def count_unseen_questions(
        self, student_id: int, question_type: str, level: str
    ) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) as cnt FROM questions q
               WHERE q.question_type = ?
                 AND q.level = ?
                 AND q.id NOT IN (
                     SELECT question_id FROM answers WHERE student_id = ?
                 )""",
            (question_type, level, student_id),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_questions_by_ids(self, ids: List[int]) -> List[Question]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT * FROM questions WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [self._row_to_question(r) for r in rows]

    def _row_to_question(self, row: sqlite3.Row) -> Question:
        return Question(
            id=row["id"],
            level=row["level"],
            question_type=row["question_type"],
            topic=row["topic"],
            difficulty=row["difficulty"],
            stem=row["stem"],
            passage=row["passage"],
            choices=json.loads(row["choices"]),
            correct_answer=row["correct_answer"],
            explanation=row["explanation"],
            generated_at=row["generated_at"],
            batch_id=row["batch_id"],
        )

    # ------------------------------------------------------------------
    # Test Sessions
    # ------------------------------------------------------------------
    def create_session(self, session: TestSession) -> TestSession:
        cur = self.conn.execute(
            """INSERT INTO test_sessions
               (student_id, level, grade, mode, started_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                session.student_id,
                session.level,
                session.grade,
                session.mode,
                session.started_at or datetime.now().isoformat(),
            ),
        )
        self.conn.commit()
        session.id = cur.lastrowid
        return session

    def update_session(self, session: TestSession) -> None:
        self.conn.execute(
            """UPDATE test_sessions SET
               completed_at=?, verbal_raw=?, verbal_scaled=?,
               quantitative_raw=?, quantitative_scaled=?,
               reading_raw=?, reading_scaled=?,
               total_scaled=?,
               verbal_percentile=?, quantitative_percentile=?,
               reading_percentile=?
               WHERE id=?""",
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

    def get_sessions_for_student(
        self, student_id: int, mode: Optional[str] = None, limit: int = 20
    ) -> List[TestSession]:
        if mode:
            rows = self.conn.execute(
                """SELECT * FROM test_sessions
                   WHERE student_id = ? AND mode = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (student_id, mode, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM test_sessions
                   WHERE student_id = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (student_id, limit),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def _row_to_session(self, row: sqlite3.Row) -> TestSession:
        return TestSession(
            id=row["id"],
            student_id=row["student_id"],
            level=row["level"],
            grade=row["grade"],
            mode=row["mode"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
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
        cur = self.conn.execute(
            """INSERT INTO answers
               (session_id, question_id, student_id, selected_answer,
                is_correct, time_spent_seconds, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                answer.session_id, answer.question_id, answer.student_id,
                answer.selected_answer, int(answer.is_correct) if answer.is_correct is not None else None,
                answer.time_spent_seconds,
                answer.answered_at or datetime.now().isoformat(),
            ),
        )
        self.conn.commit()
        answer.id = cur.lastrowid
        return answer

    def save_answers(self, answers: List[Answer]) -> List[Answer]:
        for a in answers:
            self.save_answer(a)
        return answers

    def get_answers_for_session(self, session_id: int) -> List[Answer]:
        rows = self.conn.execute(
            "SELECT * FROM answers WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [self._row_to_answer(r) for r in rows]

    def get_wrong_answers_for_student(
        self, student_id: int, limit: int = 50
    ) -> List[Tuple[Answer, Question]]:
        rows = self.conn.execute(
            """SELECT a.*, q.level as q_level, q.question_type as q_type,
                      q.topic as q_topic, q.difficulty as q_difficulty,
                      q.stem as q_stem, q.passage as q_passage,
                      q.choices as q_choices, q.correct_answer as q_correct,
                      q.explanation as q_explanation,
                      q.generated_at as q_generated_at, q.batch_id as q_batch_id
               FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = ? AND a.is_correct = 0
               ORDER BY a.answered_at DESC
               LIMIT ?""",
            (student_id, limit),
        ).fetchall()
        results = []
        for r in rows:
            answer = self._row_to_answer(r)
            question = Question(
                id=r["question_id"],
                level=r["q_level"],
                question_type=r["q_type"],
                topic=r["q_topic"],
                difficulty=r["q_difficulty"],
                stem=r["q_stem"],
                passage=r["q_passage"],
                choices=json.loads(r["q_choices"]),
                correct_answer=r["q_correct"],
                explanation=r["q_explanation"],
                generated_at=r["q_generated_at"],
                batch_id=r["q_batch_id"],
            )
            results.append((answer, question))
        return results

    def get_frequently_missed_questions(
        self, student_id: int, min_wrong_count: int = 2
    ) -> List[Tuple[Question, int]]:
        rows = self.conn.execute(
            """SELECT q.*, COUNT(*) as wrong_count
               FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = ? AND a.is_correct = 0
               GROUP BY a.question_id
               HAVING wrong_count >= ?
               ORDER BY wrong_count DESC""",
            (student_id, min_wrong_count),
        ).fetchall()
        results = []
        for r in rows:
            q = self._row_to_question(r)
            results.append((q, r["wrong_count"]))
        return results

    def get_answers_for_student_topic(
        self, student_id: int, topic_tag: str, limit: int = 50
    ) -> List[Answer]:
        rows = self.conn.execute(
            """SELECT a.* FROM answers a
               JOIN questions q ON a.question_id = q.id
               WHERE a.student_id = ?
                 AND (q.question_type = ? OR q.topic = ?)
               ORDER BY a.answered_at DESC
               LIMIT ?""",
            (student_id, topic_tag, topic_tag, limit),
        ).fetchall()
        return [self._row_to_answer(r) for r in rows]

    def _row_to_answer(self, row: sqlite3.Row) -> Answer:
        return Answer(
            id=row["id"],
            session_id=row["session_id"],
            question_id=row["question_id"],
            student_id=row["student_id"],
            selected_answer=row["selected_answer"],
            is_correct=bool(row["is_correct"]) if row["is_correct"] is not None else None,
            time_spent_seconds=row["time_spent_seconds"] or 0.0,
            answered_at=row["answered_at"],
        )

    # ------------------------------------------------------------------
    # Topic Mastery
    # ------------------------------------------------------------------
    def upsert_topic_mastery(self, mastery: TopicMastery) -> None:
        self.conn.execute(
            """INSERT INTO topic_mastery
               (student_id, topic_tag, difficulty_level,
                total_attempted, total_correct,
                last_50_attempted, last_50_correct, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(student_id, topic_tag) DO UPDATE SET
                 difficulty_level = excluded.difficulty_level,
                 total_attempted = excluded.total_attempted,
                 total_correct = excluded.total_correct,
                 last_50_attempted = excluded.last_50_attempted,
                 last_50_correct = excluded.last_50_correct,
                 updated_at = excluded.updated_at""",
            (
                mastery.student_id, mastery.topic_tag,
                mastery.difficulty_level,
                mastery.total_attempted, mastery.total_correct,
                mastery.last_50_attempted, mastery.last_50_correct,
                mastery.updated_at or datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def get_topic_mastery(self, student_id: int) -> List[TopicMastery]:
        rows = self.conn.execute(
            "SELECT * FROM topic_mastery WHERE student_id = ? ORDER BY topic_tag",
            (student_id,),
        ).fetchall()
        return [self._row_to_mastery(r) for r in rows]

    def get_topic_mastery_for_tag(
        self, student_id: int, topic_tag: str
    ) -> Optional[TopicMastery]:
        row = self.conn.execute(
            "SELECT * FROM topic_mastery WHERE student_id = ? AND topic_tag = ?",
            (student_id, topic_tag),
        ).fetchone()
        if not row:
            return None
        return self._row_to_mastery(row)

    def _row_to_mastery(self, row: sqlite3.Row) -> TopicMastery:
        return TopicMastery(
            student_id=row["student_id"],
            topic_tag=row["topic_tag"],
            difficulty_level=row["difficulty_level"],
            total_attempted=row["total_attempted"],
            total_correct=row["total_correct"],
            last_50_attempted=row["last_50_attempted"],
            last_50_correct=row["last_50_correct"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------
    # Writing Samples
    # ------------------------------------------------------------------
    def save_writing_sample(self, sample: WritingSample) -> WritingSample:
        cur = self.conn.execute(
            """INSERT INTO writing_samples
               (student_id, session_id, prompt, response, feedback)
               VALUES (?, ?, ?, ?, ?)""",
            (
                sample.student_id, sample.session_id,
                sample.prompt, sample.response, sample.feedback,
            ),
        )
        self.conn.commit()
        sample.id = cur.lastrowid
        return sample

    def get_writing_samples(
        self, student_id: int, limit: int = 10
    ) -> List[WritingSample]:
        rows = self.conn.execute(
            """SELECT * FROM writing_samples
               WHERE student_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (student_id, limit),
        ).fetchall()
        return [self._row_to_writing(r) for r in rows]

    def _row_to_writing(self, row: sqlite3.Row) -> WritingSample:
        return WritingSample(
            id=row["id"],
            student_id=row["student_id"],
            session_id=row["session_id"],
            prompt=row["prompt"],
            response=row["response"],
            feedback=row["feedback"],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------
    def get_student_stats(self, student_id: int) -> Dict:
        full_tests = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM test_sessions WHERE student_id = ? AND mode = 'full_test'",
            (student_id,),
        ).fetchone()["cnt"]

        section_practices = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM test_sessions WHERE student_id = ? AND mode = 'section_practice'",
            (student_id,),
        ).fetchone()["cnt"]

        drills = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM test_sessions WHERE student_id = ? AND mode = 'quick_drill'",
            (student_id,),
        ).fetchone()["cnt"]

        total_answers = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM answers WHERE student_id = ?",
            (student_id,),
        ).fetchone()["cnt"]

        return {
            "full_tests": full_tests,
            "section_practices": section_practices,
            "drills": drills,
            "total_answers": total_answers,
        }
