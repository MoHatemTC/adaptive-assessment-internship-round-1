import pytest
from sqlalchemy import delete
from sqlmodel import select

from app.core.database import SQLModel, async_session, engine
from app.features.mcq.models import MCQOption, MCQQuestion, MCQResponse
from app.features.mcq.service import (
    build_sample_question,
    build_submit_response,
    grade_answer,
)
from app.features.mcq.tool import (
    generate_mcq_for_agent_async,
    get_mcq_tools,
)


async def reset_mcq_tables():
    """
    Create MCQ tables if needed and clean MCQ data before each database test.

    engine.dispose() is used to avoid Windows asyncpg event-loop reuse issues
    between pytest async tests.
    """
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        await db.exec(delete(MCQResponse))
        await db.exec(delete(MCQOption))
        await db.exec(delete(MCQQuestion))
        await db.commit()

    await engine.dispose()


@pytest.fixture
async def db_session():
    await reset_mcq_tables()

    async with async_session() as db:
        try:
            yield db
        finally:
            await db.rollback()
            await db.close()
            await engine.dispose()


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
    result = await build_submit_response(
        db=db_session,
        question_id=1,
        correct_option="C",
        selected_option="C",
    )

    await db_session.commit()

    assert result["question_id"] == 1
    assert result["selected_option"] == "C"
    assert result["is_correct"] is True
    assert result["score"] == 1


@pytest.mark.asyncio
async def test_build_sample_question_does_not_expose_correct_answer(db_session):
    question = await build_sample_question(db=db_session)

    assert question["id"] == 1
    assert "question_text" in question
    assert "options" in question
    assert "correct_option" not in question
    assert len(question["options"]) == 4


@pytest.mark.asyncio
async def test_submit_response_is_persisted_in_postgres(db_session):
    result = await build_submit_response(
        db=db_session,
        question_id=1,
        selected_option="C",
        learner_id="learner-1",
    )

    await db_session.commit()

    saved_result = await db_session.exec(select(MCQResponse))
    saved_responses = saved_result.all()

    assert result["is_correct"] is True
    assert result["score"] == 1
    assert len(saved_responses) == 1
    assert saved_responses[0].question_id == 1
    assert saved_responses[0].learner_id == "learner-1"
    assert saved_responses[0].selected_option == "C"
    assert saved_responses[0].is_correct is True
    assert saved_responses[0].score == 1


def test_langchain_mcq_tools_are_available():
    tools = get_mcq_tools()
    tool_names = [tool.name for tool in tools]

    assert "mcq_generate_question" in tool_names
    assert "mcq_grade_answer" in tool_names


@pytest.mark.asyncio
async def test_generate_mcq_for_agent_contract():
    await reset_mcq_tables()

    question = await generate_mcq_for_agent_async(
        topic="Python basics",
        difficulty="easy",
        question_count=1,
    )

    assert question["id"] == 1
    assert question["difficulty"] == "easy"
    assert len(question["options"]) == 4
    assert "correct_option" not in question

    await engine.dispose()


def test_grade_mcq_for_agent_contract():
    tools = get_mcq_tools()
    grade_tool = next(
        tool for tool in tools if tool.name == "mcq_grade_answer"
    )

    assert grade_tool.name == "mcq_grade_answer"
    assert grade_tool.description is not None
    assert grade_tool.args_schema is not None

    fields = grade_tool.args_schema.model_fields

    assert "question_id" in fields
    assert "selected_option" in fields
    assert "learner_id" in fields