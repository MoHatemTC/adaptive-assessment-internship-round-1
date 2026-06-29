"""Tests for shared blueprint limit helpers."""

from app.shared.blueprint_utils import (
    DEFAULT_CODE_QUESTION_TIME_SECONDS,
    session_time_limit_seconds,
    tool_question_count,
    tool_time_limit_seconds,
)


def test_tool_question_count_reads_planner_shape():
    blueprint = {
        "tools": {
            "code": {"question_count": 10, "dimensions": ["thinking"]},
            "voice": {"question_count": 3},
        },
        "total_questions": 13,
    }
    assert tool_question_count(blueprint, "code") == 10
    assert tool_question_count(blueprint, "voice") == 3


def test_tool_question_count_reads_legacy_shape():
    blueprint = {"coding": {"max_questions": 4}}
    assert tool_question_count(blueprint, "code", legacy_keys=("coding", "code")) == 4


def test_tool_time_limit_seconds_reads_planner_shape():
    blueprint = {
        "tools": {
            "code": {"question_count": 5, "time_limit_seconds": 900},
        }
    }
    assert tool_time_limit_seconds(blueprint, "code") == 900


def test_tool_time_limit_seconds_uses_default_for_code():
    blueprint = {"tools": {"code": {"question_count": 5}}}

    assert (
        tool_time_limit_seconds(
            blueprint,
            "code",
            default=DEFAULT_CODE_QUESTION_TIME_SECONDS,
        )
        == 600
    )


def test_session_time_limit_seconds_reads_blueprint():
    blueprint = {"session_time_limit_seconds": 3600, "tools": {}}
    assert session_time_limit_seconds(blueprint) == 3600
