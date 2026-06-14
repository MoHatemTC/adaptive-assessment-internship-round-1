"""LLM Evaluator — scores submissions using admin config and kernel LiteLLM."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.structured_llm import extract_llm_text, get_structured_llm_with_tracing
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.evaluation.defaults import DEFAULT_EVALUATION_CONFIG
from app.evaluation.prompts import build_evaluator_system_prompt, build_evaluator_user_prompt
from app.evaluation.schemas import (
    CodeEvaluationContext,
    DimensionScores,
    EvaluationResult,
    PlatformEvaluationConfig,
    ScoreBreakdown,
)

_logger = get_logger(__name__)
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_response(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def _points_for_dimension(
    normalized: float,
    weight: float,
    max_score: int,
) -> int:
    return round(normalized * weight * max_score)


def _build_breakdown(
    dims: DimensionScores,
    config: PlatformEvaluationConfig,
) -> ScoreBreakdown:
    w = config.scoring.weights
    max_score = config.scoring.max_score
    return ScoreBreakdown(
        correctness=_points_for_dimension(dims.correctness, w.correctness, max_score),
        completeness=_points_for_dimension(dims.completeness, w.completeness, max_score),
        code_quality=_points_for_dimension(dims.code_quality, w.code_quality, max_score),
        performance=_points_for_dimension(dims.performance, w.performance, max_score),
        creativity=_points_for_dimension(dims.creativity, w.creativity, max_score),
        documentation=_points_for_dimension(dims.documentation, w.documentation, max_score),
    )


def _total_score(breakdown: ScoreBreakdown) -> int:
    return (
        breakdown.correctness
        + breakdown.completeness
        + breakdown.code_quality
        + breakdown.performance
        + breakdown.creativity
        + breakdown.documentation
    )


def _deterministic_fallback(
    ctx: CodeEvaluationContext,
    config: PlatformEvaluationConfig,
) -> EvaluationResult:
    """Build an evaluation without LLM when the provider is unavailable."""
    completeness = ctx.correctness_ratio * 0.9 if ctx.total_tests else 0.0
    dims = DimensionScores(
        correctness=ctx.correctness_ratio,
        completeness=completeness,
        code_quality=ctx.correctness_ratio * 0.85,
        performance=ctx.performance_ratio,
        creativity=0.5,
        documentation=0.4,
    )
    breakdown = _build_breakdown(dims, config)
    score = _total_score(breakdown)
    passed = score >= config.scoring.passing_threshold
    return EvaluationResult(
        challenge_id=ctx.challenge_id,
        score=score,
        status="Passed" if passed else "Failed",
        breakdown=breakdown,
        strengths=["Automated tests executed successfully."] if ctx.passed_tests else [],
        weaknesses=(
            [f"Only {ctx.passed_tests}/{ctx.total_tests} tests passed."]
            if ctx.passed_tests < ctx.total_tests
            else []
        ),
        recommendations=["Review failing test cases and edge cases."],
        next_difficulty="same",
        dimension_scores=dims,
        feedback_summary="Deterministic evaluation (LLM unavailable).",
    )


async def evaluate_code_submission(
    ctx: CodeEvaluationContext,
    *,
    config: PlatformEvaluationConfig | None = None,
) -> EvaluationResult:
    """Evaluate a code submission using admin scoring rules and LiteLLM.

    Correctness and performance ratios should come from E2B execution.
    The LLM scores subjective dimensions and produces actionable feedback.
    Falls back to deterministic scoring when the LLM is unavailable.
    """
    eval_config = config or DEFAULT_EVALUATION_CONFIG
    settings = get_settings()

    if not settings.LITELLM_API_KEY.get_secret_value():
        return _deterministic_fallback(ctx, eval_config)

    llm, callbacks = get_structured_llm_with_tracing()
    model = settings.LITELLM_MODEL
    start = time.perf_counter()

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=build_evaluator_system_prompt(eval_config.ai_evaluation)),
                HumanMessage(content=build_evaluator_user_prompt(ctx)),
            ],
            config={"callbacks": callbacks},
        )
        record_llm_call(model, "llm_evaluator", "success", time.perf_counter() - start)
    except Exception as exc:  # noqa: BLE001
        record_llm_call(model, "llm_evaluator", "error", time.perf_counter() - start)
        _logger.warning("llm_evaluator_failed", error=str(exc))
        return _deterministic_fallback(ctx, eval_config)

    raw = extract_llm_text(response.content)
    parsed = _parse_json_response(raw)
    if not parsed or "dimension_scores" not in parsed:
        _logger.warning("llm_evaluator_unparseable", raw=raw[:200])
        return _deterministic_fallback(ctx, eval_config)

    try:
        llm_dims = DimensionScores.model_validate(parsed["dimension_scores"])
    except Exception:  # noqa: BLE001
        return _deterministic_fallback(ctx, eval_config)

    dims = DimensionScores(
        correctness=ctx.correctness_ratio,
        completeness=llm_dims.completeness,
        code_quality=llm_dims.code_quality,
        performance=ctx.performance_ratio,
        creativity=llm_dims.creativity,
        documentation=llm_dims.documentation,
    )
    breakdown = _build_breakdown(dims, eval_config)
    score = _total_score(breakdown)
    passed = score >= eval_config.scoring.passing_threshold

    return EvaluationResult(
        challenge_id=ctx.challenge_id,
        score=score,
        status="Passed" if passed else "Failed",
        breakdown=breakdown,
        strengths=[str(s) for s in parsed.get("strengths", [])[:5]],
        weaknesses=[str(s) for s in parsed.get("weaknesses", [])[:5]],
        recommendations=[str(s) for s in parsed.get("recommendations", [])[:5]],
        next_difficulty=str(parsed.get("next_difficulty", "same")),
        dimension_scores=dims,
        feedback_summary=str(parsed.get("feedback_summary", "")),
    )


def evaluation_to_rubric_scores(result: EvaluationResult) -> list[dict[str, Any]]:
    """Map evaluation dimension scores to API rubric entries."""
    dims = result.dimension_scores
    feedback_by_dim = {
        "correctness": result.weaknesses[0] if result.weaknesses else "",
        "code_quality": result.feedback_summary[:120] if result.feedback_summary else "",
    }
    entries: list[dict[str, Any]] = []
    for dimension, value in dims.model_dump().items():
        entries.append(
            {
                "dimension": dimension,
                "score": round(float(value), 3),
                "feedback": feedback_by_dim.get(dimension) or f"{dimension}: {value:.0%}",
            }
        )
    return entries
