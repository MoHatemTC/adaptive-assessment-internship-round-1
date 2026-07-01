"""Golden cases for G-Eval grading quality checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceGradingGolden:
    """Reference case for voice rubric G-Eval."""

    question: str
    transcript: str
    difficulty: str
    rubric_json: str
    quality_band: str  # e.g. "strong", "weak"


VOICE_GRADING_GOLDENS: tuple[VoiceGradingGolden, ...] = (
    VoiceGradingGolden(
        question="Explain how you would design a REST API for a payment system.",
        transcript=(
            "I would use resource-oriented endpoints with idempotent POST for "
            "payments, JWT auth, rate limiting, and audit logs for compliance."
        ),
        difficulty="intermediate",
        rubric_json=(
            '{"dimensions": ['
            '{"name": "thinking", "score": 0.82, "feedback": "Clear API design."}, '
            '{"name": "soft", "score": 0.75, "feedback": "Well structured answer."}, '
            '{"name": "work", "score": 0.78, "feedback": "Mentions compliance."}, '
            '{"name": "growth", "score": 0.7, "feedback": "Shows security awareness."}'
            '], "overall": 0.76}'
        ),
        quality_band="strong",
    ),
    VoiceGradingGolden(
        question="Describe a technical challenge you faced and how you solved it.",
        transcript="Um, I don't know. Maybe something with bugs.",
        difficulty="intermediate",
        rubric_json=(
            '{"dimensions": ['
            '{"name": "thinking", "score": 0.1, "feedback": "No concrete example."}, '
            '{"name": "soft", "score": 0.2, "feedback": "Very vague."}, '
            '{"name": "work", "score": 0.1, "feedback": "No evidence of problem solving."}, '
            '{"name": "growth", "score": 0.15, "feedback": "No learning signal."}'
            '], "overall": 0.14}'
        ),
        quality_band="weak",
    ),
)


__all__ = ["VoiceGradingGolden", "VOICE_GRADING_GOLDENS"]
