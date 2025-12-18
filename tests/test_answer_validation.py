"""Tests for answer bias validation module."""

import pytest

from cert_speedrun.answer_validation import (
    BiasThresholds,
    BiasIssueType,
    IssueSeverity,
    analyze_answer_lengths,
    validate_answer_bias,
    format_bias_error_message,
    get_answer_length_guidelines,
    calculate_quality_score,
    score_to_grade,
)


class TestAnalyzeAnswerLengths:
    """Tests for analyze_answer_lengths function."""

    def test_basic_length_calculation(self):
        """Test basic length statistics calculation."""
        answers = [
            {"text": "Short answer", "is_correct": True},
            {"text": "Another short one", "is_correct": False},
            {"text": "Medium length answer here", "is_correct": False},
            {"text": "A bit longer answer text", "is_correct": False},
        ]

        metrics = analyze_answer_lengths(answers)

        assert metrics.mean_length > 0
        assert metrics.min_length <= metrics.max_length
        assert metrics.correct_avg_length > 0
        assert metrics.distractor_avg_length > 0
        assert len(metrics.individual_lengths) == 4

    def test_correct_distractor_ratio(self):
        """Test correct to distractor length ratio."""
        # Correct answer is longer
        answers = [
            {"text": "This is a much longer correct answer with lots of detail", "is_correct": True},
            {"text": "Short wrong", "is_correct": False},
            {"text": "Also short", "is_correct": False},
            {"text": "Brief one", "is_correct": False},
        ]

        metrics = analyze_answer_lengths(answers)

        assert metrics.correct_distractor_ratio > 1.0
        assert metrics.correct_avg_length > metrics.distractor_avg_length

    def test_balanced_lengths(self):
        """Test with balanced answer lengths."""
        answers = [
            {"text": "Answer option A here", "is_correct": True},
            {"text": "Answer option B here", "is_correct": False},
            {"text": "Answer option C here", "is_correct": False},
            {"text": "Answer option D here", "is_correct": False},
        ]

        metrics = analyze_answer_lengths(answers)

        # All same length, ratio should be 1.0
        assert abs(metrics.correct_distractor_ratio - 1.0) < 0.01
        assert metrics.length_variance_percent < 10

    def test_empty_answers(self):
        """Test with empty answer list."""
        metrics = analyze_answer_lengths([])

        assert metrics.mean_length == 0
        assert metrics.correct_distractor_ratio == 1.0


class TestValidateAnswerBias:
    """Tests for validate_answer_bias function."""

    def test_valid_balanced_answers(self):
        """Test that balanced answers pass validation."""
        answers = [
            {"text": "Use Amazon S3 for object storage", "is_correct": True},
            {"text": "Use Amazon EBS for block storage", "is_correct": False, "distractor_reason": "EBS is for EC2 volumes"},
            {"text": "Use Amazon EFS for file storage", "is_correct": False, "distractor_reason": "EFS is for shared files"},
            {"text": "Use Amazon FSx for Windows files", "is_correct": False, "distractor_reason": "FSx is for Windows"},
        ]

        result = validate_answer_bias(answers)

        assert result.is_valid
        assert result.quality_grade in ("A", "B")
        assert len(result.issues) == 0

    def test_correct_answer_too_long(self):
        """Test detection of correct answer being too long."""
        answers = [
            {
                "text": "This is a very long and detailed correct answer that provides extensive information and context about the topic at hand, explaining multiple aspects and considerations",
                "is_correct": True,
            },
            {"text": "Short A", "is_correct": False},
            {"text": "Short B", "is_correct": False},
            {"text": "Short C", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        assert not result.is_valid
        assert any(i.issue_type == BiasIssueType.CORRECT_TOO_LONG for i in result.issues)

    def test_high_length_variance(self):
        """Test detection of high length variance."""
        answers = [
            {"text": "A", "is_correct": False},
            {"text": "This is a very long answer that has much more detail", "is_correct": True},
            {"text": "B", "is_correct": False},
            {"text": "C", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        assert not result.is_valid
        assert any(i.issue_type == BiasIssueType.LENGTH_VARIANCE_HIGH for i in result.issues)

    def test_answer_too_short(self):
        """Test detection of answers that are too short."""
        answers = [
            {"text": "Good answer here", "is_correct": True},
            {"text": "OK", "is_correct": False},  # Too short
            {"text": "Also good here", "is_correct": False},
            {"text": "Another option", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        assert not result.is_valid
        assert any(i.issue_type == BiasIssueType.ANSWER_TOO_SHORT for i in result.issues)

    def test_missing_distractor_reason_when_required(self):
        """Test that missing distractor reason is flagged when required."""
        answers = [
            {"text": "Correct answer here", "is_correct": True},
            {"text": "Wrong answer A here", "is_correct": False},  # Missing reason
            {"text": "Wrong answer B here", "is_correct": False},
            {"text": "Wrong answer C here", "is_correct": False},
        ]

        thresholds = BiasThresholds(require_distractor_reason=True)
        result = validate_answer_bias(answers, thresholds)

        assert not result.is_valid
        assert any(i.issue_type == BiasIssueType.MISSING_DISTRACTOR_REASON for i in result.issues)

    def test_distractor_reason_not_required_by_default(self):
        """Test that distractor reason is not required by default."""
        answers = [
            {"text": "Correct answer here", "is_correct": True},
            {"text": "Wrong answer A here", "is_correct": False},
            {"text": "Wrong answer B here", "is_correct": False},
            {"text": "Wrong answer C here", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        # Should not fail due to missing distractor reasons
        missing_reason_issues = [
            i for i in result.issues if i.issue_type == BiasIssueType.MISSING_DISTRACTOR_REASON
        ]
        assert len(missing_reason_issues) == 0

    def test_short_distractor_reason_warning(self):
        """Test warning for short distractor reasons."""
        answers = [
            {"text": "Correct answer here", "is_correct": True},
            {"text": "Wrong answer A here", "is_correct": False, "distractor_reason": "Bad"},  # Too short
            {"text": "Wrong answer B here", "is_correct": False, "distractor_reason": "Also bad"},
            {"text": "Wrong answer C here", "is_correct": False, "distractor_reason": "Short"},
        ]

        result = validate_answer_bias(answers)

        assert any(w.issue_type == BiasIssueType.DISTRACTOR_REASON_TOO_SHORT for w in result.warnings)

    def test_custom_thresholds(self):
        """Test with custom thresholds."""
        answers = [
            {"text": "Correct A", "is_correct": True},
            {"text": "Wrong B longer", "is_correct": False},
            {"text": "Wrong C longer", "is_correct": False},
            {"text": "Wrong D longer", "is_correct": False},
        ]

        # Relaxed thresholds
        thresholds = BiasThresholds(
            max_length_variance_percent=100,
            min_correct_distractor_ratio=0.5,
            max_correct_distractor_ratio=2.0,
            min_answer_length=5,
        )

        result = validate_answer_bias(answers, thresholds)

        # Should pass with relaxed thresholds
        assert result.is_valid


class TestQualityScoring:
    """Tests for quality score calculation."""

    def test_perfect_score(self):
        """Test that perfect answers get high score."""
        answers = [
            {"text": "Answer option A here", "is_correct": True},
            {"text": "Answer option B here", "is_correct": False},
            {"text": "Answer option C here", "is_correct": False},
            {"text": "Answer option D here", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        assert result.quality_score >= 0.9
        assert result.quality_grade == "A"

    def test_score_degrades_with_issues(self):
        """Test that issues reduce the score."""
        answers = [
            {
                "text": "This is a very long correct answer with extensive detail",
                "is_correct": True,
            },
            {"text": "Short", "is_correct": False},
            {"text": "Short", "is_correct": False},
            {"text": "Short", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        assert result.quality_score < 0.7
        assert result.quality_grade in ("D", "F")

    def test_score_to_grade_boundaries(self):
        """Test grade boundary conversions."""
        assert score_to_grade(0.95) == "A"
        assert score_to_grade(0.90) == "A"
        assert score_to_grade(0.85) == "B"
        assert score_to_grade(0.80) == "B"
        assert score_to_grade(0.75) == "C"
        assert score_to_grade(0.70) == "C"
        assert score_to_grade(0.65) == "D"
        assert score_to_grade(0.60) == "D"
        assert score_to_grade(0.55) == "F"
        assert score_to_grade(0.0) == "F"


class TestFormatBiasErrorMessage:
    """Tests for error message formatting."""

    def test_format_includes_issues(self):
        """Test that formatted message includes issues."""
        answers = [
            {
                "text": "Very long correct answer with lots and lots of details",
                "is_correct": True,
            },
            {"text": "A", "is_correct": False},
            {"text": "B", "is_correct": False},
            {"text": "C", "is_correct": False},
        ]

        result = validate_answer_bias(answers)
        message = format_bias_error_message(result)

        assert "validation failed" in message.lower()
        assert "Rewrite answers" in message

    def test_format_includes_metrics(self):
        """Test that formatted message includes metrics."""
        answers = [
            {"text": "Correct answer text here", "is_correct": True},
            {"text": "A", "is_correct": False},
            {"text": "B", "is_correct": False},
            {"text": "C", "is_correct": False},
        ]

        result = validate_answer_bias(answers)
        message = format_bias_error_message(result)

        assert "Mean answer length" in message or "mean" in message.lower()


class TestGetAnswerLengthGuidelines:
    """Tests for get_answer_length_guidelines function."""

    def test_returns_guidelines(self):
        """Test that guidelines are returned."""
        guidelines = get_answer_length_guidelines("single", num_answers=4)

        assert "target_length" in guidelines
        assert "min_length" in guidelines
        assert "max_length" in guidelines
        assert "constraints" in guidelines
        assert "anti_patterns" in guidelines
        assert "tips" in guidelines

    def test_custom_target_length(self):
        """Test with custom target length."""
        guidelines = get_answer_length_guidelines("single", target_length=100)

        assert guidelines["target_length"] == 100
        assert guidelines["min_length"] < 100
        assert guidelines["max_length"] > 100

    def test_anti_patterns_included(self):
        """Test that anti-patterns are included."""
        guidelines = get_answer_length_guidelines("single")

        assert len(guidelines["anti_patterns"]) > 0
        # Check for common bias patterns
        patterns_text = " ".join(guidelines["anti_patterns"]).lower()
        assert "longer" in patterns_text or "detailed" in patterns_text


class TestMultipleCorrectAnswers:
    """Tests for questions with multiple correct answers."""

    def test_choose_n_balanced(self):
        """Test choose_n questions with balanced answers."""
        answers = [
            {"text": "Correct answer option A", "is_correct": True},
            {"text": "Correct answer option B", "is_correct": True},
            {"text": "Incorrect answer opt C", "is_correct": False},
            {"text": "Incorrect answer opt D", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        assert result.is_valid
        assert result.metrics.correct_avg_length > 0
        assert result.metrics.distractor_avg_length > 0

    def test_select_all_with_bias(self):
        """Test select_all questions with length bias."""
        answers = [
            {"text": "This is a very long and detailed correct answer A", "is_correct": True},
            {"text": "This is a very long and detailed correct answer B", "is_correct": True},
            {"text": "Short C", "is_correct": False},
            {"text": "Short D", "is_correct": False},
        ]

        result = validate_answer_bias(answers)

        # Should detect bias
        assert not result.is_valid or len(result.warnings) > 0
