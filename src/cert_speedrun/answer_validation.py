"""Answer bias validation module for detecting LLM-generated answer patterns."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BiasIssueType(Enum):
    """Types of bias issues that can be detected."""

    LENGTH_VARIANCE_HIGH = "length_variance_high"
    CORRECT_TOO_LONG = "correct_too_long"
    CORRECT_TOO_SHORT = "correct_too_short"
    ANSWER_TOO_SHORT = "answer_too_short"
    MISSING_DISTRACTOR_REASON = "missing_distractor_reason"
    DISTRACTOR_REASON_TOO_SHORT = "distractor_reason_too_short"


class IssueSeverity(Enum):
    """Severity level of bias issues."""

    WARNING = "warning"
    ERROR = "error"


@dataclass
class BiasThresholds:
    """Configurable thresholds for bias detection.

    Attributes:
        max_length_variance_percent: Maximum allowed variance from mean length (default 50%).
            All answers should be within this percentage of the mean length.
        min_correct_distractor_ratio: Minimum ratio of correct answer length to distractor average.
            Correct answers shouldn't be much shorter than distractors (default 0.7).
        max_correct_distractor_ratio: Maximum ratio of correct answer length to distractor average.
            Correct answers shouldn't be much longer than distractors (default 1.3).
        min_answer_length: Minimum characters per answer (default 10).
        require_distractor_reason: Whether distractor_reason is required for incorrect answers.
        min_distractor_reason_length: Minimum characters for distractor_reason if provided.
    """

    max_length_variance_percent: float = 50.0
    min_correct_distractor_ratio: float = 0.7
    max_correct_distractor_ratio: float = 1.3
    min_answer_length: int = 10
    require_distractor_reason: bool = False  # User requested this default to False
    min_distractor_reason_length: int = 20


@dataclass
class BiasIssue:
    """A detected bias issue in answer options."""

    issue_type: BiasIssueType
    severity: IssueSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LengthMetrics:
    """Statistics about answer lengths."""

    mean_length: float
    min_length: int
    max_length: int
    correct_avg_length: float
    distractor_avg_length: float
    correct_distractor_ratio: float
    length_variance_percent: float
    individual_lengths: list[dict[str, Any]]


@dataclass
class BiasAnalysisResult:
    """Result of bias analysis on a set of answers."""

    is_valid: bool
    issues: list[BiasIssue]
    warnings: list[BiasIssue]
    metrics: LengthMetrics | None
    quality_score: float  # 0-1, higher is better
    quality_grade: str  # A, B, C, D, F


def analyze_answer_lengths(
    answers: list[dict[str, Any]],
) -> LengthMetrics:
    """Analyze length statistics for a set of answers.

    Args:
        answers: List of answer dicts with 'text' and 'is_correct' fields.

    Returns:
        LengthMetrics with comprehensive length statistics.
    """
    lengths = [(a.get("text", ""), len(a.get("text", "")), a.get("is_correct", False)) for a in answers]

    all_lengths = [l[1] for l in lengths]
    correct_lengths = [l[1] for l in lengths if l[2]]
    distractor_lengths = [l[1] for l in lengths if not l[2]]

    mean_length = sum(all_lengths) / len(all_lengths) if all_lengths else 0
    correct_avg = sum(correct_lengths) / len(correct_lengths) if correct_lengths else 0
    distractor_avg = sum(distractor_lengths) / len(distractor_lengths) if distractor_lengths else 0

    # Calculate ratio of correct to distractor length
    if distractor_avg > 0:
        ratio = correct_avg / distractor_avg
    else:
        ratio = 1.0

    # Calculate variance as percentage of mean
    if mean_length > 0:
        max_deviation = max(abs(l - mean_length) for l in all_lengths)
        variance_percent = (max_deviation / mean_length) * 100
    else:
        variance_percent = 0

    individual = [
        {
            "text_preview": text[:50] + "..." if len(text) > 50 else text,
            "length": length,
            "is_correct": is_correct,
            "deviation_from_mean": length - mean_length,
            "deviation_percent": ((length - mean_length) / mean_length * 100) if mean_length > 0 else 0,
        }
        for text, length, is_correct in lengths
    ]

    return LengthMetrics(
        mean_length=mean_length,
        min_length=min(all_lengths) if all_lengths else 0,
        max_length=max(all_lengths) if all_lengths else 0,
        correct_avg_length=correct_avg,
        distractor_avg_length=distractor_avg,
        correct_distractor_ratio=ratio,
        length_variance_percent=variance_percent,
        individual_lengths=individual,
    )


def validate_answer_bias(
    answers: list[dict[str, Any]],
    thresholds: BiasThresholds | None = None,
) -> BiasAnalysisResult:
    """Validate answers for bias patterns.

    Args:
        answers: List of answer dicts with 'text', 'is_correct', and optionally 'distractor_reason'.
        thresholds: Optional custom thresholds. Uses defaults if not provided.

    Returns:
        BiasAnalysisResult with validation status, issues, warnings, and metrics.
    """
    if thresholds is None:
        thresholds = BiasThresholds()

    issues: list[BiasIssue] = []
    warnings: list[BiasIssue] = []

    # Analyze lengths
    metrics = analyze_answer_lengths(answers)

    # Check 1: Length variance
    if metrics.length_variance_percent > thresholds.max_length_variance_percent:
        issues.append(
            BiasIssue(
                issue_type=BiasIssueType.LENGTH_VARIANCE_HIGH,
                severity=IssueSeverity.ERROR,
                message=f"Answer lengths vary too much ({metrics.length_variance_percent:.1f}% from mean). "
                f"Target: within {thresholds.max_length_variance_percent}% of mean.",
                details={
                    "variance_percent": metrics.length_variance_percent,
                    "threshold": thresholds.max_length_variance_percent,
                    "mean_length": metrics.mean_length,
                    "min_length": metrics.min_length,
                    "max_length": metrics.max_length,
                },
            )
        )

    # Check 2: Correct answer too long
    if metrics.correct_distractor_ratio > thresholds.max_correct_distractor_ratio:
        issues.append(
            BiasIssue(
                issue_type=BiasIssueType.CORRECT_TOO_LONG,
                severity=IssueSeverity.ERROR,
                message=f"Correct answer(s) are {metrics.correct_distractor_ratio:.2f}x longer than distractors. "
                f"Target: ratio between {thresholds.min_correct_distractor_ratio} and {thresholds.max_correct_distractor_ratio}.",
                details={
                    "ratio": metrics.correct_distractor_ratio,
                    "correct_avg": metrics.correct_avg_length,
                    "distractor_avg": metrics.distractor_avg_length,
                    "max_ratio": thresholds.max_correct_distractor_ratio,
                },
            )
        )

    # Check 3: Correct answer too short
    if metrics.correct_distractor_ratio < thresholds.min_correct_distractor_ratio:
        warnings.append(
            BiasIssue(
                issue_type=BiasIssueType.CORRECT_TOO_SHORT,
                severity=IssueSeverity.WARNING,
                message=f"Correct answer(s) are {metrics.correct_distractor_ratio:.2f}x the length of distractors. "
                f"Consider expanding correct answers.",
                details={
                    "ratio": metrics.correct_distractor_ratio,
                    "correct_avg": metrics.correct_avg_length,
                    "distractor_avg": metrics.distractor_avg_length,
                    "min_ratio": thresholds.min_correct_distractor_ratio,
                },
            )
        )

    # Check 4: Individual answer too short
    for i, answer in enumerate(answers):
        text = answer.get("text", "")
        if len(text) < thresholds.min_answer_length:
            issues.append(
                BiasIssue(
                    issue_type=BiasIssueType.ANSWER_TOO_SHORT,
                    severity=IssueSeverity.ERROR,
                    message=f"Answer {i + 1} is too short ({len(text)} chars). Minimum: {thresholds.min_answer_length}.",
                    details={
                        "answer_index": i,
                        "length": len(text),
                        "min_length": thresholds.min_answer_length,
                        "text_preview": text[:30],
                    },
                )
            )

    # Check 5: Distractor reasons
    for i, answer in enumerate(answers):
        if answer.get("is_correct", False):
            continue  # Skip correct answers

        distractor_reason = answer.get("distractor_reason")

        if thresholds.require_distractor_reason and not distractor_reason:
            issues.append(
                BiasIssue(
                    issue_type=BiasIssueType.MISSING_DISTRACTOR_REASON,
                    severity=IssueSeverity.ERROR,
                    message=f"Answer {i + 1} (distractor) is missing 'distractor_reason'. "
                    "Explain why this wrong answer is tempting.",
                    details={"answer_index": i},
                )
            )
        elif distractor_reason and len(distractor_reason) < thresholds.min_distractor_reason_length:
            warnings.append(
                BiasIssue(
                    issue_type=BiasIssueType.DISTRACTOR_REASON_TOO_SHORT,
                    severity=IssueSeverity.WARNING,
                    message=f"Answer {i + 1} distractor_reason is too brief ({len(distractor_reason)} chars). "
                    f"Consider expanding to at least {thresholds.min_distractor_reason_length} chars.",
                    details={
                        "answer_index": i,
                        "length": len(distractor_reason),
                        "min_length": thresholds.min_distractor_reason_length,
                    },
                )
            )

    # Calculate quality score (0-1)
    quality_score = calculate_quality_score(metrics, issues, warnings, thresholds)
    quality_grade = score_to_grade(quality_score)

    return BiasAnalysisResult(
        is_valid=len(issues) == 0,
        issues=issues,
        warnings=warnings,
        metrics=metrics,
        quality_score=quality_score,
        quality_grade=quality_grade,
    )


def calculate_quality_score(
    metrics: LengthMetrics,
    issues: list[BiasIssue],
    warnings: list[BiasIssue],
    thresholds: BiasThresholds,
) -> float:
    """Calculate a quality score from 0-1 based on bias metrics.

    Scoring factors:
    - Length variance: 30% weight
    - Correct/distractor ratio: 40% weight
    - Issues penalty: -0.15 per issue
    - Warnings penalty: -0.05 per warning
    """
    score = 1.0

    # Length variance component (30% weight)
    if thresholds.max_length_variance_percent > 0:
        variance_score = max(0, 1 - (metrics.length_variance_percent / thresholds.max_length_variance_percent))
        score -= 0.30 * (1 - variance_score)

    # Ratio component (40% weight)
    ideal_ratio = 1.0
    ratio_deviation = abs(metrics.correct_distractor_ratio - ideal_ratio)
    max_deviation = max(
        ideal_ratio - thresholds.min_correct_distractor_ratio,
        thresholds.max_correct_distractor_ratio - ideal_ratio,
    )
    if max_deviation > 0:
        ratio_score = max(0, 1 - (ratio_deviation / max_deviation))
        score -= 0.40 * (1 - ratio_score)

    # Issue penalties
    score -= len(issues) * 0.15
    score -= len(warnings) * 0.05

    return max(0.0, min(1.0, score))


def score_to_grade(score: float) -> str:
    """Convert a 0-1 quality score to a letter grade."""
    if score >= 0.9:
        return "A"
    elif score >= 0.8:
        return "B"
    elif score >= 0.7:
        return "C"
    elif score >= 0.6:
        return "D"
    else:
        return "F"


def format_bias_error_message(result: BiasAnalysisResult) -> str:
    """Format a BiasAnalysisResult into a human-readable error message.

    Args:
        result: The bias analysis result to format.

    Returns:
        A formatted string suitable for returning in tool errors.
    """
    lines = ["Answer bias validation failed:", ""]

    for i, issue in enumerate(result.issues, 1):
        lines.append(f"{i}. {issue.message}")
        lines.append("")

    if result.warnings:
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning.message}")
        lines.append("")

    if result.metrics:
        lines.append("Current metrics:")
        lines.append(f"  - Mean answer length: {result.metrics.mean_length:.0f} chars")
        lines.append(f"  - Correct avg: {result.metrics.correct_avg_length:.0f} chars")
        lines.append(f"  - Distractor avg: {result.metrics.distractor_avg_length:.0f} chars")
        lines.append(f"  - Correct/Distractor ratio: {result.metrics.correct_distractor_ratio:.2f}x")
        lines.append("")

    lines.append("Rewrite answers to address these issues before retrying.")

    return "\n".join(lines)


def get_answer_length_guidelines(
    question_type: str,
    num_answers: int = 4,
    target_length: int | None = None,
) -> dict[str, Any]:
    """Get guidelines for answer lengths to prevent bias.

    Args:
        question_type: Type of question (single, choose_n, select_all).
        num_answers: Number of answer options.
        target_length: Optional target length in characters.

    Returns:
        Dict with guidelines including target_length, constraints, and anti-patterns.
    """
    # Default target length based on typical certification exam answers
    if target_length is None:
        target_length = 80  # Characters

    thresholds = BiasThresholds()

    min_length = int(target_length * (1 - thresholds.max_length_variance_percent / 100))
    max_length = int(target_length * (1 + thresholds.max_length_variance_percent / 100))

    return {
        "target_length": target_length,
        "min_length": max(thresholds.min_answer_length, min_length),
        "max_length": max_length,
        "constraints": {
            "all_answers_similar_length": f"Keep all {num_answers} answers within {thresholds.max_length_variance_percent}% of each other in length.",
            "correct_not_longer": "Correct answer(s) should NOT be noticeably longer than incorrect ones.",
            "distractors_plausible": "Each distractor must be a plausible answer that someone could reasonably choose.",
        },
        "anti_patterns": [
            "Making correct answers more detailed or comprehensive than distractors",
            "Using vague, obviously-wrong distractors like 'None of the above' or 'All of the above'",
            "Starting correct answers with more specific technical terms",
            "Including hedging language only in incorrect answers",
            "Making only the correct answer grammatically complete",
        ],
        "tips": [
            "Write all answers first, then check lengths match",
            "Add context/detail to short distractors",
            "Trim overly-detailed correct answers",
            "Each distractor should represent a common misconception",
        ],
    }
