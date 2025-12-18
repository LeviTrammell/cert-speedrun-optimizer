"""Pydantic models for cert speedrun optimizer."""

from pydantic import BaseModel, Field
from typing import Literal


class AnswerOption(BaseModel):
    """Answer option for a question."""

    text: str = Field(..., description="The answer text")
    is_correct: bool = Field(..., description="Whether this is a correct answer")
    distractor_reason: str | None = Field(
        None, description="For incorrect answers: why this option is tempting"
    )


class CreateExamRequest(BaseModel):
    """Request to create an exam."""

    name: str = Field(..., description="Name of the certification exam")
    vendor: str = Field(..., description="Certification vendor (e.g., AWS, Azure)")
    exam_code: str | None = Field(None, description="Official exam code")
    description: str | None = Field(None, description="Exam description")
    passing_score: int | None = Field(None, ge=0, le=100, description="Passing score percentage")
    time_limit_minutes: int | None = Field(None, ge=1, description="Exam time limit")


class CreateTopicRequest(BaseModel):
    """Request to create a topic."""

    exam_id: str = Field(..., description="ID of the exam")
    name: str = Field(..., description="Topic name")
    description: str | None = Field(None, description="Topic description")
    weight_percent: float | None = Field(None, ge=0, le=100, description="Exam weight percentage")


class CreateQuestionRequest(BaseModel):
    """Request to create a question."""

    exam_id: str = Field(..., description="ID of the exam")
    question_text: str = Field(..., description="The question text")
    question_type: Literal["single", "choose_n", "select_all"] = Field(
        ..., description="Type of question"
    )
    answers: list[AnswerOption] = Field(..., min_length=2, description="Answer options")
    topic_ids: list[str] | None = Field(None, description="Topic IDs to tag")
    choose_n: int | None = Field(None, ge=2, description="For choose_n: how many to select")
    explanation: str | None = Field(None, description="Explanation of the answer")
    difficulty: Literal["easy", "medium", "hard"] = Field("medium", description="Difficulty level")
    pattern_tags: list[str] | None = Field(None, description="Pattern tags")
    source: str | None = Field(None, description="Question source")


def validate_question_answers(
    question_type: str,
    answers: list[AnswerOption],
    choose_n: int | None,
) -> None:
    """Validate answer configuration for question type."""
    correct_count = sum(1 for a in answers if a.is_correct)

    if question_type == "single":
        if correct_count != 1:
            raise ValueError(
                f"Single choice questions must have exactly 1 correct answer, found {correct_count}"
            )
    elif question_type == "choose_n":
        if choose_n is None:
            raise ValueError("choose_n parameter is required for choose_n question type")
        if correct_count != choose_n:
            raise ValueError(
                f"Choose {choose_n} questions must have exactly {choose_n} correct answers, found {correct_count}"
            )
        if choose_n >= len(answers):
            raise ValueError(
                f"choose_n ({choose_n}) must be less than total answers ({len(answers)})"
            )
    elif question_type == "select_all":
        if correct_count < 1:
            raise ValueError("Select all questions must have at least 1 correct answer")
