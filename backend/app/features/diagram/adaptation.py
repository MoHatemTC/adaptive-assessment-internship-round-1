"""
Adaptation layer for the diagram/image feature.

Responsibility: turn a DimensionVector + learner profile + admin blueprint
config into a concrete decision: serve another visual question at difficulty
D on topic T, or stop serving visual questions for this session.

Consumes:  DimensionVector (from analysis.py), LearnerProfile, BlueprintConfig
Produces:  NextVisualDecision (consumed by the examiner agent's router)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.features.diagram.analysis import DimensionVector


class Action(str, Enum):
    SERVE_NEXT = "serve_next"
    EXHAUST_TYPE = "exhaust_type"     # blueprint's visual-question quota is used up


@dataclass(frozen=True)
class LearnerProfile:
    target_role: str
    self_reported_level: int          # 1-10, from intake
    weak_topics_hint: tuple[str, ...] = ()   # optional, from profile/resume parsing


@dataclass(frozen=True)
class BlueprintConfig:
    """Per-assessment admin config relevant to the diagram tool (Phase 0.1's
    blueprint, scoped to this question type)."""
    difficulty_min: int
    difficulty_max: int
    visual_question_count: int
    visual_questions_served: int      # how many already served this session


@dataclass(frozen=True)
class NextVisualDecision:
    action: Action
    target_difficulty: int | None = None
    target_topic_tags: tuple[str, ...] = ()
    rationale: str = ""


# Tunable thresholds — kept as module constants so they're easy to move to
# admin config later without touching selection logic.
LOW_SCORE_THRESHOLD = 0.5
HIGH_SCORE_THRESHOLD = 0.75
MIN_CONFIDENCE_TO_ACT = 0.34   # below this, hold difficulty steady (not enough signal)
STEP_SIZE = 1


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _select_difficulty(
    estimates: DimensionVector,
    current_difficulty: int,
    blueprint: BlueprintConfig,
) -> tuple[int, str]:
    weak_dim = estimates.weakest_dimension()
    estimate = estimates.estimates[weak_dim]

    if estimate.confidence < MIN_CONFIDENCE_TO_ACT:
        return current_difficulty, f"low confidence on '{weak_dim}' ({estimate.confidence}) — holding steady"

    if estimate.score < LOW_SCORE_THRESHOLD:
        new_diff = current_difficulty - STEP_SIZE
        reason = f"'{weak_dim}' scoring low ({estimate.score}) — stepping down"
    elif estimate.score > HIGH_SCORE_THRESHOLD:
        new_diff = current_difficulty + STEP_SIZE
        reason = f"'{weak_dim}' scoring high ({estimate.score}) — stepping up"
    else:
        new_diff = current_difficulty
        reason = f"'{weak_dim}' in target band ({estimate.score}) — holding steady"

    clamped = _clamp(new_diff, blueprint.difficulty_min, blueprint.difficulty_max)
    return clamped, reason


def _select_topics(estimates: DimensionVector, profile: LearnerProfile) -> tuple[str, ...]:
    """Bias topic selection toward the weakest dimension, folding in any
    profile hints. The retriever (Phase 3.3) uses these tags to query Qdrant;
    this layer only decides intent, not the actual lookup."""
    weak_dim = estimates.weakest_dimension()
    tags = (weak_dim,) + profile.weak_topics_hint
    return tags


def select_next_visual(
    estimates: DimensionVector,
    profile: LearnerProfile,
    blueprint: BlueprintConfig,
    current_difficulty: int,
) -> NextVisualDecision:
    """Pure decision function — Phase 3.1 (selector) + 3.2 (blueprint guard)
    combined, since the guard is just a clamp + quota check on the same call."""
    if blueprint.visual_questions_served >= blueprint.visual_question_count:
        return NextVisualDecision(
            action=Action.EXHAUST_TYPE,
            rationale="visual question quota reached for this session",
        )

    difficulty, reason = _select_difficulty(estimates, current_difficulty, blueprint)
    topics = _select_topics(estimates, profile)

    return NextVisualDecision(
        action=Action.SERVE_NEXT,
        target_difficulty=difficulty,
        target_topic_tags=topics,
        rationale=reason,
    )