"""Shared blueprint schema — planner output, examiner input.

The :class:`Blueprint` is the structured contract produced by the planner agent
(:func:`app.agent.nodes.blueprint.run_planner`) and consumed by the examiner
orchestrator (:mod:`app.agent.graph`). It is serialized as ``blueprint_json`` on
:class:`~app.admin.models.Assessment`.

Tool keys here always use the admin vocabulary ``"code"``. The
``AdaptiveContract.tool_type`` vocabulary uses ``"coding"`` instead; the examiner
layer owns the single mapping between the two (see ``TOOL_TO_CONTRACT_TYPE`` in
:mod:`app.agent.graph`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Canonical ordering of tools as the examiner serves them.
_TOOL_ORDER: list[str] = ["mcq", "voice", "diagram", "code"]


class ToolBlueprint(BaseModel):
    """Per-tool configuration within an assessment blueprint.

    Attributes:
        enabled: Whether this tool participates in the assessment.
        question_count: Number of questions this tool contributes (1-10).
        min_difficulty: Lowest difficulty the adaptive loop may select.
        max_difficulty: Highest difficulty the adaptive loop may select.
        time_limit_seconds: Optional per-question time budget, or ``None``.
    """

    enabled: bool
    question_count: int = Field(default=3, ge=0, le=10)
    min_difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    max_difficulty: Literal["beginner", "intermediate", "advanced"] = "advanced"
    time_limit_seconds: int | None = None


class Blueprint(BaseModel):
    """Structured assessment blueprint produced by the planner agent.

    Stored as ``blueprint_json`` on :class:`~app.admin.models.Assessment` and
    read by the examiner to sequence tools.

    Attributes:
        title: Concise assessment title.
        description: One- to two-sentence description.
        tools: Per-tool configuration keyed by ``"mcq"``/``"voice"``/
            ``"diagram"``/``"code"``. Only enabled tools need be present.
        skill_dimensions: Subset of
            ``thinking``/``soft``/``work``/``digital_ai``/``growth``.
        total_questions: Sum of ``question_count`` across all enabled tools.
        session_time_limit_seconds: Optional whole-sitting time budget in seconds.
    """

    title: str
    description: str
    tools: dict[str, ToolBlueprint]
    skill_dimensions: list[str]
    total_questions: int
    session_time_limit_seconds: int | None = None

    def enabled_tools(self) -> list[str]:
        """Return enabled tool names in serving order: mcq, voice, diagram, code.

        Returns:
            The enabled tool keys, filtered and ordered by ``_TOOL_ORDER``.
        """
        return [
            tool
            for tool in _TOOL_ORDER
            if self.tools.get(tool) is not None and self.tools[tool].enabled
        ]
