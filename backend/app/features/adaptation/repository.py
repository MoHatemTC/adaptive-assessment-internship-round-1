"""
app/features/adaptation/repository.py

The ONLY file that imports feature-specific answer models.
Each `_fetch_<tool>_answers` function queries that tool's table and
maps rows into the shared AnswerRecord shape.

When voice/camera/code features land, add one function each here —
the agent and prompt code never need to change.
"""

import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.adaptation.schemas import AnswerRecord


async def _fetch_diagram_answers(db: AsyncSession, session_id: uuid.UUID) -> list[AnswerRecord]:
    from app.features.diagram.models import DiagramAnswer

    result = await db.execute(
        select(DiagramAnswer)
        .options(selectinload(DiagramAnswer.question))
        .where(DiagramAnswer.session_id == session_id)
        .where(DiagramAnswer.score.isnot(None))
    )
    rows = result.scalars().all()
    return [
        AnswerRecord(
            tool="diagram",
            dimension=row.question.dimension.value,
            score=row.score,
            feedback=row.grading_feedback or "",
        )
        for row in rows
    ]


async def _fetch_mcq_answers(db: AsyncSession, session_id: uuid.UUID) -> list[AnswerRecord]:
    # TODO: wire up once app.features.mcq.models is available.
    # Expected shape: MCQAnswer with session_id, dimension, score (0.0-1.0), feedback.
    return []


async def _fetch_voice_answers(db: AsyncSession, session_id: uuid.UUID) -> list[AnswerRecord]:
    # TODO: wire up once app.features.voice.models is available.
    return []


async def _fetch_code_answers(db: AsyncSession, session_id: uuid.UUID) -> list[AnswerRecord]:
    # TODO: wire up once app.features.code.models is available.
    return []


async def fetch_all_answers(db: AsyncSession, session_id: uuid.UUID) -> list[AnswerRecord]:
    """
    Gathers normalized answers across every tool used in this session so far.
    Add a new _fetch_<tool>_answers function and one line below when a
    new feature lands — nothing else in core/adaptation changes.
    """
    answers: list[AnswerRecord] = []
    answers += await _fetch_diagram_answers(db, session_id)
    answers += await _fetch_mcq_answers(db, session_id)
    answers += await _fetch_voice_answers(db, session_id)
    answers += await _fetch_code_answers(db, session_id)
    return answers