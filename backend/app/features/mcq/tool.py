"""MCQ examiner-agent tool, implemented as a BaseTool subgraph.

The MCQ tool exposes the adaptive MCQ loop to the examiner agent through the
kernel BaseTool contract.

The graph output never exposes correctness, score, or correct_option to the
learner.
"""

from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.base_tool import BaseTool
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.mcq.loop import run_mcq_adaptive_loop

_logger = get_logger(__name__)


class MCQState(TypedDict, total=False):
    """State passed through the MCQ adaptive subgraph."""

    question_id: int
    selected_option: str
    session_id: str
    question_index: int
    learner_profile: Optional[dict[str, Any]]
    admin_config: Optional[dict[str, Any]]
    received: bool
    next_plan: dict[str, Any]
    next_question: dict[str, Any]


class MCQTool(BaseTool):
    """Examiner-agent tool that runs the adaptive MCQ loop."""

    @property
    def tool_name(self) -> str:
        """Stable identifier used by the agent registry and observability."""
        return "mcq_tool"

    @property
    def tool_description(self) -> str:
        """Natural-language summary the examiner agent uses to call this tool."""
        return (
            "Runs adaptive MCQ assessment: silently grades the current answer, "
            "adapts the next plan, and generates the next MCQ through the "
            "LiteLLM gateway."
        )

    def build_graph(self) -> CompiledStateGraph:
        """Build and compile the MCQ adaptive subgraph."""
        graph: StateGraph = StateGraph(MCQState)
        graph.add_node("adaptive_loop", self._adaptive_loop_node)
        graph.set_entry_point("adaptive_loop")
        graph.add_edge("adaptive_loop", END)
        return graph.compile()

    async def _adaptive_loop_node(self, state: MCQState) -> dict[str, Any]:
        """Run one adaptive MCQ step."""
        async with async_session() as db:
            result = await run_mcq_adaptive_loop(
                db=db,
                question_id=state["question_id"],
                selected_option=state["selected_option"],
                session_id=state["session_id"],
                question_index=state["question_index"],
                learner_profile=state.get("learner_profile"),
                admin_config=state.get("admin_config"),
            )
            await db.commit()

        _logger.info(
            "mcq_adaptive_tool_step_completed",
            question_id=state["question_id"],
            session_id=state["session_id"],
            question_index=state["question_index"],
        )

        return {
            "received": True,
            "next_plan": result["next_plan"],
            "next_question": result["next_question"],
        }
