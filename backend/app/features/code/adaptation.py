"""Layer 4 — Adaptation.

Reads the session's ``skill_dimension_scores`` (and the ``assessment_sessions``
blueprint) and produces an :class:`AdaptiveContract` describing the *next*
question for the Generator Agent. This layer performs **no** database write —
the contract is a transient output passed straight to the generator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.core.logging import get_logger
from app.sessions.models import AssessmentSession, SkillDimensionScore
from app.shared.schemas.memory import (
    AdaptiveContract,
    DifficultyLevel,
    DimensionName,
    DimensionScore,
)

_logger = get_logger(__name__)

TOOL_TYPE = "coding"

_ENGAGED_DIMENSIONS: tuple[DimensionName, ...] = ("thinking", "work", "digital_ai")


@dataclass(frozen=True)
class AdaptivePolicy:
    """Learner/profile and admin-configured coding adaptation policy."""

    max_questions: int | None
    intermediate_at: int | None
    advanced_at: int | None
    initial_difficulty: DifficultyLevel = "beginner"


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _section(data: dict[str, Any], *names: str) -> dict[str, Any]:
    for name in names:
        value = data.get(name)
        if isinstance(value, dict):
            return value
    return {}


def _optional_int_setting(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _difficulty_setting(value: object, default: DifficultyLevel) -> DifficultyLevel:
    if value in {"beginner", "intermediate", "advanced"}:
        return value  # type: ignore[return-value]
    return default


def _profile_initial_difficulty(profile: dict[str, Any]) -> DifficultyLevel:
    level = str(
        profile.get("level")
        or profile.get("experience_level")
        or profile.get("seniority")
        or ""
    ).lower()
    if any(marker in level for marker in ("senior", "advanced", "expert")):
        return "advanced"
    if any(marker in level for marker in ("mid", "intermediate", "regular")):
        return "intermediate"
    return "beginner"


def _policy_from_config(
    *,
    assessment: Assessment | None,
    session: AssessmentSession | None,
) -> AdaptivePolicy:
    blueprint = _parse_json_object(assessment.blueprint_json if assessment else None)
    tool_config = _parse_json_object(assessment.tool_config if assessment else None)
    learner_profile = _parse_json_object(
        session.learner_profile_json if session else None
    )

    coding_blueprint = _section(blueprint, "coding", "code")
    adaptive_blueprint = _section(blueprint, "adaptive", "adaptation")
    coding_tool_config = _section(tool_config, "coding", "code")
    thresholds = (
        _section(coding_blueprint, "difficulty_thresholds", "thresholds")
        or _section(adaptive_blueprint, "difficulty_thresholds", "thresholds")
        or _section(coding_tool_config, "difficulty_thresholds", "thresholds")
    )

    default_initial = _profile_initial_difficulty(learner_profile)
    initial = (
        coding_blueprint.get("initial_difficulty")
        or adaptive_blueprint.get("initial_difficulty")
        or coding_tool_config.get("initial_difficulty")
    )

    max_questions = (
        _optional_int_setting(coding_blueprint, "max_questions")
        or _optional_int_setting(adaptive_blueprint, "max_questions")
        or _optional_int_setting(coding_tool_config, "max_questions")
    )
    intermediate_at = _optional_int_setting(thresholds, "intermediate")
    advanced_at = _optional_int_setting(thresholds, "advanced")
    if intermediate_at is not None:
        intermediate_at = max(1, min(10, intermediate_at))
    if advanced_at is not None:
        advanced_at = max(1, min(10, advanced_at))
    if intermediate_at is not None and advanced_at is not None:
        advanced_at = max(intermediate_at, advanced_at)

    return AdaptivePolicy(
        max_questions=max(1, max_questions) if max_questions is not None else None,
        intermediate_at=intermediate_at,
        advanced_at=advanced_at,
        initial_difficulty=_difficulty_setting(initial, default_initial),
    )


def _mean_int(values: list[int]) -> int | None:
    """Return the rounded integer mean of ``values``, or ``None`` if empty."""
    if not values:
        return None
    return max(1, min(10, round(sum(values) / len(values))))


def _difficulty_for(avg: int | None, policy: AdaptivePolicy) -> DifficultyLevel:
    """Map an average engaged score to the next question's configured tier."""
    if avg is None:
        return policy.initial_difficulty
    if policy.advanced_at is not None and avg >= policy.advanced_at:
        return "advanced"
    if policy.intermediate_at is not None and avg >= policy.intermediate_at:
        return "intermediate"
    return policy.initial_difficulty


async def compute_adaptive_contract(
    db: AsyncSession,
    session_id: str,
    assessment_id: str,
) -> AdaptiveContract:
    """Compute the adaptive contract for the next question.

    Aggregates all ``skill_dimension_scores`` rows for the session into
    cumulative dimension scores, picks the next difficulty from the engaged
    average, targets the weakest engaged dimension, and decides whether to
    stop. No row is written.

    Args:
        db: Active async database session.
        session_id: Platform assessment session UUID.
        assessment_id: Parent assessment identifier (passed through to context).

    Returns:
        A transient :class:`AdaptiveContract` for the Generator Agent.
    """
    rows = (
        await db.exec(
            select(SkillDimensionScore)
            .where(SkillDimensionScore.session_id == session_id)
            .order_by(SkillDimensionScore.question_index)
        )
    ).all()

    session = await db.get(AssessmentSession, session_id)
    assessment = await db.get(Assessment, assessment_id)
    policy = _policy_from_config(assessment=assessment, session=session)
    session_completed = session is not None and session.status in {
        "completed",
        "expired",
    }

    per_dim: dict[DimensionName, list[int]] = {dim: [] for dim in _ENGAGED_DIMENSIONS}
    for row in rows:
        for dim in _ENGAGED_DIMENSIONS:
            value = getattr(row, dim)
            if value is not None:
                per_dim[dim].append(int(value))

    cumulative = DimensionScore(
        thinking=_mean_int(per_dim["thinking"]),
        work=_mean_int(per_dim["work"]),
        digital_ai=_mean_int(per_dim["digital_ai"]),
        soft=None,
        growth=None,
    )

    engaged_means = {
        dim: _mean_int(per_dim[dim])
        for dim in _ENGAGED_DIMENSIONS
        if _mean_int(per_dim[dim]) is not None
    }
    avg_engaged = _mean_int([m for m in engaged_means.values() if m is not None])

    focus_dimension: DimensionName | None = None
    if engaged_means:
        focus_dimension = min(engaged_means, key=lambda d: engaged_means[d])  # type: ignore[arg-type]

    answered = len({row.question_index for row in rows})
    next_index = (max((row.question_index for row in rows), default=-1)) + 1
    stop = session_completed or (
        policy.max_questions is not None and answered >= policy.max_questions
    )

    if stop:
        memory_summary = (
            f"Coding loop complete after {answered} question(s); "
            f"engaged average {avg_engaged or 'n/a'}/10."
        )
    elif avg_engaged is None:
        memory_summary = "No coding evidence yet; starting at beginner difficulty."
    else:
        memory_summary = (
            f"After {answered} question(s) the learner averages {avg_engaged}/10 on "
            f"engaged dimensions; next focus on '{focus_dimension}'."
        )

    contract = AdaptiveContract(
        session_id=session_id,
        question_index=next_index,
        tool_type=TOOL_TYPE,
        difficulty=_difficulty_for(avg_engaged, policy),
        focus_dimension=focus_dimension,
        stop=stop,
        memory_summary=memory_summary,
        cumulative_scores=cumulative,
    )

    _logger.info(
        "code_adaptive_contract_computed",
        session_id=session_id,
        assessment_id=assessment_id,
        next_index=next_index,
        difficulty=contract.difficulty,
        stop=stop,
        focus=focus_dimension,
    )
    return contract


__all__ = ["compute_adaptive_contract"]
