"""Tests for the examiner orchestrator nodes.

The examiner is routing-only: it sequences tools and tracks per-tool progress,
never grading. These tests exercise the pure node functions directly.
"""

from __future__ import annotations

from typing import Any

from app.agent.graph import (
    check_completion,
    route_question,
    run_tool_loop,
    update_session,
)


def _blueprint() -> dict[str, Any]:
    """An mcq(2) + voice(1) blueprint, total 3 questions."""
    return {
        "title": "Screen",
        "description": "Desc",
        "tools": {
            "mcq": {
                "enabled": True,
                "question_count": 2,
                "min_difficulty": "beginner",
                "max_difficulty": "advanced",
                "time_limit_seconds": None,
            },
            "voice": {
                "enabled": True,
                "question_count": 1,
                "min_difficulty": "beginner",
                "max_difficulty": "intermediate",
                "time_limit_seconds": 180,
            },
        },
        "skill_dimensions": ["thinking"],
        "total_questions": 3,
    }


def _state(**overrides: Any) -> dict[str, Any]:
    """Build a complete examiner state, with optional field overrides."""
    state: dict[str, Any] = {
        "session_id": "sess-1",
        "assessment_id": "assess-1",
        "blueprint": _blueprint(),
        "learner_profile": {},
        "active_tools": ["mcq", "voice"],
        "current_tool": "",
        "current_question_index": 0,
        "questions_done": {"mcq": 0, "voice": 0},
        "current_difficulty": {"mcq": "beginner", "voice": "beginner"},
        "prior_question_ids": {"mcq": [], "voice": []},
        "last_response": {},
        "next_question": None,
        "is_complete": False,
        "error": None,
    }
    state.update(overrides)
    return state


def test_examiner_routes_to_first_enabled_tool():
    state = _state()
    result = route_question(state)
    assert result["current_tool"] == "mcq"
    assert result["next_question"]["tool"] == "mcq"


def test_examiner_marks_complete_when_all_questions_done():
    state = _state(questions_done={"mcq": 2, "voice": 1})
    result = check_completion(state)
    assert result["is_complete"] is True


def test_examiner_increments_question_count():
    state = _state(last_response={"tool": "mcq", "action": "next"})
    result = run_tool_loop(state)
    assert result["questions_done"]["mcq"] == 1
    assert result["questions_done"]["voice"] == 0


def test_examiner_complete_tool_fast_forwards():
    state = _state(last_response={"tool": "mcq", "action": "complete_tool"})
    result = run_tool_loop(state)
    assert result["questions_done"]["mcq"] == 2


def test_examiner_update_session_sums_progress():
    state = _state(questions_done={"mcq": 2, "voice": 0})
    result = update_session(state)
    assert result["current_question_index"] == 2


def test_examiner_routes_to_second_tool_when_first_done():
    state = _state(questions_done={"mcq": 2, "voice": 0})
    result = route_question(state)
    assert result["current_tool"] == "voice"
