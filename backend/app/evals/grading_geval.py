"""G-Eval metric factories for Masaar grading outputs."""

from __future__ import annotations

from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

from app.evals.litellm_judge import MasaarLiteLLMJudge, get_masaar_eval_judge


def build_rubric_fairness_metric(
    *,
    judge: MasaarLiteLLMJudge | None = None,
    threshold: float = 0.7,
) -> GEval:
    """Judge whether a rubric fairly reflects transcript quality for the question."""
    return GEval(
        name="RubricFairness",
        criteria=(
            "The actual output is a JSON rubric grading a voice interview answer. "
            "Determine whether the scores and feedback fairly reflect the candidate "
            "transcript quality for the interview question in the input. "
            "Strong substantive answers should not receive very low overall scores; "
            "empty or vague answers should not receive very high overall scores."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        threshold=threshold,
        model=judge or get_masaar_eval_judge(),
    )


def build_rubric_coherence_metric(
    *,
    judge: MasaarLiteLLMJudge | None = None,
    threshold: float = 0.7,
) -> GEval:
    """Judge whether rubric JSON is well-formed and internally consistent."""
    return GEval(
        name="RubricCoherence",
        criteria=(
            "The actual output must be valid grading JSON with dimension scores in "
            "[0.0, 1.0], concise feedback per dimension, and an overall score that "
            "is consistent with the dimension scores. Penalize missing dimensions, "
            "non-numeric scores, or contradictory feedback."
        ),
        evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
        threshold=threshold,
        model=judge or get_masaar_eval_judge(),
    )


def voice_grading_input(golden_question: str, golden_transcript: str, difficulty: str) -> str:
    """Format a voice grading scenario for G-Eval input."""
    return (
        f"Question: {golden_question}\n"
        f"Difficulty: {difficulty}\n"
        f"Transcript: {golden_transcript}"
    )


__all__ = [
    "build_rubric_coherence_metric",
    "build_rubric_fairness_metric",
    "voice_grading_input",
]
