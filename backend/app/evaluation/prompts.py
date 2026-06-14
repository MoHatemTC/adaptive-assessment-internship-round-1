"""Prompt templates for the LLM evaluator."""

from app.evaluation.schemas import AIEvaluationSettings, CodeEvaluationContext


def build_evaluator_system_prompt(settings: AIEvaluationSettings) -> str:
    strictness_guide = {
        "lenient": "Be encouraging; focus on growth opportunities.",
        "balanced": "Be fair and constructive.",
        "strict": "Apply rigorous professional standards.",
    }.get(settings.strictness, "Be fair and constructive.")

    verbosity_guide = {
        "brief": "Keep strengths, weaknesses, and recommendations to one short item each.",
        "detailed": "Provide 2–3 specific, actionable items per list.",
    }.get(settings.feedback_verbosity, "Provide 2–3 specific items per list.")

    safeguards = (
        "Base scores ONLY on the submission and test results provided. "
        "Do not invent requirements or test outcomes."
        if settings.hallucination_safeguards
        else ""
    )

    criteria = ", ".join(settings.allowed_criteria)

    return f"""You are the LLM Evaluator for an adaptive challenge platform.
{strictness_guide}
{verbosity_guide}
{safeguards}

Score these dimensions (each 0.0–1.0): {criteria}
- correctness and performance are pre-computed; echo them exactly in dimension_scores.
- score completeness, code_quality, creativity, and documentation yourself.

Return ONLY valid JSON:
{{
  "dimension_scores": {{
    "correctness": <float>,
    "completeness": <float>,
    "code_quality": <float>,
    "performance": <float>,
    "creativity": <float>,
    "documentation": <float>
  }},
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommendations": ["..."],
  "next_difficulty": "easier|same|harder|Intermediate|Advanced",
  "feedback_summary": "<one paragraph>"
}}"""


def build_evaluator_user_prompt(ctx: CodeEvaluationContext) -> str:
    return (
        f"Challenge ID: {ctx.challenge_id}\n"
        f"Title: {ctx.title}\n"
        f"Description: {ctx.description}\n"
        f"Language: {ctx.language}\n"
        f"Tests passed: {ctx.passed_tests}/{ctx.total_tests}\n"
        f"Pre-computed correctness ratio: {ctx.correctness_ratio:.3f}\n"
        f"Pre-computed performance ratio: {ctx.performance_ratio:.3f}\n"
        f"Execution error: {ctx.execution_error or 'none'}\n\n"
        f"Submission:\n```{ctx.language}\n{ctx.submitted_code}\n```"
    )
