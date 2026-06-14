"""Tests for adaptive difficulty and category selection."""

from __future__ import annotations

import json

import pytest

from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from app.features.code.adaptation import decide_next_adaptation, initial_adaptation_decision
from app.features.code.adaptive_schemas import LearnerCodeAnalysis
from app.features.code.models import CodeMemoryCard


def test_initial_adaptation_uses_profile():
    profile = UserProfile(
        name="Learner",
        skills=["Python"],
        experience_level="beginner",
    )
    decision = initial_adaptation_decision(profile, PlatformChallengeConfig())
    assert decision.next_difficulty == "beginner"
    assert decision.next_category


def test_bump_difficulty_on_strong_performance():
    profile = UserProfile(name="Learner", skills=["Python"], experience_level="intermediate")
    config = PlatformChallengeConfig()
    analysis = LearnerCodeAnalysis(
        dimension_estimates={"problem_solving": 0.8},
        strong_problem_types=["arrays"],
        weak_problem_types=[],
        average_pass_rate=0.9,
        average_efficiency=0.8,
        average_rubric_score=0.85,
        turns_completed=1,
    )
    last = CodeMemoryCard(
        id=1,
        code_session_id="assess-x",
        challenge_id=1,
        problem_type="arrays",
        difficulty="intermediate",
        language="python",
        pass_rate=0.9,
        efficiency=0.8,
        rubric_score=0.85,
        dimension_signals_json="{}",
        passed=True,
        test_results_json="[]",
    )
    decision = decide_next_adaptation(
        analysis,
        profile,
        config,
        last_card=last,
        current_difficulty="intermediate",
    )
    assert decision.next_difficulty == "advanced"


def test_lower_difficulty_on_weak_performance():
    profile = UserProfile(name="Learner", skills=["Python"], experience_level="intermediate")
    config = PlatformChallengeConfig()
    analysis = LearnerCodeAnalysis(
        dimension_estimates={"problem_solving": 0.3},
        strong_problem_types=[],
        weak_problem_types=["strings"],
        average_pass_rate=0.3,
        average_efficiency=0.4,
        average_rubric_score=0.35,
        turns_completed=1,
    )
    last = CodeMemoryCard(
        id=1,
        code_session_id="assess-x",
        challenge_id=1,
        problem_type="strings",
        difficulty="intermediate",
        language="python",
        pass_rate=0.2,
        efficiency=0.4,
        rubric_score=0.3,
        dimension_signals_json="{}",
        passed=False,
        test_results_json="[]",
    )
    decision = decide_next_adaptation(
        analysis,
        profile,
        config,
        last_card=last,
        current_difficulty="intermediate",
    )
    assert decision.next_difficulty == "beginner"
    assert decision.next_category == "strings"
