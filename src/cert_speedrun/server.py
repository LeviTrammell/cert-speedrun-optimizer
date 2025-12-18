"""MCP Server for Cert Speedrun Optimizer."""

from typing import Annotated, Literal
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .db.database import ensure_db_exists
from .db.repository import Repository
from .models import AnswerOption, validate_question_answers
from .answer_validation import (
    BiasThresholds,
    validate_answer_bias,
    format_bias_error_message,
    get_answer_length_guidelines,
)

# Initialize FastMCP server
mcp = FastMCP(
    name="CertSpeedrunOptimizer",
    instructions="""
    This MCP server helps create and manage certification exam question banks.

    ## Recommended Workflow for Creating Questions

    To avoid common LLM biases in answer generation:

    1. Call `get_answer_guidelines` FIRST to understand length/format constraints
    2. Draft your question and answers following the guidelines
    3. Call `analyze_proposed_answers` to validate BEFORE committing
    4. Only call `create_question` once validation passes

    ## Common Biases to Avoid

    - **Length bias**: Correct answers should NOT be longer than distractors
    - **Distractor weakness**: Incorrect answers must be plausible, not obviously wrong
    - Keep all answers within 50% of each other in length
    - Each distractor should represent a common misconception

    ## Question Types

    - single: Traditional multiple choice (1 correct answer)
    - choose_n: Select exactly N answers (e.g., "Select TWO")
    - select_all: Select all correct answers (variable count)

    ## Key Design Decisions

    Answer options are stored WITHOUT ordinal position and randomized
    at retrieval time to counter LLM bias toward A/B answers.

    ## Available Tool Categories

    - **Creation**: create_exam, create_topic, create_question
    - **Listing**: list_exams, list_topics, list_questions, search_questions, get_question
    - **Bias Prevention**: get_answer_guidelines, analyze_proposed_answers
    - **Quality Analysis**: analyze_question_quality, analyze_exam_bias
    - **Editing**: update_answer, update_question, bulk_update_answers
    """,
)


# ==================== EXAM TOOLS ====================


@mcp.tool
async def create_exam(
    name: Annotated[str, "Full name of the certification exam (e.g., 'AWS Solutions Architect Associate')"],
    vendor: Annotated[str, "Certification vendor (e.g., 'AWS', 'Azure', 'GCP', 'CompTIA')"],
    exam_code: Annotated[str | None, "Official exam code (e.g., 'SAA-C03')"] = None,
    description: Annotated[str | None, "Description of the certification"] = None,
    passing_score: Annotated[int | None, "Passing score percentage (0-100)"] = None,
    time_limit_minutes: Annotated[int | None, "Total exam time in minutes"] = None,
) -> dict:
    """
    Create a new certification exam container.

    Use this tool when starting to build a question bank for a new certification.
    The exam serves as the top-level container for topics and questions.
    """
    await ensure_db_exists()

    # Check for duplicate
    existing = await Repository.get_exam_by_name(name)
    if existing:
        raise ToolError(f"Exam '{name}' already exists with ID: {existing['id']}")

    # Validate passing_score
    if passing_score is not None and not (0 <= passing_score <= 100):
        raise ToolError("passing_score must be between 0 and 100")

    exam = await Repository.create_exam(
        name=name,
        vendor=vendor,
        exam_code=exam_code,
        description=description,
        passing_score=passing_score,
        time_limit_minutes=time_limit_minutes,
    )

    return {
        "id": exam["id"],
        "name": exam["name"],
        "vendor": exam["vendor"],
        "exam_code": exam["exam_code"],
        "description": exam["description"],
        "passing_score": exam["passing_score"],
        "time_limit_minutes": exam["time_limit_minutes"],
        "created_at": exam["created_at"],
    }


@mcp.tool
async def list_exams(
    vendor: Annotated[str | None, "Filter by vendor (e.g., 'AWS')"] = None,
    include_stats: Annotated[bool, "Include question and topic counts"] = False,
) -> list[dict]:
    """
    List all certification exams.

    Use this tool to discover available exams before creating topics or questions.
    """
    await ensure_db_exists()
    exams = await Repository.list_exams(vendor=vendor, include_stats=include_stats)
    return exams


# ==================== TOPIC TOOLS ====================


@mcp.tool
async def create_topic(
    exam_id: Annotated[str, "ID of the exam this topic belongs to"],
    name: Annotated[str, "Topic name (e.g., 'Networking', 'Security')"],
    description: Annotated[str | None, "Description of what this topic covers"] = None,
    weight_percent: Annotated[float | None, "Percentage of exam this topic represents (0-100)"] = None,
) -> dict:
    """
    Create a topic/category within an exam.

    Topics are flat tags used to categorize questions by subject area.
    A question can belong to multiple topics.
    """
    await ensure_db_exists()

    # Verify exam exists
    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise ToolError(f"Exam with ID '{exam_id}' not found")

    # Check for duplicate
    existing = await Repository.get_topic_by_name(exam_id, name)
    if existing:
        raise ToolError(f"Topic '{name}' already exists in exam '{exam['name']}'")

    # Validate weight
    if weight_percent is not None and not (0 <= weight_percent <= 100):
        raise ToolError("weight_percent must be between 0 and 100")

    topic = await Repository.create_topic(
        exam_id=exam_id,
        name=name,
        description=description,
        weight_percent=weight_percent,
    )

    return {
        "id": topic["id"],
        "exam_id": topic["exam_id"],
        "name": topic["name"],
        "description": topic["description"],
        "weight_percent": topic["weight_percent"],
        "created_at": topic["created_at"],
    }


@mcp.tool
async def list_topics(
    exam_id: Annotated[str, "ID of the exam to list topics for"],
    include_stats: Annotated[bool, "Include question counts per topic"] = False,
) -> list[dict]:
    """
    List all topics for a specific exam.

    Use this tool to see available categories before creating or tagging questions.
    """
    await ensure_db_exists()

    # Verify exam exists
    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise ToolError(f"Exam with ID '{exam_id}' not found")

    topics = await Repository.list_topics(exam_id=exam_id, include_stats=include_stats)
    return topics


# ==================== QUESTION TOOLS ====================


@mcp.tool
async def create_question(
    exam_id: Annotated[str, "ID of the exam this question belongs to"],
    question_text: Annotated[str, "The full question text"],
    question_type: Annotated[
        Literal["single", "choose_n", "select_all"],
        "Type: single (1 answer), choose_n (exactly N), select_all (all correct)",
    ],
    answers: Annotated[
        list[dict],
        "List of answers. Each: {text: str, is_correct: bool, distractor_reason?: str}",
    ],
    topic_ids: Annotated[list[str] | None, "Topic IDs to tag this question with"] = None,
    choose_n: Annotated[int | None, "For choose_n type: how many answers to select"] = None,
    explanation: Annotated[str | None, "Explanation of why the answer is correct"] = None,
    difficulty: Annotated[Literal["easy", "medium", "hard"], "Difficulty level"] = "medium",
    pattern_tags: Annotated[list[str] | None, "Tags like 'scenario-based', 'calculation'"] = None,
    source: Annotated[str | None, "Source of the question"] = None,
    skip_bias_check: Annotated[bool, "Skip answer bias validation (not recommended)"] = False,
) -> dict:
    """
    Create a question with answer options.

    IMPORTANT: Answers are stored WITHOUT ordinal position. They will be
    randomized every time the question is retrieved. This counters LLM
    bias toward putting correct answers in position A or B.

    RECOMMENDED WORKFLOW:
    1. Call get_answer_guidelines first for length constraints
    2. Call analyze_proposed_answers to validate before creating
    3. Only then call this tool

    Question types:
    - single: Exactly 1 correct answer (traditional multiple choice)
    - choose_n: Exactly N correct answers (requires choose_n parameter)
    - select_all: Variable correct answers (at least 1)
    """
    await ensure_db_exists()

    # Verify exam exists
    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise ToolError(f"Exam with ID '{exam_id}' not found")

    # Validate answers
    if len(answers) < 2:
        raise ToolError("Questions must have at least 2 answer options")

    # Parse answers into AnswerOption objects for validation
    try:
        answer_objs = [AnswerOption(**a) for a in answers]
    except Exception as e:
        raise ToolError(f"Invalid answer format: {e}")

    # Validate answer configuration for question type
    try:
        validate_question_answers(question_type, answer_objs, choose_n)
    except ValueError as e:
        raise ToolError(str(e))

    # Run bias validation unless skipped
    if not skip_bias_check:
        answer_dicts = [
            {
                "text": a.text,
                "is_correct": a.is_correct,
                "distractor_reason": a.distractor_reason,
            }
            for a in answer_objs
        ]
        bias_result = validate_answer_bias(answer_dicts)

        if not bias_result.is_valid:
            raise ToolError(format_bias_error_message(bias_result))

    # Verify topics exist
    if topic_ids:
        for topic_id in topic_ids:
            topic = await Repository.get_topic(topic_id)
            if not topic:
                raise ToolError(f"Topic with ID '{topic_id}' not found")
            if topic["exam_id"] != exam_id:
                raise ToolError(f"Topic '{topic_id}' does not belong to exam '{exam_id}'")

    question = await Repository.create_question(
        exam_id=exam_id,
        question_text=question_text,
        question_type=question_type,
        answers=[a.model_dump() for a in answer_objs],
        topic_ids=topic_ids,
        choose_n=choose_n,
        explanation=explanation,
        difficulty=difficulty,
        pattern_tags=pattern_tags,
        source=source,
    )

    correct_count = sum(1 for a in answer_objs if a.is_correct)

    return {
        "id": question["id"],
        "exam_id": question["exam_id"],
        "question_type": question["question_type"],
        "choose_n": question["choose_n"],
        "question_text": question["question_text"][:100] + "..." if len(question["question_text"]) > 100 else question["question_text"],
        "answer_count": len(answers),
        "correct_count": correct_count,
        "topic_ids": topic_ids or [],
        "difficulty": question["difficulty"],
        "pattern_tags": question["pattern_tags"],
        "created_at": question["created_at"],
    }


@mcp.tool
async def list_questions(
    exam_id: Annotated[str | None, "Filter by exam ID"] = None,
    topic_id: Annotated[str | None, "Filter by topic ID"] = None,
    difficulty: Annotated[Literal["easy", "medium", "hard"] | None, "Filter by difficulty"] = None,
    limit: Annotated[int, "Maximum questions to return (1-500)"] = 50,
    offset: Annotated[int, "Pagination offset"] = 0,
) -> dict:
    """
    List questions with optional filtering and pagination.

    Use this tool to browse the question bank or check coverage by topic.
    """
    await ensure_db_exists()

    # Validate limit
    if limit < 1 or limit > 500:
        raise ToolError("limit must be between 1 and 500")

    result = await Repository.list_questions(
        exam_id=exam_id,
        topic_id=topic_id,
        difficulty=difficulty,
        limit=limit,
        offset=offset,
    )

    return result


@mcp.tool
async def get_question(
    question_id: Annotated[str, "ID of the question to retrieve"],
) -> dict:
    """
    Get a single question with full details and randomized answer order.

    IMPORTANT: Answer options are returned in RANDOM order every time
    this tool is called. This prevents memorization of answer positions.
    """
    await ensure_db_exists()

    question = await Repository.get_question(question_id, randomize_answers=True)
    if not question:
        raise ToolError(f"Question with ID '{question_id}' not found")

    return question


@mcp.tool
async def search_questions(
    query: Annotated[str, "Search query to match against question text"],
    exam_id: Annotated[str | None, "Limit search to specific exam"] = None,
    limit: Annotated[int, "Maximum results (1-100)"] = 20,
) -> list[dict]:
    """
    Search questions by keyword or pattern.

    Use this tool to find questions about specific concepts or services.
    Searches question text and explanations.
    """
    await ensure_db_exists()

    if limit < 1 or limit > 100:
        raise ToolError("limit must be between 1 and 100")

    results = await Repository.search_questions(
        query=query,
        exam_id=exam_id,
        limit=limit,
    )

    return results


# ==================== BIAS PREVENTION TOOLS ====================


@mcp.tool
async def get_answer_guidelines(
    question_type: Annotated[
        Literal["single", "choose_n", "select_all"],
        "Type of question being created",
    ],
    num_answers: Annotated[int, "Number of answer options (typically 4-5)"] = 4,
    target_length: Annotated[int | None, "Target answer length in characters (default: 80)"] = None,
) -> dict:
    """
    Get guidelines for writing bias-free answers BEFORE generating them.

    Call this tool FIRST when creating questions to understand constraints.
    Returns target lengths, rules, and anti-patterns to avoid.

    This helps prevent common LLM biases like:
    - Making correct answers longer/more detailed than distractors
    - Writing obviously-wrong distractors
    - Inconsistent answer lengths
    """
    guidelines = get_answer_length_guidelines(
        question_type=question_type,
        num_answers=num_answers,
        target_length=target_length,
    )

    return {
        "question_type": question_type,
        "num_answers": num_answers,
        **guidelines,
    }


@mcp.tool
async def analyze_proposed_answers(
    question_type: Annotated[
        Literal["single", "choose_n", "select_all"],
        "Type of question",
    ],
    answers: Annotated[
        list[dict],
        "List of proposed answers: [{text: str, is_correct: bool, distractor_reason?: str}]",
    ],
    choose_n: Annotated[int | None, "For choose_n type: how many answers to select"] = None,
) -> dict:
    """
    Analyze proposed answers for bias BEFORE creating the question.

    Call this after drafting answers but BEFORE calling create_question.
    Returns validation status, issues to fix, and quality metrics.

    If validation fails, rewrite answers to address the issues and re-analyze.
    """
    # Convert to format expected by validation
    answer_dicts = [
        {
            "text": a.get("text", ""),
            "is_correct": a.get("is_correct", False),
            "distractor_reason": a.get("distractor_reason"),
        }
        for a in answers
    ]

    # Validate answer configuration for question type first
    try:
        answer_objs = [AnswerOption(**a) for a in answer_dicts]
        validate_question_answers(question_type, answer_objs, choose_n)
    except ValueError as e:
        return {
            "is_valid": False,
            "structural_error": str(e),
            "bias_analysis": None,
        }

    # Run bias analysis
    result = validate_answer_bias(answer_dicts)

    return {
        "is_valid": result.is_valid,
        "quality_score": result.quality_score,
        "quality_grade": result.quality_grade,
        "issues": [
            {
                "type": issue.issue_type.value,
                "severity": issue.severity.value,
                "message": issue.message,
                "details": issue.details,
            }
            for issue in result.issues
        ],
        "warnings": [
            {
                "type": w.issue_type.value,
                "severity": w.severity.value,
                "message": w.message,
                "details": w.details,
            }
            for w in result.warnings
        ],
        "metrics": {
            "mean_length": result.metrics.mean_length,
            "correct_avg_length": result.metrics.correct_avg_length,
            "distractor_avg_length": result.metrics.distractor_avg_length,
            "correct_distractor_ratio": result.metrics.correct_distractor_ratio,
            "length_variance_percent": result.metrics.length_variance_percent,
        }
        if result.metrics
        else None,
        "recommendation": "Answers pass validation. Proceed with create_question."
        if result.is_valid
        else "Address the issues above before creating the question.",
    }


# ==================== QUALITY ANALYSIS TOOLS ====================


@mcp.tool
async def analyze_question_quality(
    question_id: Annotated[str, "ID of the question to analyze"],
) -> dict:
    """
    Analyze a single question for answer bias and quality issues.

    Returns a quality score (0-1), letter grade (A-F), and specific issues.
    Use this to identify questions that need improvement.
    """
    await ensure_db_exists()

    question = await Repository.get_question(question_id, randomize_answers=False)
    if not question:
        raise ToolError(f"Question with ID '{question_id}' not found")

    # Convert answers to validation format
    answer_dicts = [
        {
            "text": a["option_text"],
            "is_correct": bool(a["is_correct"]),
            "distractor_reason": a.get("distractor_reason"),
        }
        for a in question["answers"]
    ]

    result = validate_answer_bias(answer_dicts)

    return {
        "question_id": question_id,
        "question_preview": question["question_text"][:100] + "..."
        if len(question["question_text"]) > 100
        else question["question_text"],
        "quality_score": result.quality_score,
        "quality_grade": result.quality_grade,
        "is_valid": result.is_valid,
        "issues": [
            {
                "type": issue.issue_type.value,
                "message": issue.message,
            }
            for issue in result.issues
        ],
        "warnings": [
            {
                "type": w.issue_type.value,
                "message": w.message,
            }
            for w in result.warnings
        ],
        "metrics": {
            "mean_length": result.metrics.mean_length,
            "correct_avg_length": result.metrics.correct_avg_length,
            "distractor_avg_length": result.metrics.distractor_avg_length,
            "correct_distractor_ratio": result.metrics.correct_distractor_ratio,
        }
        if result.metrics
        else None,
        "answers": [
            {
                "id": a["id"],
                "text_preview": a["option_text"][:50] + "..."
                if len(a["option_text"]) > 50
                else a["option_text"],
                "length": len(a["option_text"]),
                "is_correct": bool(a["is_correct"]),
                "has_distractor_reason": bool(a.get("distractor_reason")),
            }
            for a in question["answers"]
        ],
    }


@mcp.tool
async def analyze_exam_bias(
    exam_id: Annotated[str, "ID of the exam to analyze"],
    include_question_breakdown: Annotated[
        bool, "Include per-question analysis (can be large)"
    ] = False,
) -> dict:
    """
    Analyze all questions in an exam for aggregate bias metrics.

    Returns overall quality distribution, worst offenders, and recommendations.
    Use this to get a high-level view of question bank quality.
    """
    await ensure_db_exists()

    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise ToolError(f"Exam with ID '{exam_id}' not found")

    questions = await Repository.get_exam_questions_with_answers(exam_id)

    if not questions:
        return {
            "exam_id": exam_id,
            "exam_name": exam["name"],
            "total_questions": 0,
            "message": "No questions found for this exam.",
        }

    # Analyze each question
    results = []
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    total_score = 0
    worst_offenders = []

    for q in questions:
        answer_dicts = [
            {
                "text": a["option_text"],
                "is_correct": bool(a["is_correct"]),
                "distractor_reason": a.get("distractor_reason"),
            }
            for a in q["answers"]
        ]

        analysis = validate_answer_bias(answer_dicts)
        total_score += analysis.quality_score
        grade_counts[analysis.quality_grade] += 1

        question_result = {
            "question_id": q["id"],
            "quality_score": analysis.quality_score,
            "quality_grade": analysis.quality_grade,
            "issue_count": len(analysis.issues),
        }

        if analysis.quality_grade in ("D", "F"):
            worst_offenders.append(
                {
                    "question_id": q["id"],
                    "question_preview": q["question_text"][:80] + "..."
                    if len(q["question_text"]) > 80
                    else q["question_text"],
                    "quality_grade": analysis.quality_grade,
                    "issues": [i.message for i in analysis.issues[:3]],
                }
            )

        results.append(question_result)

    avg_score = total_score / len(questions)

    response = {
        "exam_id": exam_id,
        "exam_name": exam["name"],
        "total_questions": len(questions),
        "average_quality_score": round(avg_score, 3),
        "grade_distribution": grade_counts,
        "worst_offenders": worst_offenders[:10],  # Top 10 worst
        "recommendations": [],
    }

    # Add recommendations
    if grade_counts["F"] > 0:
        response["recommendations"].append(
            f"{grade_counts['F']} questions have failing grades and need immediate attention."
        )
    if grade_counts["D"] > 0:
        response["recommendations"].append(
            f"{grade_counts['D']} questions have D grades and should be reviewed."
        )
    if avg_score < 0.7:
        response["recommendations"].append(
            "Overall quality is below target. Consider reviewing answer length balance."
        )

    if include_question_breakdown:
        response["question_breakdown"] = results

    return response


# ==================== EDITING TOOLS ====================


@mcp.tool
async def update_answer(
    answer_id: Annotated[str, "ID of the answer option to update"],
    option_text: Annotated[str | None, "New answer text"] = None,
    is_correct: Annotated[bool | None, "Update correctness flag"] = None,
    distractor_reason: Annotated[
        str | None, "Explanation of why this distractor is tempting"
    ] = None,
) -> dict:
    """
    Update an individual answer option.

    Use this to fix bias issues identified by analyze_question_quality.
    At least one of option_text, is_correct, or distractor_reason must be provided.
    """
    await ensure_db_exists()

    # Verify answer exists
    existing = await Repository.get_answer(answer_id)
    if not existing:
        raise ToolError(f"Answer with ID '{answer_id}' not found")

    if option_text is None and is_correct is None and distractor_reason is None:
        raise ToolError("At least one field must be provided to update")

    updated = await Repository.update_answer(
        answer_id=answer_id,
        option_text=option_text,
        is_correct=is_correct,
        distractor_reason=distractor_reason,
    )

    return {
        "id": updated["id"],
        "question_id": updated["question_id"],
        "option_text": updated["option_text"],
        "is_correct": bool(updated["is_correct"]),
        "distractor_reason": updated["distractor_reason"],
        "updated": True,
    }


@mcp.tool
async def update_question(
    question_id: Annotated[str, "ID of the question to update"],
    question_text: Annotated[str | None, "New question text"] = None,
    explanation: Annotated[str | None, "New explanation"] = None,
    difficulty: Annotated[Literal["easy", "medium", "hard"] | None, "New difficulty"] = None,
) -> dict:
    """
    Update a question's text and metadata.

    Use this to clarify question wording or update explanations.
    To update answers, use update_answer or bulk_update_answers instead.
    """
    await ensure_db_exists()

    # Verify question exists
    existing = await Repository.get_question(question_id, randomize_answers=False)
    if not existing:
        raise ToolError(f"Question with ID '{question_id}' not found")

    if question_text is None and explanation is None and difficulty is None:
        raise ToolError("At least one field must be provided to update")

    updated = await Repository.update_question(
        question_id=question_id,
        question_text=question_text,
        explanation=explanation,
        difficulty=difficulty,
    )

    return {
        "id": updated["id"],
        "question_text": updated["question_text"][:100] + "..."
        if len(updated["question_text"]) > 100
        else updated["question_text"],
        "explanation": updated["explanation"][:100] + "..."
        if updated["explanation"] and len(updated["explanation"]) > 100
        else updated["explanation"],
        "difficulty": updated["difficulty"],
        "updated": True,
    }


@mcp.tool
async def bulk_update_answers(
    question_id: Annotated[str, "ID of the question whose answers to update"],
    updates: Annotated[
        list[dict],
        "List of updates: [{answer_id: str, option_text?: str, distractor_reason?: str}]",
    ],
) -> dict:
    """
    Update multiple answers for a question in one operation.

    Efficient way to rebalance answer lengths across all options.
    Each update dict must include answer_id, plus fields to change.
    """
    await ensure_db_exists()

    # Verify question exists
    question = await Repository.get_question(question_id, randomize_answers=False)
    if not question:
        raise ToolError(f"Question with ID '{question_id}' not found")

    if not updates:
        raise ToolError("At least one update must be provided")

    # Validate update format
    for i, update in enumerate(updates):
        if "answer_id" not in update:
            raise ToolError(f"Update {i + 1} missing required 'answer_id' field")

    updated_answers = await Repository.bulk_update_answers(question_id, updates)

    # Re-analyze after updates
    answer_dicts = [
        {
            "text": a["option_text"],
            "is_correct": bool(a["is_correct"]),
            "distractor_reason": a.get("distractor_reason"),
        }
        for a in updated_answers
    ]
    analysis = validate_answer_bias(answer_dicts)

    return {
        "question_id": question_id,
        "updates_applied": len(updates),
        "answers": [
            {
                "id": a["id"],
                "option_text": a["option_text"][:50] + "..."
                if len(a["option_text"]) > 50
                else a["option_text"],
                "length": len(a["option_text"]),
                "is_correct": bool(a["is_correct"]),
            }
            for a in updated_answers
        ],
        "new_quality_score": analysis.quality_score,
        "new_quality_grade": analysis.quality_grade,
        "remaining_issues": len(analysis.issues),
    }


# ==================== BATCH OPERATIONS ====================


@mcp.tool
async def get_biased_questions(
    exam_id: Annotated[str, "ID of the exam to analyze"],
    min_grade: Annotated[
        Literal["F", "D", "C"],
        "Return questions with this grade or worse"
    ] = "D",
    limit: Annotated[int, "Maximum questions to return (1-100)"] = 20,
) -> dict:
    """
    Get a batch of biased questions that need fixing, with specific fix instructions.

    Returns questions sorted by severity (worst first) with:
    - Current answer lengths and the target length
    - Specific instructions: "shorten by X chars" or "expand by X chars"
    - Answer IDs for use with bulk_update_answers

    Use this to identify questions needing fixes, then generate new answer
    text and apply with bulk_update_answers.
    """
    await ensure_db_exists()

    exam = await Repository.get_exam(exam_id)
    if not exam:
        raise ToolError(f"Exam with ID '{exam_id}' not found")

    grade_thresholds = {"F": 0.6, "D": 0.7, "C": 0.8}
    max_score = grade_thresholds.get(min_grade, 0.7)

    questions = await Repository.get_exam_questions_with_answers(exam_id, limit=500)

    biased_questions = []

    for q in questions:
        answer_dicts = [
            {
                "text": a["option_text"],
                "is_correct": bool(a["is_correct"]),
            }
            for a in q["answers"]
        ]

        result = validate_answer_bias(answer_dicts)

        if result.quality_score >= max_score:
            continue

        # Calculate target length (balanced mean)
        lengths = [len(a["option_text"]) for a in q["answers"]]
        target_length = int(sum(lengths) / len(lengths))

        # Generate fix instructions for each answer
        answer_instructions = []
        for a in q["answers"]:
            current_len = len(a["option_text"])
            diff = current_len - target_length

            if abs(diff) <= target_length * 0.2:
                instruction = "OK - within range"
            elif diff > 0:
                instruction = f"SHORTEN by ~{diff} chars"
            else:
                instruction = f"EXPAND by ~{abs(diff)} chars"

            answer_instructions.append({
                "answer_id": a["id"],
                "text": a["option_text"],
                "is_correct": bool(a["is_correct"]),
                "current_length": current_len,
                "instruction": instruction,
            })

        biased_questions.append({
            "question_id": q["id"],
            "question_text": q["question_text"],
            "quality_score": round(result.quality_score, 3),
            "quality_grade": result.quality_grade,
            "target_length": target_length,
            "correct_to_distractor_ratio": round(result.metrics.correct_distractor_ratio, 2) if result.metrics else None,
            "answers": answer_instructions,
            "primary_issue": result.issues[0].message if result.issues else "Length imbalance",
        })

    # Sort by score (worst first)
    biased_questions.sort(key=lambda x: x["quality_score"])

    return {
        "exam_id": exam_id,
        "exam_name": exam["name"],
        "total_questions": len(questions),
        "biased_count": len(biased_questions),
        "returned_count": min(limit, len(biased_questions)),
        "questions": biased_questions[:limit],
        "usage_hint": "For each question, rewrite answers to match target_length, then call bulk_update_answers with the new text.",
    }


# Entry point for running the server
if __name__ == "__main__":
    mcp.run()
