"""MCQ examiner-agent tool, implemented as a :class:`BaseTool` subgraph.

The MCQ tool exposes objective grading to the examiner agent through the kernel
:class:`~app.core.base_tool.BaseTool` contract. ``build_graph`` returns a
compiled LangGraph ``StateGraph`` whose single node grades and persists a
learner's answer silently — the graph output carries only a ``received`` flag,
never a score.
"""

from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.base_tool import BaseTool
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.mcq.service import build_submit_response

_logger = get_logger(__name__)


class MCQState(TypedDict, total=False):
    """State passed through the MCQ grading subgraph.

    Attributes:
        question_id: Primary key of the answered question.
        selected_option: The option identifier the learner submitted.
        session_id: Owning assessment session id.
        learner_id: Optional learner identifier.
        received: Set to ``True`` once the answer is graded and persisted.
    """

    question_id: int
    selected_option: str
    session_id: str
    learner_id: Optional[str]
    received: bool


class MCQTool(BaseTool):
    """Examiner-agent tool that presents and objectively scores MCQ items."""

    @property
    def tool_name(self) -> str:
        """Stable identifier used by the agent registry and observability.

        Returns:
            The tool name ``"mcq_tool"``.
        """
        return "mcq_tool"

    @property
    def tool_description(self) -> str:
        """Natural-language summary the agent uses to decide when to call this.

        Returns:
            A short description of the tool's behaviour.
        """
        return "Presents structured MCQ items and scores them objectively"

    def build_graph(self) -> CompiledStateGraph:
        """Build and compile the MCQ grading subgraph.

        Returns:
            A compiled single-node graph that grades and persists an answer.
        """
        graph: StateGraph = StateGraph(MCQState)
        graph.add_node("grade", self._grade_node)
        graph.set_entry_point("grade")
        graph.add_edge("grade", END)
        return graph.compile()

    async def _grade_node(self, state: MCQState) -> dict[str, Any]:
        """Silently grade and persist the learner's answer.

        Opens its own database session because the tool runs outside the FastAPI
        request lifecycle. The returned state update carries only ``received`` —
        the score is persisted server-side and never surfaced to the learner.

        Args:
            state: The incoming graph state with question and answer fields.

        Returns:
            A state update marking the answer as received.
        """
        async with async_session() as db:
            await build_submit_response(
                db=db,
                question_id=state["question_id"],
                selected_option=state["selected_option"],
                session_id=state["session_id"],
                learner_id=state.get("learner_id"),
            )
            await db.commit()

        return {"received": True}
