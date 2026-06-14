"""
tool.py — LangChain tool wrapping the diagram feature.

The examiner agent (LangChain/LangGraph) calls this when the blueprint
says "next question type = diagram". The tool:
  1. fetches the question (image_url, prompt, rubric, difficulty)
  2. delivers it to the learner via the chat interface
  3. receives the learner's text answer
  4. calls submit_answer → vision grading → returns structured result

The agent uses the returned score + dimension to adapt the next question.
Image is passed to the model as a vision content block — not as text.
"""

from typing import Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import uuid

from app.features.diagram.service import DiagramService
from app.core.database import get_sync_db   # use your project's sync session getter


class DiagramToolInput(BaseModel):
    question_id: str = Field(..., description="UUID of the DiagramQuestion to deliver")
    session_id:  str = Field(..., description="Blueprint session tracking ID")
    answer_text: str = Field(..., description="Learner's text answer to the diagram question")


class DiagramTool(BaseTool):
    """
    LangChain tool for the diagram/image reasoning assessment item.
    Invoked by the examiner agent when the blueprint selects a diagram question.
    Returns a silent structured grading result — score is never shown to the learner.
    """

    name:        str = "diagram_tool"
    description: str = (
        "Deliver a diagram/image question to the learner and grade their text answer "
        "silently against the rubric. Input: question_id, session_id, answer_text. "
        "Output: score (0.0-1.0), dimension, feedback (internal). "
        "Use when the blueprint calls for a diagram/image reasoning item."
    )
    args_schema: Type[BaseModel] = DiagramToolInput

    def _run(
        self,
        question_id: str,
        session_id: str,
        answer_text: str,
    ) -> dict:
        """Sync entry point — delegates to async service via event loop."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._arun(question_id, session_id, answer_text)
        )

    async def _arun(
        self,
        question_id: str,
        session_id: str,
        answer_text: str,
    ) -> dict:
        """
        Async path — preferred when the agent runs in an async context.
        Image is fetched, validated (type + size), and passed to the
        vision model as a base64 content block inside submit_answer.
        """
        service = DiagramService()

        async with get_sync_db() as db:
            answer = await service.submit_answer(
                db=db,
                question_id=uuid.UUID(question_id),
                session_id=uuid.UUID(session_id),
                answer_text=answer_text,
            )
            question = await service.fetch_question(db, uuid.UUID(question_id))
            await db.commit()

        return {
            "answer_id":        str(answer.id),
            "score":            answer.score,
            "dimension":        question.dimension.value,
            "grading_feedback": answer.grading_feedback,
        }