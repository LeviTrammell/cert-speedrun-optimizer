"""Repository for database operations."""

import json
import uuid
import random
from datetime import datetime
from typing import Any
import aiosqlite

from .database import get_db


def generate_id() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class Repository:
    """Repository for all database operations."""

    # ==================== EXAMS ====================

    @staticmethod
    async def create_exam(
        name: str,
        vendor: str,
        exam_code: str | None = None,
        description: str | None = None,
        passing_score: int | None = None,
        time_limit_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Create a new exam."""
        exam_id = generate_id()
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO exams (id, name, vendor, exam_code, description, passing_score, time_limit_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (exam_id, name, vendor, exam_code, description, passing_score, time_limit_minutes),
            )
            await db.commit()

            cursor = await db.execute("SELECT * FROM exams WHERE id = ?", (exam_id,))
            row = await cursor.fetchone()
            return dict(row)

    @staticmethod
    async def get_exam(exam_id: str) -> dict[str, Any] | None:
        """Get an exam by ID."""
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM exams WHERE id = ?", (exam_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def get_exam_by_name(name: str) -> dict[str, Any] | None:
        """Get an exam by name."""
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM exams WHERE name = ?", (name,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def list_exams(vendor: str | None = None, include_stats: bool = False) -> list[dict[str, Any]]:
        """List all exams, optionally filtered by vendor."""
        async with get_db() as db:
            if include_stats:
                query = """
                    SELECT e.*,
                           COUNT(DISTINCT q.id) as question_count,
                           COUNT(DISTINCT t.id) as topic_count
                    FROM exams e
                    LEFT JOIN questions q ON e.id = q.exam_id
                    LEFT JOIN topics t ON e.id = t.exam_id
                """
                if vendor:
                    query += " WHERE e.vendor = ?"
                    query += " GROUP BY e.id ORDER BY e.created_at DESC"
                    cursor = await db.execute(query, (vendor,))
                else:
                    query += " GROUP BY e.id ORDER BY e.created_at DESC"
                    cursor = await db.execute(query)
            else:
                query = "SELECT * FROM exams"
                if vendor:
                    query += " WHERE vendor = ?"
                    query += " ORDER BY created_at DESC"
                    cursor = await db.execute(query, (vendor,))
                else:
                    query += " ORDER BY created_at DESC"
                    cursor = await db.execute(query)

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ==================== TOPICS ====================

    @staticmethod
    async def create_topic(
        exam_id: str,
        name: str,
        description: str | None = None,
        weight_percent: float | None = None,
    ) -> dict[str, Any]:
        """Create a new topic."""
        topic_id = generate_id()
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO topics (id, exam_id, name, description, weight_percent)
                VALUES (?, ?, ?, ?, ?)
                """,
                (topic_id, exam_id, name, description, weight_percent),
            )
            await db.commit()

            cursor = await db.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
            row = await cursor.fetchone()
            return dict(row)

    @staticmethod
    async def get_topic(topic_id: str) -> dict[str, Any] | None:
        """Get a topic by ID."""
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def get_topic_by_name(exam_id: str, name: str) -> dict[str, Any] | None:
        """Get a topic by name within an exam."""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM topics WHERE exam_id = ? AND name = ?",
                (exam_id, name),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def list_topics(exam_id: str, include_stats: bool = False) -> list[dict[str, Any]]:
        """List all topics for an exam."""
        async with get_db() as db:
            if include_stats:
                query = """
                    SELECT t.*, COUNT(qt.question_id) as question_count
                    FROM topics t
                    LEFT JOIN question_topics qt ON t.id = qt.topic_id
                    WHERE t.exam_id = ?
                    GROUP BY t.id
                    ORDER BY t.weight_percent DESC NULLS LAST, t.name
                """
            else:
                query = """
                    SELECT * FROM topics
                    WHERE exam_id = ?
                    ORDER BY weight_percent DESC NULLS LAST, name
                """
            cursor = await db.execute(query, (exam_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ==================== QUESTIONS ====================

    @staticmethod
    async def get_question_type_id(code: str) -> int:
        """Get question type ID by code."""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id FROM question_types WHERE code = ?", (code.upper(),)
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError(f"Unknown question type: {code}")
            return row["id"]

    @staticmethod
    async def create_question(
        exam_id: str,
        question_text: str,
        question_type: str,
        answers: list[dict[str, Any]],
        topic_ids: list[str] | None = None,
        choose_n: int | None = None,
        explanation: str | None = None,
        difficulty: str = "medium",
        pattern_tags: list[str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Create a new question with answers."""
        question_id = generate_id()
        question_type_id = await Repository.get_question_type_id(question_type)

        async with get_db() as db:
            # Insert question
            await db.execute(
                """
                INSERT INTO questions (
                    id, exam_id, question_type_id, question_text, explanation,
                    difficulty, choose_n, pattern_tags, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    exam_id,
                    question_type_id,
                    question_text,
                    explanation,
                    difficulty,
                    choose_n,
                    json.dumps(pattern_tags) if pattern_tags else None,
                    source,
                ),
            )

            # Insert answer options
            for answer in answers:
                answer_id = generate_id()
                await db.execute(
                    """
                    INSERT INTO answer_options (id, question_id, option_text, is_correct, distractor_reason)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        answer_id,
                        question_id,
                        answer["text"],
                        1 if answer.get("is_correct", False) else 0,
                        answer.get("distractor_reason"),
                    ),
                )

            # Link to topics
            if topic_ids:
                for topic_id in topic_ids:
                    await db.execute(
                        "INSERT INTO question_topics (question_id, topic_id) VALUES (?, ?)",
                        (question_id, topic_id),
                    )

            # Initialize stats
            await db.execute(
                "INSERT INTO question_stats (question_id) VALUES (?)",
                (question_id,),
            )

            await db.commit()

            return await Repository.get_question(question_id)

    @staticmethod
    async def get_question(question_id: str, randomize_answers: bool = True) -> dict[str, Any] | None:
        """Get a question by ID with answers."""
        async with get_db() as db:
            # Get question
            cursor = await db.execute(
                """
                SELECT q.*, qt.code as question_type, e.name as exam_name, e.vendor as exam_vendor
                FROM questions q
                JOIN question_types qt ON q.question_type_id = qt.id
                JOIN exams e ON q.exam_id = e.id
                WHERE q.id = ?
                """,
                (question_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            question = dict(row)

            # Parse JSON fields
            question["pattern_tags"] = (
                json.loads(question["pattern_tags"]) if question["pattern_tags"] else []
            )

            # Get answers
            cursor = await db.execute(
                "SELECT id, option_text, is_correct, distractor_reason FROM answer_options WHERE question_id = ?",
                (question_id,),
            )
            answers = [dict(r) for r in await cursor.fetchall()]

            # Randomize answer order if requested
            if randomize_answers:
                random.shuffle(answers)

            # Assign display letters
            for i, answer in enumerate(answers):
                answer["letter"] = chr(65 + i)

            question["answers"] = answers

            # Get topics
            cursor = await db.execute(
                """
                SELECT t.id, t.name FROM topics t
                JOIN question_topics qt ON t.id = qt.topic_id
                WHERE qt.question_id = ?
                """,
                (question_id,),
            )
            question["topics"] = [dict(r) for r in await cursor.fetchall()]

            # Generate instruction based on question type
            if question["question_type"] == "SINGLE":
                question["instruction"] = "Select ONE answer."
            elif question["question_type"] == "SELECT_ALL":
                question["instruction"] = "Select ALL correct answers."
            elif question["question_type"] == "CHOOSE_N":
                question["instruction"] = f"Select exactly {question['choose_n']} answers."

            return question

    @staticmethod
    async def list_questions(
        exam_id: str | None = None,
        topic_id: str | None = None,
        difficulty: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List questions with filters and pagination."""
        async with get_db() as db:
            conditions = []
            params: list[Any] = []

            if exam_id:
                conditions.append("q.exam_id = ?")
                params.append(exam_id)

            if topic_id:
                conditions.append(
                    "q.id IN (SELECT question_id FROM question_topics WHERE topic_id = ?)"
                )
                params.append(topic_id)

            if difficulty:
                conditions.append("q.difficulty = ?")
                params.append(difficulty)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # Get total count
            count_query = f"SELECT COUNT(*) as count FROM questions q WHERE {where_clause}"
            cursor = await db.execute(count_query, params)
            total = (await cursor.fetchone())["count"]

            # Get questions
            query = f"""
                SELECT q.*, qt.code as question_type
                FROM questions q
                JOIN question_types qt ON q.question_type_id = qt.id
                WHERE {where_clause}
                ORDER BY q.created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(query, params + [limit, offset])
            rows = await cursor.fetchall()

            questions = []
            for row in rows:
                q = dict(row)
                q["pattern_tags"] = json.loads(q["pattern_tags"]) if q["pattern_tags"] else []

                # Get topic IDs
                topic_cursor = await db.execute(
                    "SELECT topic_id FROM question_topics WHERE question_id = ?",
                    (q["id"],),
                )
                q["topic_ids"] = [r["topic_id"] for r in await topic_cursor.fetchall()]

                questions.append(q)

            return {
                "questions": questions,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(questions)) < total,
            }

    @staticmethod
    async def search_questions(
        query: str,
        exam_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search questions by keyword."""
        async with get_db() as db:
            search_term = f"%{query}%"
            conditions = ["(q.question_text LIKE ? OR q.explanation LIKE ?)"]
            params: list[Any] = [search_term, search_term]

            if exam_id:
                conditions.append("q.exam_id = ?")
                params.append(exam_id)

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT q.id, q.exam_id, q.question_type_id, q.question_text,
                       q.difficulty, q.pattern_tags, qt.code as question_type,
                       e.name as exam_name
                FROM questions q
                JOIN question_types qt ON q.question_type_id = qt.id
                JOIN exams e ON q.exam_id = e.id
                WHERE {where_clause}
                LIMIT ?
            """
            params.append(limit)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            results = []
            for row in rows:
                result = dict(row)
                result["pattern_tags"] = (
                    json.loads(result["pattern_tags"]) if result["pattern_tags"] else []
                )

                # Create snippet
                text = result["question_text"]
                query_lower = query.lower()
                text_lower = text.lower()

                idx = text_lower.find(query_lower)
                if idx >= 0:
                    start = max(0, idx - 50)
                    end = min(len(text), idx + len(query) + 50)
                    snippet = (
                        ("..." if start > 0 else "")
                        + text[start:end]
                        + ("..." if end < len(text) else "")
                    )
                    result["match_snippet"] = snippet
                else:
                    result["match_snippet"] = (
                        text[:150] + ("..." if len(text) > 150 else "")
                    )

                # Get topics
                topic_cursor = await db.execute(
                    """
                    SELECT t.name FROM topics t
                    JOIN question_topics qt ON t.id = qt.topic_id
                    WHERE qt.question_id = ?
                    """,
                    (result["id"],),
                )
                result["topics"] = [r["name"] for r in await topic_cursor.fetchall()]

                results.append(result)

            return results

    # ==================== PRACTICE SESSIONS ====================

    @staticmethod
    async def create_session(
        exam_id: str,
        session_type: str = "practice",
    ) -> dict[str, Any]:
        """Create a new practice session."""
        session_id = generate_id()
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO practice_sessions (id, exam_id, session_type)
                VALUES (?, ?, ?)
                """,
                (session_id, exam_id, session_type),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT * FROM practice_sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            return dict(row)

    @staticmethod
    async def end_session(session_id: str) -> None:
        """End a practice session."""
        async with get_db() as db:
            await db.execute(
                "UPDATE practice_sessions SET ended_at = datetime('now') WHERE id = ?",
                (session_id,),
            )
            await db.commit()

    @staticmethod
    async def record_attempt(
        session_id: str,
        question_id: str,
        is_correct: bool,
        time_taken_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Record a question attempt and update stats."""
        attempt_id = generate_id()
        async with get_db() as db:
            # Record attempt
            await db.execute(
                """
                INSERT INTO question_attempts (id, session_id, question_id, is_correct, time_taken_seconds)
                VALUES (?, ?, ?, ?, ?)
                """,
                (attempt_id, session_id, question_id, 1 if is_correct else 0, time_taken_seconds),
            )

            # Update stats
            await db.execute(
                """
                INSERT INTO question_stats (question_id, attempt_count, correct_count, last_attempted_at)
                VALUES (?, 1, ?, datetime('now'))
                ON CONFLICT(question_id) DO UPDATE SET
                    attempt_count = attempt_count + 1,
                    correct_count = correct_count + ?,
                    last_attempted_at = datetime('now')
                """,
                (question_id, 1 if is_correct else 0, 1 if is_correct else 0),
            )

            await db.commit()

            cursor = await db.execute(
                "SELECT * FROM question_attempts WHERE id = ?", (attempt_id,)
            )
            row = await cursor.fetchone()
            return dict(row)

    @staticmethod
    async def get_session_results(session_id: str) -> dict[str, Any]:
        """Get results for a practice session."""
        async with get_db() as db:
            # Get session
            cursor = await db.execute(
                "SELECT * FROM practice_sessions WHERE id = ?", (session_id,)
            )
            session = dict(await cursor.fetchone())

            # Get attempts
            cursor = await db.execute(
                """
                SELECT qa.*, q.question_text, q.difficulty
                FROM question_attempts qa
                JOIN questions q ON qa.question_id = q.id
                WHERE qa.session_id = ?
                ORDER BY qa.attempted_at
                """,
                (session_id,),
            )
            attempts = [dict(r) for r in await cursor.fetchall()]

            correct = sum(1 for a in attempts if a["is_correct"])
            total = len(attempts)

            return {
                "session": session,
                "attempts": attempts,
                "correct": correct,
                "total": total,
                "accuracy": correct / total if total > 0 else 0,
            }

    @staticmethod
    async def get_weak_questions(
        exam_id: str,
        limit: int = 20,
        include_unattempted: bool = True,
    ) -> list[dict[str, Any]]:
        """Get questions the user struggles with most, prioritizing by accuracy."""
        async with get_db() as db:
            # Get weak questions (low accuracy, at least 1 attempt)
            cursor = await db.execute(
                """
                SELECT q.*, qs.attempt_count, qs.correct_count,
                       CAST(qs.correct_count AS REAL) / qs.attempt_count AS accuracy,
                       qt.code as question_type
                FROM questions q
                JOIN question_stats qs ON q.id = qs.question_id
                JOIN question_types qt ON q.question_type_id = qt.id
                WHERE q.exam_id = ? AND qs.attempt_count >= 1
                ORDER BY accuracy ASC, qs.attempt_count DESC
                LIMIT ?
                """,
                (exam_id, limit),
            )
            rows = await cursor.fetchall()

            results = []
            for row in rows:
                q = dict(row)
                q["pattern_tags"] = json.loads(q["pattern_tags"]) if q["pattern_tags"] else []
                results.append(q)

            # If we need more questions, add unattempted ones
            if include_unattempted and len(results) < limit:
                remaining = limit - len(results)
                cursor = await db.execute(
                    """
                    SELECT q.*, 0 as attempt_count, 0 as correct_count,
                           NULL as accuracy, qt.code as question_type
                    FROM questions q
                    JOIN question_types qt ON q.question_type_id = qt.id
                    LEFT JOIN question_stats qs ON q.id = qs.question_id
                    WHERE q.exam_id = ? AND (qs.attempt_count IS NULL OR qs.attempt_count = 0)
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (exam_id, remaining),
                )
                unattempted = await cursor.fetchall()
                for row in unattempted:
                    q = dict(row)
                    q["pattern_tags"] = json.loads(q["pattern_tags"]) if q["pattern_tags"] else []
                    results.append(q)

            return results

    @staticmethod
    async def update_session_question_ids(session_id: str, question_ids: list[str]) -> None:
        """Store the question IDs for a session (for recovery after restart)."""
        async with get_db() as db:
            await db.execute(
                "UPDATE practice_sessions SET question_ids = ? WHERE id = ?",
                (json.dumps(question_ids), session_id),
            )
            await db.commit()

    @staticmethod
    async def get_session(session_id: str) -> dict[str, Any] | None:
        """Get a practice session by ID."""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM practice_sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("question_ids"):
                    result["question_ids"] = json.loads(result["question_ids"])
                return result
            return None

    @staticmethod
    async def get_topic_stats(exam_id: str) -> list[dict[str, Any]]:
        """Get accuracy stats broken down by topic."""
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT
                    t.id,
                    t.name,
                    COUNT(DISTINCT qa.id) as attempt_count,
                    COALESCE(SUM(qa.is_correct), 0) as correct_count,
                    CASE
                        WHEN COUNT(qa.id) > 0
                        THEN CAST(SUM(qa.is_correct) AS REAL) / COUNT(qa.id)
                        ELSE NULL
                    END as accuracy
                FROM topics t
                LEFT JOIN question_topics qt ON t.id = qt.topic_id
                LEFT JOIN question_attempts qa ON qt.question_id = qa.question_id
                WHERE t.exam_id = ?
                GROUP BY t.id
                ORDER BY accuracy ASC NULLS LAST
                """,
                (exam_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ==================== ANSWER/QUESTION UPDATES ====================

    @staticmethod
    async def get_answer(answer_id: str) -> dict[str, Any] | None:
        """Get an answer option by ID."""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM answer_options WHERE id = ?",
                (answer_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def get_answers_for_question(question_id: str) -> list[dict[str, Any]]:
        """Get all answers for a question (not randomized, for analysis)."""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM answer_options WHERE question_id = ?",
                (question_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def update_answer(
        answer_id: str,
        option_text: str | None = None,
        is_correct: bool | None = None,
        distractor_reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Update an answer option."""
        async with get_db() as db:
            # Build dynamic update
            updates = []
            params: list[Any] = []

            if option_text is not None:
                updates.append("option_text = ?")
                params.append(option_text)

            if is_correct is not None:
                updates.append("is_correct = ?")
                params.append(1 if is_correct else 0)

            if distractor_reason is not None:
                updates.append("distractor_reason = ?")
                params.append(distractor_reason)

            if not updates:
                # No changes, just return current state
                return await Repository.get_answer(answer_id)

            params.append(answer_id)
            query = f"UPDATE answer_options SET {', '.join(updates)} WHERE id = ?"

            await db.execute(query, params)
            await db.commit()

            return await Repository.get_answer(answer_id)

    @staticmethod
    async def update_question(
        question_id: str,
        question_text: str | None = None,
        explanation: str | None = None,
        difficulty: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a question's text and metadata."""
        async with get_db() as db:
            updates = []
            params: list[Any] = []

            if question_text is not None:
                updates.append("question_text = ?")
                params.append(question_text)

            if explanation is not None:
                updates.append("explanation = ?")
                params.append(explanation)

            if difficulty is not None:
                updates.append("difficulty = ?")
                params.append(difficulty)

            if not updates:
                return await Repository.get_question(question_id, randomize_answers=False)

            params.append(question_id)
            query = f"UPDATE questions SET {', '.join(updates)} WHERE id = ?"

            await db.execute(query, params)
            await db.commit()

            return await Repository.get_question(question_id, randomize_answers=False)

    @staticmethod
    async def bulk_update_answers(
        question_id: str,
        updates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Update multiple answers for a question in a single transaction."""
        async with get_db() as db:
            for update in updates:
                answer_id = update.get("answer_id")
                if not answer_id:
                    continue

                # Verify answer belongs to question
                cursor = await db.execute(
                    "SELECT id FROM answer_options WHERE id = ? AND question_id = ?",
                    (answer_id, question_id),
                )
                if not await cursor.fetchone():
                    continue

                set_clauses = []
                params: list[Any] = []

                if "option_text" in update:
                    set_clauses.append("option_text = ?")
                    params.append(update["option_text"])

                if "distractor_reason" in update:
                    set_clauses.append("distractor_reason = ?")
                    params.append(update["distractor_reason"])

                if "is_correct" in update:
                    set_clauses.append("is_correct = ?")
                    params.append(1 if update["is_correct"] else 0)

                if set_clauses:
                    params.append(answer_id)
                    query = f"UPDATE answer_options SET {', '.join(set_clauses)} WHERE id = ?"
                    await db.execute(query, params)

            await db.commit()

        return await Repository.get_answers_for_question(question_id)

    # ==================== BIAS ANALYSIS QUERIES ====================

    @staticmethod
    async def get_exam_questions_with_answers(
        exam_id: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Get all questions with their answers for bias analysis."""
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT q.id, q.question_text, q.difficulty, qt.code as question_type
                FROM questions q
                JOIN question_types qt ON q.question_type_id = qt.id
                WHERE q.exam_id = ?
                LIMIT ?
                """,
                (exam_id, limit),
            )
            questions = [dict(row) for row in await cursor.fetchall()]

            # Get answers for each question
            for question in questions:
                cursor = await db.execute(
                    "SELECT id, option_text, is_correct, distractor_reason FROM answer_options WHERE question_id = ?",
                    (question["id"],),
                )
                question["answers"] = [dict(row) for row in await cursor.fetchall()]

            return questions
