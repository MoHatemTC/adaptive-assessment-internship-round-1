"""Examiner orchestrator state schema.

The :class:`ExaminerState` is the typed payload threaded through the examiner
LangGraph (:mod:`app.agent.graph`). It is serialized to
``assessment_sessions.examiner_state_json`` between turns, so every field must be
JSON-serializable.

Per the routing-only design, the examiner never processes answers itself — each
tool grades through its own endpoint. The state only tracks *which* tool is
current and how many questions each tool has completed.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ExaminerState(TypedDict):
    """Mutable state for one pass through the examiner graph.

    Attributes:
        session_id: Platform assessment session UUID.
        assessment_id: Owning assessment UUID.
        blueprint: Serialized :class:`~app.shared.schemas.blueprint.Blueprint`.
        learner_profile: Learner context (name/role/consent), read-only here.
        active_tools: Enabled tools in serving order (admin vocabulary).
        current_tool: The tool the learner should use next.
        current_question_index: Global question counter across all tools.
        questions_done: Per-tool completed-question counts.
        current_difficulty: Per-tool current difficulty tier.
        prior_question_ids: Per-tool ids already served (dedup bookkeeping).
        last_response: Routing metadata for this turn, ``{tool, action}``.
        next_question: Tool-render hint for the frontend, or ``None``.
        is_complete: Whether every tool has met its question count.
        error: Set when the turn could not be processed.
    """

    session_id: str
    assessment_id: str
    blueprint: dict[str, Any]
    learner_profile: dict[str, Any]
    active_tools: list[str]
    current_tool: str
    current_question_index: int
    questions_done: dict[str, int]
    current_difficulty: dict[str, str]
    prior_question_ids: dict[str, list[int]]
    last_response: dict[str, Any]
    next_question: dict[str, Any] | None
    is_complete: bool
    error: str | None
