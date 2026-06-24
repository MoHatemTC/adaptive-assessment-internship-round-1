"""Tests for session radar report aggregation."""

from __future__ import annotations

from app.reports.schemas import dimension_label
from app.reports.service import aggregate_dimension_scores
from app.sessions.models import SkillDimensionScore


def _row(**kwargs) -> SkillDimensionScore:
    defaults = {
        "session_id": "sess-1",
        "question_index": 0,
        "tool_type": "voice",
        "thinking": None,
        "soft": None,
        "work": None,
        "digital_ai": None,
        "growth": None,
    }
    defaults.update(kwargs)
    return SkillDimensionScore(**defaults)


def test_aggregate_dimension_scores_averages_across_rows():
    rows = [
        _row(question_index=0, thinking=8, soft=6, work=None),
        _row(question_index=1, tool_type="coding", thinking=6, work=9, digital_ai=7),
    ]
    scores = aggregate_dimension_scores(rows)
    assert scores["thinking"] == 7
    assert scores["soft"] == 6
    assert scores["work"] == 9
    assert scores["digital_ai"] == 7
    assert scores["growth"] is None


def test_aggregate_dimension_scores_empty():
    assert aggregate_dimension_scores([])["thinking"] is None


def test_dimension_labels():
    assert dimension_label("thinking") == "Reasoning"
    assert dimension_label("digital_ai") == "Digital & AI"
