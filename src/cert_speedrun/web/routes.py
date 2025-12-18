"""Web routes for cert speedrun optimizer."""

import random
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..db.database import ensure_db_exists
from ..db.repository import Repository

router = APIRouter()

# Initialize templates directly to avoid circular import
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR)


# ==================== MAIN PAGES ====================


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - list all exams."""
    await ensure_db_exists()
    exams = await Repository.list_exams(include_stats=True)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "exams": exams},
    )


@router.get("/exam/{exam_id}", response_class=HTMLResponse)
async def exam_detail(request: Request, exam_id: str):
    """Exam detail page - show topics and stats."""
    await ensure_db_exists()
    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    topics = await Repository.list_topics(exam_id, include_stats=True)
    questions = await Repository.list_questions(exam_id=exam_id, limit=10)

    return templates.TemplateResponse(
        "exam.html",
        {
            "request": request,
            "exam": exam,
            "topics": topics,
            "recent_questions": questions["questions"],
            "total_questions": questions["total"],
        },
    )


# ==================== PRACTICE SESSION ====================


# Store active sessions in memory (in production, use Redis or DB)
active_sessions: dict[str, dict] = {}


@router.get("/exam/{exam_id}/practice", response_class=HTMLResponse)
async def practice_start(
    request: Request,
    exam_id: str,
    topic_id: Annotated[str | None, Query()] = None,
    mode: Annotated[str, Query()] = "practice",
):
    """Start a practice session."""
    await ensure_db_exists()
    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    topics = await Repository.list_topics(exam_id, include_stats=True)

    # Create session
    session = await Repository.create_session(exam_id, session_type=mode)
    session_id = session["id"]

    # Get questions for the session
    if mode == "speedrun":
        questions = await Repository.get_weak_questions(exam_id, limit=20)
        if not questions:
            # Fall back to regular questions if no weak ones
            result = await Repository.list_questions(exam_id=exam_id, topic_id=topic_id, limit=20)
            questions = result["questions"]
    else:
        result = await Repository.list_questions(exam_id=exam_id, topic_id=topic_id, limit=20)
        questions = result["questions"]

    # Shuffle questions
    random.shuffle(questions)

    # Store session state
    question_ids = [q["id"] for q in questions]
    active_sessions[session_id] = {
        "exam_id": exam_id,
        "question_ids": question_ids,
        "current_index": 0,
        "answers": [],
        "start_time": None,
    }

    # Persist question IDs to DB for session recovery
    await Repository.update_session_question_ids(session_id, question_ids)

    return templates.TemplateResponse(
        "practice.html",
        {
            "request": request,
            "exam": exam,
            "topics": topics,
            "session_id": session_id,
            "total_questions": len(questions),
            "mode": mode,
        },
    )


@router.get("/practice/{session_id}/question", response_class=HTMLResponse)
async def get_next_question(request: Request, session_id: str):
    """HTMX: Get the next question in the session."""
    # Try in-memory first, then recover from DB
    if session_id not in active_sessions:
        # Attempt recovery from DB
        session_data = await Repository.get_session(session_id)
        if not session_data or not session_data.get("question_ids"):
            return HTMLResponse("<p>Session expired. Please start a new practice session.</p>")

        # Get already-answered questions to determine current_index
        results = await Repository.get_session_results(session_id)
        answered_ids = {a["question_id"] for a in results["attempts"]}

        # Rebuild session state
        active_sessions[session_id] = {
            "exam_id": session_data["exam_id"],
            "question_ids": session_data["question_ids"],
            "current_index": len(answered_ids),
            "answers": [],
            "start_time": None,
        }

    session = active_sessions[session_id]
    question_ids = session["question_ids"]
    current_index = session["current_index"]

    if current_index >= len(question_ids):
        # Session complete
        return templates.TemplateResponse(
            "components/session_complete.html",
            {"request": request, "session_id": session_id},
        )

    question_id = question_ids[current_index]
    question = await Repository.get_question(question_id, randomize_answers=True)

    return templates.TemplateResponse(
        "components/question.html",
        {
            "request": request,
            "question": question,
            "session_id": session_id,
            "current": current_index + 1,
            "total": len(question_ids),
        },
    )


@router.post("/practice/{session_id}/submit", response_class=HTMLResponse)
async def submit_answer(
    request: Request,
    session_id: str,
    question_id: Annotated[str, Form()],
    selected: Annotated[list[str], Form()] = [],
):
    """HTMX: Submit an answer and get feedback."""
    if session_id not in active_sessions:
        return HTMLResponse("<p>Session expired.</p>")

    # Get the question with answers (not randomized for checking)
    question = await Repository.get_question(question_id, randomize_answers=False)
    if not question:
        return HTMLResponse("<p>Question not found.</p>")

    # Determine correct answers
    correct_ids = {a["id"] for a in question["answers"] if a["is_correct"]}
    selected_set = set(selected)

    # Check if correct
    is_correct = selected_set == correct_ids

    # Record the attempt
    await Repository.record_attempt(
        session_id=session_id,
        question_id=question_id,
        is_correct=is_correct,
    )

    # Update session state
    session = active_sessions[session_id]
    session["current_index"] += 1
    session["answers"].append({
        "question_id": question_id,
        "is_correct": is_correct,
        "selected": selected,
    })

    return templates.TemplateResponse(
        "components/answer_feedback.html",
        {
            "request": request,
            "question": question,
            "is_correct": is_correct,
            "selected_ids": selected_set,
            "correct_ids": correct_ids,
            "session_id": session_id,
            "has_more": session["current_index"] < len(session["question_ids"]),
        },
    )


@router.get("/practice/{session_id}/results", response_class=HTMLResponse)
async def session_results(request: Request, session_id: str):
    """Show practice session results."""
    results = await Repository.get_session_results(session_id)

    # Get exam info
    exam = await Repository.get_exam(results["session"]["exam_id"])

    # Clean up session from memory
    if session_id in active_sessions:
        del active_sessions[session_id]

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "exam": exam,
            "results": results,
        },
    )


# ==================== SPEEDRUN MODE ====================


@router.get("/exam/{exam_id}/speedrun", response_class=HTMLResponse)
async def speedrun_start(request: Request, exam_id: str):
    """Start a speedrun session targeting weak questions."""
    # Redirect to practice with speedrun mode
    return await practice_start(request, exam_id, mode="speedrun")


# ==================== PERFORMANCE STATS ====================


@router.get("/exam/{exam_id}/stats", response_class=HTMLResponse)
async def exam_stats(request: Request, exam_id: str):
    """Show performance statistics for an exam."""
    await ensure_db_exists()
    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    topic_stats = await Repository.get_topic_stats(exam_id)
    weak_questions = await Repository.get_weak_questions(exam_id, limit=10, include_unattempted=False)

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "exam": exam,
            "topic_stats": topic_stats,
            "weak_questions": weak_questions,
        },
    )
