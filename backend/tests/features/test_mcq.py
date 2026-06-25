import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

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
from app.features.mcq.evaluation import evaluate_mcq_answer
from app.features.mcq.loop import run_mcq_loop
from app.features.mcq.models import (
    MCQOption,
    MCQQuestion,
    MCQResponse,
    SkillDimension,
)
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
    models use the declarative ``Mapped`` style. The shared test engine is
    configured in ``tests/conftest.py`` (session-scoped loop + NullPool).
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        await db.exec(delete(MCQResponse))
        await db.exec(delete(MCQOption))
        await db.exec(delete(MCQQuestion))
        await db.commit()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    await reset_mcq_tables()

    async with async_session() as db:
        try:
            yield db
        finally:
            await db.rollback()
            await db.close()


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


# ---------------------------------------------------------------------------
# Sprint 3 — adaptive loop: evaluation, loop orchestration, silent /answer
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "score",
    "correct",
    "is_correct",
    "passed",
    "grading_feedback",
    "rubric_scores",
    "memory_card",
    "memory_summary",
    "dimension_signals",
}


def _assert_no_grading_leak(obj: object) -> None:
    """Recursively assert no grading/internal key appears anywhere in ``obj``."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key not in _FORBIDDEN_KEYS, f"forbidden key leaked: {key}"
            _assert_no_grading_leak(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_grading_leak(item)


async def _make_response(
    db: AsyncSession,
    selected_option: str,
    correct_option: str = "5",
    dimension: str | None = None,
) -> int:
    """Create a question and an ungraded response; return the response id."""
    question_in = await create_question(
        db=db,
        question_text="What is the output of print(2 + 3)?",
        correct_option=correct_option,
        options=SAMPLE_OPTIONS,
        dimension=dimension,
    )
    response = MCQResponse(
        question_id=question_in["id"],
        session_id="session-eval-1",
        selected_option=selected_option,
        is_correct=False,
        score=None,
    )
    db.add(response)
    await db.flush()
    return response.id


@pytest.mark.asyncio
async def test_evaluate_correct_answer_persists_score_1(db_session):
    response_id = await _make_response(db_session, selected_option="5")

    with patch(
        "app.features.mcq.evaluation.run_memory_agent",
        new=AsyncMock(return_value=(None, "summary")),
    ):
        await evaluate_mcq_answer(
            session_id="session-eval-1",
            question_index=0,
            mcq_response_id=response_id,
            db=db_session,
        )

    result = await db_session.exec(
        select(MCQResponse).where(MCQResponse.id == response_id)
    )
    saved = result.first()
    assert saved.score == 1.0
    assert saved.grading_feedback is not None


@pytest.mark.asyncio
async def test_evaluate_wrong_answer_persists_score_0(db_session):
    response_id = await _make_response(db_session, selected_option="2")

    with patch(
        "app.features.mcq.evaluation.run_memory_agent",
        new=AsyncMock(return_value=(None, "summary")),
    ):
        await evaluate_mcq_answer(
            session_id="session-eval-1",
            question_index=0,
            mcq_response_id=response_id,
            db=db_session,
        )

    result = await db_session.exec(
        select(MCQResponse).where(MCQResponse.id == response_id)
    )
    saved = result.first()
    assert saved.score == 0.0


@pytest.mark.asyncio
async def test_evaluate_persists_dimension_to_question(db_session):
    # NOTE: dimension lives on MCQQuestion (read by the shared adaptation agent
    # via question.dimension.value), not on MCQResponse.
    response_id = await _make_response(
        db_session, selected_option="5", dimension="thinking"
    )

    with patch(
        "app.features.mcq.evaluation.run_memory_agent",
        new=AsyncMock(return_value=(None, "summary")),
    ):
        await evaluate_mcq_answer(
            session_id="session-eval-1",
            question_index=0,
            mcq_response_id=response_id,
            db=db_session,
        )

    resp_result = await db_session.exec(
        select(MCQResponse).where(MCQResponse.id == response_id)
    )
    saved_response = resp_result.first()
    q_result = await db_session.exec(
        select(MCQQuestion).where(MCQQuestion.id == saved_response.question_id)
    )
    question = q_result.first()
    assert question.dimension == SkillDimension.thinking


@pytest.mark.asyncio
async def test_evaluate_calls_memory_agent_with_correct_tool_type():
    """Mocked-DB variant: avoids the real-Postgres ``db_session`` fixture so
    this test cannot time out waiting on the Supabase connection. The DB layer
    is faked with in-memory model instances and a mocked ``db.exec``; only the
    call into ``run_memory_agent`` is asserted.
    """
    mcq_response = MCQResponse(
        id=1,
        question_id=10,
        session_id="session-eval-1",
        selected_option="5",
        is_correct=False,
        score=None,
    )
    question = MCQQuestion(
        id=10,
        question_text="What is the output of print(2 + 3)?",
        correct_option="5",
        difficulty="easy",
        dimension=None,
    )
    options = [
        MCQOption(id=1, question_id=10, label="2", text="2"),
        MCQOption(id=2, question_id=10, label="3", text="3"),
        MCQOption(id=3, question_id=10, label="5", text="5"),
        MCQOption(id=4, question_id=10, label="23", text="23"),
    ]

    response_result = MagicMock()
    response_result.first.return_value = mcq_response
    question_result = MagicMock()
    question_result.first.return_value = question
    options_result = MagicMock()
    options_result.all.return_value = options

    db = AsyncMock()
    db.exec = AsyncMock(side_effect=[response_result, question_result, options_result])
    db.commit = AsyncMock()

    memory_mock = AsyncMock(return_value=(None, "summary"))
    with patch("app.features.mcq.evaluation.run_memory_agent", new=memory_mock):
        await evaluate_mcq_answer(
            session_id="session-eval-1",
            question_index=0,
            mcq_response_id=1,
            db=db,
        )

    memory_mock.assert_awaited_once()
    assert memory_mock.await_args.kwargs["tool_type"] == "mcq"


@pytest.mark.asyncio
async def test_loop_returns_complete_when_last_question():
    eval_mock = AsyncMock(return_value={"memory_card": None, "memory_summary": ""})
    with patch("app.features.mcq.loop.evaluate_mcq_answer", new=eval_mock):
        result = await run_mcq_loop(
            session_id="s1",
            question_index=4,
            mcq_response_id=1,
            total_questions=5,
            db=AsyncMock(),
        )
    assert result["is_complete"] is True


@pytest.mark.asyncio
async def test_loop_returns_not_complete_when_more_questions_remain():
    eval_mock = AsyncMock(return_value={"memory_card": None, "memory_summary": ""})
    with patch("app.features.mcq.loop.evaluate_mcq_answer", new=eval_mock):
        result = await run_mcq_loop(
            session_id="s1",
            question_index=0,
            mcq_response_id=1,
            total_questions=5,
            db=AsyncMock(),
        )
    assert result["is_complete"] is False


def test_answer_endpoint_response_never_contains_score():
    """The adaptive /answer endpoint must never leak any grading detail."""
    asyncio.run(reset_mcq_tables())

    app = FastAPI()
    app.include_router(mcq_router)
    app.dependency_overrides[get_db] = _override_get_db

    next_question = {
        "id": 999,
        "question_text": "Next question?",
        "difficulty": "beginner",
        "dimension": "thinking",
        "options": [
            {"label": "A", "text": "alpha"},
            {"label": "B", "text": "beta"},
        ],
    }

    loop_mock = AsyncMock(
        return_value={
            "is_complete": False,
            "memory_card": None,
            "memory_summary": "internal only",
        }
    )
    gen_mock = AsyncMock(return_value=next_question)

    with (
        patch("app.features.mcq.api.run_mcq_loop", new=loop_mock),
        patch("app.features.mcq.api.generate_and_store_next_mcq", new=gen_mock),
        TestClient(app) as client,
    ):
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

        answer_response = client.post(
            f"/mcq/sessions/{'session-answer-1'}/answer",
            json={
                "question_id": question_id,
                "selected_option": "5",
                "question_index": 0,
                "total_questions": 5,
            },
        )

    assert answer_response.status_code == 200
    body = answer_response.json()

    assert body["is_complete"] is False
    assert body["next_question"]["id"] == 999
    # No grading detail anywhere in the payload, at any nesting level.
    _assert_no_grading_leak(body)
    # And specifically: options carry no answer key.
    for option in body["next_question"]["options"]:
        assert "is_correct" not in option
        assert set(option.keys()) == {"label", "text"}
