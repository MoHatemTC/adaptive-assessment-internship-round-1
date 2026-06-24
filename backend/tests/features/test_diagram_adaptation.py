from datetime import datetime, timezone

from app.features.diagram.analysis import DimensionVector, DimensionEstimate
from app.features.diagram.adaptation import (
    Action, BlueprintConfig, LearnerProfile, select_next_visual, _clamp,
)


def make_vector(score, confidence, n_cards=3, dim="thinking"):
    estimates = {d: DimensionEstimate(0.0, 0.0, 0) for d in
                 ["thinking", "soft", "work", "digital_ai", "growth"]}
    estimates[dim] = DimensionEstimate(score, confidence, n_cards)
    return DimensionVector(session_id="s1", estimates=estimates, computed_at=datetime.now(timezone.utc))


def make_blueprint(served=1, count=5, lo=1, hi=10):
    return BlueprintConfig(difficulty_min=lo, difficulty_max=hi,
                            visual_question_count=count, visual_questions_served=served)


PROFILE = LearnerProfile(target_role="backend_engineer", self_reported_level=4)


def test_clamp():
    assert _clamp(15, 1, 10) == 10
    assert _clamp(-3, 1, 10) == 1


def test_low_score_steps_difficulty_down():
    decision = select_next_visual(make_vector(0.3, 0.9), PROFILE, make_blueprint(), current_difficulty=5)
    assert decision.action is Action.SERVE_NEXT
    assert decision.target_difficulty == 4


def test_high_score_steps_difficulty_up():
    decision = select_next_visual(make_vector(0.9, 0.9), PROFILE, make_blueprint(), current_difficulty=5)
    assert decision.target_difficulty == 6


def test_mid_score_holds_steady():
    decision = select_next_visual(make_vector(0.6, 0.9), PROFILE, make_blueprint(), current_difficulty=5)
    assert decision.target_difficulty == 5


def test_low_confidence_holds_steady_even_with_low_score():
    decision = select_next_visual(make_vector(0.1, 0.1), PROFILE, make_blueprint(), current_difficulty=5)
    assert decision.target_difficulty == 5


def test_difficulty_clamped_to_blueprint_range():
    decision = select_next_visual(make_vector(0.9, 0.9), PROFILE,
                                   make_blueprint(lo=1, hi=6), current_difficulty=6)
    assert decision.target_difficulty == 6  # would be 7, clamped to max


def test_quota_exhausted_returns_exhaust_type():
    decision = select_next_visual(make_vector(0.3, 0.9), PROFILE,
                                   make_blueprint(served=5, count=5), current_difficulty=5)
    assert decision.action is Action.EXHAUST_TYPE
    assert decision.target_difficulty is None