"""Tests for grade_results persistence helper."""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import select

from app.core.database import async_session
from app.sessions.models import GradeResult
from app.shared.grading_persist import persist_grade_result, rubric_from_objective_score


@pytest.mark.asyncio
async def test_persist_grade_result_inserts_row():
    session_id = str(uuid.uuid4())
    rubric = rubric_from_objective_score(score=1.0, dimension="thinking")

    async with async_session() as db:
        row_id = await persist_grade_result(
            db,
            session_id=session_id,
            tool_type="mcq",
            tool_session_id=42,
            question_index=0,
            rubric_scores=rubric,
        )
        await db.commit()

        row = (
            await db.exec(select(GradeResult).where(GradeResult.id == row_id))
        ).first()
        assert row is not None
        assert row.tool_type == "mcq"
        assert row.question_index == 0
