from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import Base, async_session, engine
from app.features.diagram.models import DiagramQuestion, DiagramResponse
from app.features.diagram.service import (
    create_question,
    get_correct_label,
    get_question,
    grade_answer,
    submit_response,
)

SVG = '<svg width="600" height="400"><rect/><text>[?]</text></svg>'


async def reset_diagram_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        await db.exec(delete(DiagramResponse))
        await db.exec(delete(DiagramQuestion))
        await db.commit()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    await reset_diagram_tables()
    async with async_session() as db:
        try:
            yield db
        finally:
            await db.rollback()
            await db.close()


async def _question(db: AsyncSession) -> dict:
    return await create_question(
        db=db,
        svg_content=SVG,
        prompt="What is [?]?",
        correct_label="Load Balancer",
        rubric="Accept LB.",
        dimension="digital_ai",
    )


@pytest.mark.asyncio
async def test_create_question_excludes_correct_label(db_session):
    result = await _question(db_session)
    assert "correct_label" not in result


@pytest.mark.asyncio
async def test_create_question_excludes_rubric(db_session):
    result = await _question(db_session)
    assert "rubric" not in result


@pytest.mark.asyncio
async def test_get_question_excludes_correct_label(db_session):
    created = await _question(db_session)
    result = await get_question(db_session, created["id"])
    assert "correct_label" not in result


@pytest.mark.asyncio
async def test_get_question_excludes_rubric(db_session):
    created = await _question(db_session)
    result = await get_question(db_session, created["id"])
    assert "rubric" not in result


@pytest.mark.asyncio
async def test_get_question_404(db_session):
    with pytest.raises(HTTPException) as exc:
        await get_question(db_session, 99999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_correct_label_returns_string(db_session):
    created = await _question(db_session)
    assert await get_correct_label(db_session, created["id"]) == "Load Balancer"


@pytest.mark.asyncio
async def test_submit_response_persists_row(db_session):
    created = await _question(db_session)
    with patch(
        "app.features.diagram.service.grade_answer",
        new=AsyncMock(return_value={"score": 1.0, "feedback": "ok"}),
    ):
        result = await submit_response(
            db_session, created["id"], "session-1", "LB", "learner-1"
        )
    rows = (await db_session.exec(select(DiagramResponse))).all()
    assert result["response_id"] == rows[0].id
    assert rows[0].answer_text == "LB"
    assert rows[0].score == 1.0


@pytest.mark.asyncio
async def test_submit_response_calls_grade_answer(db_session):
    created = await _question(db_session)
    mock = AsyncMock(return_value={"score": 1.0, "feedback": "ok"})
    with patch("app.features.diagram.service.grade_answer", new=mock):
        await submit_response(db_session, created["id"], "session-1", "LB")
    mock.assert_awaited_once_with(
        correct_label="Load Balancer", rubric="Accept LB.", answer_text="LB"
    )


class FakeLLM:
    def __init__(self, content=None, error: Exception | None = None):
        self.content = content
        self.error = error
        self.model = "fake"

    async def ainvoke(self, *args, **kwargs):
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.content)


@pytest.mark.asyncio
async def test_grade_answer_returns_1_for_correct():
    with patch(
        "app.core.llm.get_llm_with_tracing",
        return_value=(FakeLLM('{"score": 1, "feedback": "correct"}'), []),
    ):
        result = await grade_answer("Load Balancer", "Accept LB.", "Load Balancer")
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_grade_answer_returns_1_for_semantic_eq():
    with patch(
        "app.core.llm.get_llm_with_tracing",
        return_value=(FakeLLM('{"score": 1, "feedback": "LB accepted"}'), []),
    ):
        result = await grade_answer("Load Balancer", "Accept LB.", "LB")
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_grade_answer_returns_0_for_wrong():
    with patch(
        "app.core.llm.get_llm_with_tracing",
        return_value=(FakeLLM('{"score": 0, "feedback": "wrong"}'), []),
    ):
        result = await grade_answer("Load Balancer", "Accept LB.", "Firewall")
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_grade_answer_clamps_non_binary_score():
    with patch(
        "app.core.llm.get_llm_with_tracing",
        return_value=(FakeLLM('{"score": 0.7, "feedback": "partial"}'), []),
    ):
        result = await grade_answer("Load Balancer", "Accept LB.", "proxy")
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_grade_answer_survives_llm_failure():
    with patch(
        "app.core.llm.get_llm_with_tracing",
        return_value=(FakeLLM(error=RuntimeError("boom")), []),
    ):
        result = await grade_answer("Load Balancer", "Accept LB.", "LB")
    assert result == {"score": 0.0, "feedback": "Grading unavailable"}
