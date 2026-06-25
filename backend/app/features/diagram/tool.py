from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.base_tool import BaseTool
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.diagram.service import submit_response

_logger = get_logger(__name__)


class DiagramState(TypedDict, total=False):
    question_id: int
    answer_text: str
    session_id: str
    learner_id: Optional[str]
    received: bool


class DiagramTool(BaseTool):
    @property
    def tool_name(self) -> str:
        return "diagram_tool"

    @property
    def tool_description(self) -> str:
        return (
            "Presents an SVG diagram with one blank component label. "
            "The learner identifies the blank. Grades silently as 1 (correct) or 0 (wrong)."
        )

    def build_graph(self) -> CompiledStateGraph:
        graph: StateGraph = StateGraph(DiagramState)
        graph.add_node("grade", self._grade_node)
        graph.set_entry_point("grade")
        graph.add_edge("grade", END)
        return graph.compile()

    async def _grade_node(self, state: DiagramState) -> dict[str, Any]:
        async with async_session() as db:
            await submit_response(
                db=db,
                question_id=state["question_id"],
                answer_text=state["answer_text"],
                session_id=state["session_id"],
                learner_id=state.get("learner_id"),
            )
            await db.commit()
        return {"received": True}
