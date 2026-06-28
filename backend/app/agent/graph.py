"""Examiner orchestrator — a routing-only LangGraph over an assessment blueprint.

The examiner does **not** process answers. Each tool grades through its own
endpoint (``POST /mcq/sessions/{id}/answer``, ``POST /voice/adaptive/...``).
The examiner's sole job per turn is to settle the just-completed question, track
per-tool progress, and tell the frontend which tool widget to render next.

Graph (linear): ``START → run_tool_loop → update_session → check_completion →
route_question → END``.

Note: the suggested order in the build prompt placed ``route_question`` first.
With the routing-only design (decision item 6) the just-answered question must be
counted *before* routing, otherwise routing would run against stale counts and a
tool could be over- or under-served. The node order is therefore
increment-then-route.
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.agent.state import ExaminerState
from app.core.logging import get_logger
from app.sessions.models import AssessmentSession
from app.shared.schemas.blueprint import Blueprint

logger = get_logger(__name__)

#: Blueprint/admin tool keys → AdaptiveContract.tool_type vocabulary. Owned here
#: only; Blueprint and admin always use "code", AdaptiveContract uses "coding".
TOOL_TO_CONTRACT_TYPE: dict[str, str] = {
    "mcq": "mcq",
    "voice": "voice",
    "diagram": "diagram",
    "code": "coding",
}


def _tool_count(blueprint: dict[str, Any], tool: str) -> int:
    """Return the configured question_count for a tool, or 0 if absent.

    Args:
        blueprint: Serialized blueprint dict.
        tool: Tool key in admin vocabulary.

    Returns:
        The tool's ``question_count`` (defaults to 0 when the tool is absent).
    """
    tools = blueprint.get("tools", {})
    cfg = tools.get(tool) or {}
    try:
        return int(cfg.get("question_count", 0))
    except (TypeError, ValueError):
        return 0


def run_tool_loop(state: ExaminerState) -> dict[str, Any]:
    """Settle the just-completed question for the answering tool.

    Routing-only: this does not grade or generate. ``action == "next"``
    increments the tool's completed count by one (capped at its blueprint
    count); ``action == "complete_tool"`` fast-forwards the tool to done.

    Args:
        state: Current examiner state with ``last_response`` populated.

    Returns:
        A partial state update with the new ``questions_done`` mapping.
    """
    last = state.get("last_response") or {}
    tool = last.get("tool")
    action = last.get("action")
    questions_done = dict(state["questions_done"])

    if tool in questions_done:
        count = _tool_count(state["blueprint"], tool)
        if action == "next":
            questions_done[tool] = min(questions_done[tool] + 1, count)
        elif action == "complete_tool":
            questions_done[tool] = count

    logger.info("examiner_tool_advanced", tool=tool, action=action)
    return {"questions_done": questions_done}


def update_session(state: ExaminerState) -> dict[str, Any]:
    """Recompute the global question index from per-tool progress.

    Args:
        state: Current examiner state.

    Returns:
        A partial state update with ``current_question_index``.
    """
    total_done = sum(state["questions_done"].values())
    logger.info("examiner_session_updated", question_index=total_done)
    return {"current_question_index": total_done}


def check_completion(state: ExaminerState) -> dict[str, Any]:
    """Mark the session complete once all blueprint questions are done.

    Args:
        state: Current examiner state.

    Returns:
        A partial state update with the ``is_complete`` flag.
    """
    total_questions = int(state["blueprint"].get("total_questions", 0) or 0)
    total_done = sum(state["questions_done"].values())
    is_complete = total_done >= total_questions if total_questions else False
    if is_complete:
        logger.info("examiner_session_complete", session_id=state["session_id"])
    return {"is_complete": is_complete}


def route_question(state: ExaminerState) -> dict[str, Any]:
    """Pick the next tool to serve and build the frontend render hint.

    Selects the first enabled tool whose completed count is below its blueprint
    question count. When none remain the session is complete.

    Args:
        state: Current examiner state.

    Returns:
        A partial state update with ``current_tool`` and ``next_question`` (a
        learner-safe render hint carrying no scores), and ``is_complete`` when
        every tool is exhausted.
    """
    if state.get("is_complete"):
        return {"current_tool": "", "next_question": None}

    questions_done = state["questions_done"]
    current = ""
    for tool in state["active_tools"]:
        if questions_done.get(tool, 0) < _tool_count(state["blueprint"], tool):
            current = tool
            break

    if not current:
        return {"current_tool": "", "next_question": None, "is_complete": True}

    difficulty = state["current_difficulty"].get(current, "beginner")
    next_question = {
        "tool": current,
        "difficulty": difficulty,
        "question_number": questions_done.get(current, 0) + 1,
        "total_for_tool": _tool_count(state["blueprint"], current),
        "max_questions": _tool_count(state["blueprint"], current),
    }
    logger.info(
        "examiner_routed",
        tool=current,
        index=state["current_question_index"],
    )
    return {"current_tool": current, "next_question": next_question}


def _build_examiner_graph() -> CompiledStateGraph:
    """Compile the linear examiner graph.

    Returns:
        The compiled examiner :class:`CompiledStateGraph`.
    """
    builder = StateGraph(ExaminerState)
    builder.add_node("run_tool_loop", run_tool_loop)
    builder.add_node("update_session", update_session)
    builder.add_node("check_completion", check_completion)
    builder.add_node("route_question", route_question)

    builder.add_edge(START, "run_tool_loop")
    builder.add_edge("run_tool_loop", "update_session")
    builder.add_edge("update_session", "check_completion")
    builder.add_edge("check_completion", "route_question")
    builder.add_edge("route_question", END)
    return builder.compile()


#: Process-wide compiled examiner graph.
examiner_graph: CompiledStateGraph = _build_examiner_graph()


def _initial_state(
    session: AssessmentSession,
    blueprint: Blueprint,
) -> ExaminerState:
    """Build a fresh examiner state from a blueprint at session start.

    Args:
        session: The owning assessment session row.
        blueprint: The parsed assessment blueprint.

    Returns:
        A new :class:`ExaminerState` with zeroed per-tool progress.
    """
    active_tools = blueprint.enabled_tools()
    try:
        learner_profile = json.loads(session.learner_profile_json)
    except (TypeError, json.JSONDecodeError):
        learner_profile = {}
    return ExaminerState(
        session_id=session.id,
        assessment_id=session.assessment_id,
        blueprint=blueprint.model_dump(),
        learner_profile=learner_profile if isinstance(learner_profile, dict) else {},
        active_tools=active_tools,
        current_tool=active_tools[0] if active_tools else "",
        current_question_index=0,
        questions_done={tool: 0 for tool in active_tools},
        current_difficulty={
            tool: blueprint.tools[tool].min_difficulty for tool in active_tools
        },
        prior_question_ids={tool: [] for tool in active_tools},
        last_response={},
        next_question=None,
        is_complete=False,
        error=None,
    )


async def run_examiner_turn(
    session_id: str,
    tool: str,
    action: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Process one routing turn through the examiner orchestrator.

    Loads (or initializes) examiner state from the session, runs the graph to
    settle the answered question and route to the next tool, then persists the
    updated state. The return value is learner-safe: it carries no scores,
    grading, or memory details.

    Args:
        session_id: Platform assessment session UUID.
        tool: Tool the learner just acted on (admin vocabulary, e.g. ``"mcq"``).
        action: ``"next"`` to advance one question, ``"complete_tool"`` to finish
            the tool, or ``"start"`` to fetch the first tool without advancing.
        db: Active async database session.

    Returns:
        ``{"current_tool", "next_tool_info", "is_complete"}``.

    Raises:
        ValueError: If the session or its assessment/blueprint is missing.
    """
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise ValueError(f"AssessmentSession not found: {session_id}")

    assessment = await db.get(Assessment, session.assessment_id)
    if assessment is None:
        raise ValueError(f"Assessment not found: {session.assessment_id}")

    try:
        blueprint = Blueprint.model_validate_json(assessment.blueprint_json)
    except Exception as exc:  # noqa: BLE001 - invalid/empty blueprint is a 4xx upstream
        raise ValueError(
            f"Assessment {assessment.id} has no valid blueprint"
        ) from exc

    if session.examiner_state_json:
        try:
            state: ExaminerState = json.loads(session.examiner_state_json)
        except (TypeError, json.JSONDecodeError):
            state = _initial_state(session, blueprint)
    else:
        state = _initial_state(session, blueprint)

    state["last_response"] = {"tool": tool, "action": action}

    final_state: ExaminerState = await examiner_graph.ainvoke(state)

    session.examiner_state_json = json.dumps(final_state)
    await db.commit()

    return {
        "current_tool": final_state.get("current_tool") or None,
        "next_tool_info": final_state.get("next_question"),
        "is_complete": bool(final_state.get("is_complete")),
    }


__all__ = [
    "TOOL_TO_CONTRACT_TYPE",
    "examiner_graph",
    "run_examiner_turn",
]
