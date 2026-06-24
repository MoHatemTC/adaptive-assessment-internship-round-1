from datetime import datetime, timedelta, timezone

from app.features.diagram.evaluation_memory import VisualMemoryCard
from app.features.diagram.analysis import aggregate_dimensions, _confidence_from, _recency_weight


def make_card(scores, minutes_ago=0):
    return VisualMemoryCard(
        session_id="s1", question_id=f"q-{minutes_ago}", difficulty=4,
        topic_tags=("ds",), dimension_scores=scores, grader_confidence=0.8,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )


def test_aggregate_dimensions_no_cards_is_zero_confidence():
    vec = aggregate_dimensions("s1", [])
    assert all(e.n_cards == 0 and e.confidence == 0.0 for e in vec.estimates.values())


def test_aggregate_dimensions_recency_weighting_favors_newest():
    cards = [make_card({"thinking": 0.9}, minutes_ago=0),
              make_card({"thinking": 0.1}, minutes_ago=100)]
    vec = aggregate_dimensions("s1", cards)
    assert vec.estimates["thinking"].score > 0.5  # newer high score dominates


def test_confidence_increases_with_sample_count_decreases_with_variance():
    assert _confidence_from(1, 0.0) < _confidence_from(3, 0.0)
    assert _confidence_from(3, 0.0) > _confidence_from(3, 0.25)


def test_recency_weight_decays_with_distance():
    assert _recency_weight(0) == 1.0
    assert _recency_weight(3) == 0.5  # one half-life out


def test_weakest_dimension_ignores_unscored_dims():
    cards = [make_card({"thinking": 0.2, "soft": 0.9})]
    vec = aggregate_dimensions("s1", cards)
    assert vec.weakest_dimension() == "thinking"