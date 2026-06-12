import asyncio
import uuid
from typing import List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.database import async_session
from app.features.diagram.service import DiagramService

service = DiagramService()


class GenerateDiagramToolInput(BaseModel):
    prompt: str = Field(
        ...,
        description="Text description of the system design, flow chart, sequence diagram, or database schema to visualize.",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional learner ID string (must be a valid UUID format if provided).",
    )
    model: Optional[str] = Field(
        default=None,
        description="Optional LLM model name to use for this diagram generation request.",
    )


async def generate_diagram_for_agent_async(
    prompt: str,
    user_id: Optional[str] = None,
    model: Optional[str] = None,
):
    """
    Async LangChain-compatible diagram generation function.

    Creates its own database session since LangChain tools run outside standard endpoint DI.
    """
    uid = None
    if user_id:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            pass

    async with async_session() as db:
        diagram = await service.create_diagram(
            db=db,
            prompt=prompt,
            user_id=uid,
            model=model,
        )
        await db.commit()
        return {
            "id": str(diagram.id),
            "prompt": diagram.prompt,
            "model_name": diagram.model_name,
            "image_url": diagram.image_url,
            "status": diagram.status,
        }


def generate_diagram_for_agent(
    prompt: str,
    user_id: Optional[str] = None,
    model: Optional[str] = None,
):
    """
    Sync wrapper for environments running LangChain tools synchronously.
    """
    return asyncio.run(
        generate_diagram_for_agent_async(
            prompt=prompt,
            user_id=user_id,
            model=model,
        )
    )


generate_diagram_tool = StructuredTool.from_function(
    name="diagram_generate_visualization",
    description=(
        "Generate a visual diagram (e.g. system architecture, sequence diagram, database schema) "
        "based on a textual prompt to present to the learner. Supports optional model override."
    ),
    func=generate_diagram_for_agent,
    coroutine=generate_diagram_for_agent_async,
    args_schema=GenerateDiagramToolInput,
)


def get_diagram_tools() -> List[StructuredTool]:
    """
    Return diagram tools ready for registration in the agent kernel.
    """
    return [generate_diagram_tool]

def get_diagram_multimodel_tools() -> List[StructuredTool]:
    """
    Backward-compatible multimodel alias for diagram tool registration.
    """
    return get_diagram_tools()


DIAGRAM_TOOLS = get_diagram_tools()
DIAGRAM_MULTIMODEL_TOOLS = get_diagram_multimodel_tools()
