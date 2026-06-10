import asyncio
from typing import List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.database import async_session
from app.features.mcq.service import build_sample_question, build_submit_response


class GenerateMCQToolInput(BaseModel):
    topic: str = Field(default="Python basics", description="Assessment topic")
    difficulty: str = Field(default="easy", description="Question difficulty")
    question_count: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of MCQ questions to generate",
    )


class GradeMCQToolInput(BaseModel):
    question_id: int = Field(..., description="MCQ question id")
    selected_option: str = Field(..., description="Learner selected option")
    learner_id: Optional[str] = Field(default=None, description="Optional learner id")


async def generate_mcq_for_agent_async(
    topic: str = "Python basics",
    difficulty: str = "easy",
    question_count: int = 1,
):
    """
    Async LangChain-compatible MCQ generation function.

    It creates its own database session because LangChain tools are usually
    called outside FastAPI request dependency injection.
    """
    async with async_session() as db:
        result = await build_sample_question(
            db=db,
            topic=topic,
            difficulty=difficulty,
            question_count=question_count,
        )
        await db.commit()
        return result


async def grade_mcq_for_agent_async(
    question_id: int,
    selected_option: str,
    learner_id: Optional[str] = None,
):
    """
    Async LangChain-compatible MCQ grading function.

    It grades silently and persists the result in PostgreSQL.
    """
    async with async_session() as db:
        result = await build_submit_response(
            db=db,
            question_id=question_id,
            selected_option=selected_option,
            learner_id=learner_id,
        )
        await db.commit()
        return result


def generate_mcq_for_agent(
    topic: str = "Python basics",
    difficulty: str = "easy",
    question_count: int = 1,
):
    """
    Sync wrapper for environments that call LangChain tools synchronously.
    """
    return asyncio.run(
        generate_mcq_for_agent_async(
            topic=topic,
            difficulty=difficulty,
            question_count=question_count,
        )
    )


def grade_mcq_for_agent(
    question_id: int,
    selected_option: str,
    learner_id: Optional[str] = None,
):
    """
    Sync wrapper for environments that call LangChain tools synchronously.
    """
    return asyncio.run(
        grade_mcq_for_agent_async(
            question_id=question_id,
            selected_option=selected_option,
            learner_id=learner_id,
        )
    )


generate_mcq_tool = StructuredTool.from_function(
    name="mcq_generate_question",
    description=(
        "Generate or return an MCQ question for the learner. "
        "Use this when the examiner agent needs to present an MCQ."
    ),
    func=generate_mcq_for_agent,
    coroutine=generate_mcq_for_agent_async,
    args_schema=GenerateMCQToolInput,
)


grade_mcq_tool = StructuredTool.from_function(
    name="mcq_grade_answer",
    description=(
        "Grade a learner MCQ answer silently and persist the score. "
        "Use this after the learner submits an MCQ response."
    ),
    func=grade_mcq_for_agent,
    coroutine=grade_mcq_for_agent_async,
    args_schema=GradeMCQToolInput,
)


def get_mcq_tools() -> List[StructuredTool]:
    """
    Return MCQ LangChain tools ready for registration in the kernel/tool registry.

    Example future usage:
        tool_registry.register_many(get_mcq_tools())
    """
    return [
        generate_mcq_tool,
        grade_mcq_tool,
    ]


MCQ_TOOLS = get_mcq_tools()