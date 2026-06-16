import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.base_tool import BaseTool
from app.core.database import Base, async_session, engine
from app.core.deps import get_db
from app.features.mcq.api import router as mcq_router
from app.features.mcq.models import MCQOption, MCQQuestion, MCQResponse
from app.features.mcq.service import (
    build_submit_response,
    create_question,
    get_question,
    grade_answer,
)
from app.features.mcq.tool import MCQTool

SAMPLE_OPTIONS = [
    {"label": "2", "text": "2"},
    {"label": "3", "text": "3"},
    {"label": "5", "text": "5"},
    {"label": "23", "text": "23"},
]


async def reset_mcq_tables() -> None:
    """
    Create MCQ tables if needed and clean MCQ data before each database test.

    Tables are registered on the SQLAlchemy 2.0 ``Base`` metadata now that the
    models use the declarative ``Mapped`` style. ``engine.dispose()`` avoids
    Windows asyncpg event-loop reuse issues between pytest async tests.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        await db.exec(delete(MCQResponse))
        await db.exec(delete(MCQOption))
        await db.exec(delete(MCQQuestion))
        await db.commit()

    await engine.dispose()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    await reset_mcq_tables()

    async with async_session() as db:
        try:
            yield db
        finally:
            await db.rollback()
            await db.close()
            await engine.dispose()


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Test replacement for ``get_db`` that commits like the real dependency."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def test_grade_correct_answer():
    result = grade_answer(
        correct_option="C",
        selected_option="C",
    )

    assert result["is_correct"] is True
    assert result["score"] == 1


def test_grade_wrong_answer():
    result = grade_answer(
        correct_option="C",
        selected_option="A",
    )

    assert result["is_correct"] is False
    assert result["score"] == 0


def test_grade_answer_ignores_spaces_and_case():
    result = grade_answer(
        correct_option="C",
        selected_option=" c ",
    )

    assert result["is_correct"] is True
    assert result["score"] == 1


@pytest.mark.asyncio
async def test_build_submit_response(db_session):
    question_in = await create_question(
        db=db_session,
        question_text="What is the output of print(2 + 3)?",
        correct_option="5",
        options=SAMPLE_OPTIONS,
    )

    result = await build_submit_response(
        db=db_session,
        question_id=question_in["id"],
        selected_option="5",
        session_id="session-1",
    )

    await db_session.commit()

    assert result["question_id"] == question_in["id"]
    assert result["is_correct"] is True
    assert result["score"] == 1


@pytest.mark.asyncio
async def test_get_question_does_not_expose_correct_answer(db_session):
    question_in = await create_question(
        db=db_session,
        question_text="What is the output of print(2 + 3)?",
        correct_option="5",
        options=SAMPLE_OPTIONS,
    )

    question = await get_question(db=db_session, question_id=question_in["id"])

    assert question["id"] == question_in["id"]
    assert "question_text" in question
    assert "options" in question
    assert "correct_option" not in question
    assert len(question["options"]) == 4


@pytest.mark.asyncio
async def test_submit_response_is_persisted_in_postgres(db_session):
    question_in = await create_question(
        db=db_session,
        question_text="What is the output of print(2 + 3)?",
        correct_option="5",
        options=SAMPLE_OPTIONS,
    )

    result = await build_submit_response(
        db=db_session,
        question_id=question_in["id"],
        selected_option="5",
        session_id="session-1",
        learner_id="learner-1",
    )

    await db_session.commit()

    saved_result = await db_session.exec(select(MCQResponse))
    saved_responses = saved_result.all()

    assert result["is_correct"] is True
    assert result["score"] == 1
    assert len(saved_responses) == 1
    assert saved_responses[0].question_id == question_in["id"]
    assert saved_responses[0].session_id == "session-1"
    assert saved_responses[0].learner_id == "learner-1"
    assert saved_responses[0].selected_option == "5"
    assert saved_responses[0].is_correct is True
    assert saved_responses[0].score == 1


def test_mcq_tool_conforms_to_base_tool():
    tool = MCQTool()

    assert isinstance(tool, BaseTool)
    assert tool.tool_name == "mcq_tool"
    assert tool.tool_description is not None
    assert tool.build_graph() is not None


def test_submit_answer_round_trip():
    """Create a question over HTTP then submit, asserting no grading leak."""
    asyncio.run(reset_mcq_tables())

    app = FastAPI()
    app.include_router(mcq_router)
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        create_response = client.post(
            "/mcq/questions",
            json={
                "question_text": "What is the output of print(2 + 3)?",
                "difficulty": "easy",
                "correct_option": "5",
                "options": [
                    {"label": "2", "text": "2"},
                    {"label": "3", "text": "3"},
                    {"label": "5", "text": "5"},
                    {"label": "23", "text": "23"},
                ],
            },
        )

        assert create_response.status_code == 200
        question_id = create_response.json()["id"]

        submit_response = client.post(
            "/mcq/submit",
            json={
                "question_id": question_id,
                "session_id": "session-1",
                "selected_option": "5",
            },
        )

    assert submit_response.status_code == 200

    body = submit_response.json()
    assert body["received"] is True
    assert body["question_id"] == question_id
    assert "is_correct" not in body
    assert "score" not in body
