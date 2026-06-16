import warnings
from collections.abc import AsyncGenerator

warnings.filterwarnings(
    "ignore",
    message=r"Using `httpx` with `starlette.testclient` is deprecated.*",
)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.base_tool import BaseTool
from app.core.database import Base, async_session, engine
from app.core.deps import get_db
from app.features.mcq.adaptation import select_next_mcq_plan
from app.features.mcq.analysis import analyze_mcq_session
from app.features.mcq.api import router as mcq_router
from app.features.mcq.llm_generation import _extract_json_from_llm_response
from app.features.mcq.models import MCQOption, MCQQuestion, MCQResponse
from app.features.mcq.service import (
    build_submit_response,
    create_question,
    get_question,
    grade_answer,
)
from app.features.mcq.tool import MCQTool


SESSION_ID = "11111111-1111-1111-1111-111111111111"
ADAPTIVE_SESSION_ID = "22222222-2222-2222-2222-222222222222"

SAMPLE_OPTIONS = [
    {"label": "2", "text": "2"},
    {"label": "3", "text": "3"},
    {"label": "5", "text": "5"},
    {"label": "23", "text": "23"},
]


async def reset_mcq_tables() -> None:
    """Create MCQ tables with the current schema and clean MCQ data."""
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS mcq_responses CASCADE"))
        await connection.execute(text("DROP TABLE IF EXISTS mcq_options CASCADE"))
        await connection.execute(text("DROP TABLE IF EXISTS mcq_questions CASCADE"))
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
    """Test replacement for get_db that commits like the real dependency."""
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
        difficulty="beginner",
        dimension="Thinking",
    )

    result = await build_submit_response(
        db=db_session,
        question_id=question_in["id"],
        selected_option="5",
        session_id=SESSION_ID,
        question_index=0,
    )

    await db_session.commit()

    assert result["question_id"] == question_in["id"]
    assert result["session_id"] == SESSION_ID
    assert result["question_index"] == 0
    assert result["is_correct"] is True
    assert result["score"] == 1
    assert result["difficulty"] == "beginner"
    assert result["dimension"] == "Thinking"


@pytest.mark.asyncio
async def test_get_question_does_not_expose_correct_answer(db_session):
    question_in = await create_question(
        db=db_session,
        question_text="What is the output of print(2 + 3)?",
        correct_option="5",
        options=SAMPLE_OPTIONS,
        difficulty="beginner",
        dimension="Thinking",
    )

    question = await get_question(db=db_session, question_id=question_in["id"])

    assert question["id"] == question_in["id"]
    assert "question_text" in question
    assert "options" in question
    assert "correct_option" not in question
    assert question["difficulty"] == "beginner"
    assert question["dimension"] == "Thinking"
    assert len(question["options"]) == 4


@pytest.mark.asyncio
async def test_submit_response_is_persisted_without_grading_leak(db_session):
    question_in = await create_question(
        db=db_session,
        question_text="What is the output of print(2 + 3)?",
        correct_option="5",
        options=SAMPLE_OPTIONS,
        difficulty="beginner",
        dimension="Thinking",
    )

    result = await build_submit_response(
        db=db_session,
        question_id=question_in["id"],
        selected_option="5",
        session_id=SESSION_ID,
        question_index=0,
    )

    await db_session.commit()

    saved_result = await db_session.exec(select(MCQResponse))
    saved_responses = saved_result.all()

    assert result["is_correct"] is True
    assert result["score"] == 1

    assert len(saved_responses) == 1
    assert saved_responses[0].question_id == question_in["id"]
    assert saved_responses[0].session_id == SESSION_ID
    assert saved_responses[0].question_index == 0
    assert saved_responses[0].selected_option == "5"

    assert not hasattr(saved_responses[0], "learner_id")
    assert not hasattr(saved_responses[0], "is_correct")
    assert not hasattr(saved_responses[0], "score")


def test_mcq_tool_conforms_to_base_tool():
    tool = MCQTool()

    assert isinstance(tool, BaseTool)
    assert tool.tool_name == "mcq_tool"
    assert tool.tool_description is not None
    assert tool.build_graph() is not None


@pytest.mark.asyncio
async def test_analyze_mcq_session_from_latest_grading_result(db_session):
    latest_grading_result = {
        "response_id": 1,
        "question_id": 1,
        "session_id": SESSION_ID,
        "question_index": 0,
        "difficulty": "beginner",
        "dimension": "Work",
        "is_correct": True,
        "score": 1,
    }

    analysis = await analyze_mcq_session(
        db=db_session,
        session_id=SESSION_ID,
        latest_grading_result=latest_grading_result,
    )

    assert analysis["session_id"] == SESSION_ID
    assert analysis["total_questions"] == 1
    assert analysis["correct_answers"] == 1
    assert analysis["accuracy"] == 1.0
    assert analysis["mastery_level"] == "high"
    assert analysis["difficulty_counts"]["beginner"] == 1
    assert analysis["skill_mastery"]["Work"]["total_questions"] == 1
    assert analysis["skill_mastery"]["Work"]["correct_answers"] == 1
    assert analysis["skill_mastery"]["Work"]["accuracy"] == 1.0
    assert analysis["skill_mastery"]["Work"]["mastery_level"] == "high"
    assert analysis["weakest_skill"] == "Work"


def test_select_next_mcq_plan_uses_weakest_skill():
    analysis = {
        "session_id": SESSION_ID,
        "total_questions": 1,
        "correct_answers": 0,
        "accuracy": 0.0,
        "mastery_level": "low",
        "skill_mastery": {
            "Work": {
                "total_questions": 1,
                "correct_answers": 0,
                "accuracy": 0.0,
                "mastery_level": "low",
                "difficulties": {"intermediate": 1},
            },
        },
        "weakest_skill": "Work",
    }

    plan = select_next_mcq_plan(
        analysis=analysis,
        learner_profile={"level": "beginner"},
        admin_config={
            "allowed_skills": ["Thinking", "Work"],
            "allowed_topics": ["kitchen_1"],
            "max_difficulty": "advanced",
        },
    )

    assert plan["next_skill"] == "Work"
    assert plan["next_dimension"] == "Work"
    assert plan["next_focus"] == "kitchen_1"
    assert plan["next_difficulty"] == "beginner"
    assert plan["mastery_level"] == "low"
    assert plan["learner_profile_used"] is True
    assert plan["admin_config_used"] is True
    assert "reason" in plan


def test_extract_json_from_llm_text_blocks():
    content = [
        {"type": "thinking", "thinking": "I should generate a valid MCQ."},
        {
            "type": "text",
            "text": """
            {
              "question_text": "What is the safest first step before cooking?",
              "difficulty": "beginner",
              "dimension": "Work",
              "correct_option": "A",
              "options": [
                {"label": "A", "text": "Wash your hands"},
                {"label": "B", "text": "Use dirty tools"},
                {"label": "C", "text": "Leave food uncovered"},
                {"label": "D", "text": "Ignore safety steps"}
              ]
            }
            """,
        },
    ]

    result = _extract_json_from_llm_response(content)

    assert result["question_text"] == "What is the safest first step before cooking?"
    assert result["difficulty"] == "beginner"
    assert result["dimension"] == "Work"
    assert result["correct_option"] == "A"
    assert len(result["options"]) == 4


@pytest.mark.asyncio
async def test_adaptive_submit_round_trip_returns_next_plan(monkeypatch):
    """Create a question then submit through adaptive loop without grading leak."""
    await reset_mcq_tables()

    async def fake_generate_and_store_next_mcq(
        db,
        next_plan,
        learner_profile=None,
        admin_config=None,
    ):
        return await create_question(
            db=db,
            question_text="Kitchen 2: What is the safest next step?",
            correct_option="A",
            options=[
                {"label": "A", "text": "Clean the workspace before continuing"},
                {"label": "B", "text": "Ignore the spill and keep cooking"},
                {"label": "C", "text": "Use dirty tools again"},
                {"label": "D", "text": "Leave food uncovered"},
            ],
            difficulty=next_plan["next_difficulty"],
            dimension=next_plan["next_dimension"],
        )

    monkeypatch.setattr(
        "app.features.mcq.loop.generate_and_store_next_mcq",
        fake_generate_and_store_next_mcq,
    )

    app = FastAPI()
    app.include_router(mcq_router)
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        create_response = client.post(
            "/mcq/questions",
            json={
                "question_text": "Kitchen 1: What should you do first before cooking?",
                "difficulty": "beginner",
                "dimension": "Work",
                "correct_option": "A",
                "options": [
                    {"label": "A", "text": "Wash your hands"},
                    {"label": "B", "text": "Leave food uncovered"},
                    {"label": "C", "text": "Use dirty tools"},
                    {"label": "D", "text": "Ignore safety steps"},
                ],
            },
        )

        assert create_response.status_code == 200
        question_id = create_response.json()["id"]

        submit_response = client.post(
            "/mcq/adaptive-submit",
            json={
                "question_id": question_id,
                "session_id": ADAPTIVE_SESSION_ID,
                "question_index": 0,
                "selected_option": "A",
                "learner_profile": {"level": "beginner"},
                "admin_config": {
                    "allowed_skills": ["Thinking", "Work"],
                    "allowed_topics": ["kitchen_1", "kitchen_2"],
                    "max_difficulty": "advanced",
                },
            },
        )

    await engine.dispose()

    assert submit_response.status_code == 200

    body = submit_response.json()

    assert body["received"] is True
    assert body["question_id"] == question_id
    assert "next_plan" in body
    assert "next_question" in body

    next_plan = body["next_plan"]
    next_question = body["next_question"]

    assert next_plan["next_skill"] == "Work"
    assert next_plan["next_dimension"] == "Work"
    assert next_plan["next_focus"] == "kitchen_1"
    assert "next_difficulty" in next_plan
    assert "reason" in next_plan

    assert next_question["question_text"] == "Kitchen 2: What is the safest next step?"
    assert next_question["dimension"] == "Work"
    assert "correct_option" not in next_question

    assert "is_correct" not in body
    assert "score" not in body


@pytest.mark.asyncio
async def test_submit_answer_round_trip():
    """Create a question over HTTP then submit, asserting no grading leak."""
    await reset_mcq_tables()

    app = FastAPI()
    app.include_router(mcq_router)
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        create_response = client.post(
            "/mcq/questions",
            json={
                "question_text": "What is the output of print(2 + 3)?",
                "difficulty": "beginner",
                "dimension": "Work",
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
                "session_id": SESSION_ID,
                "question_index": 0,
                "selected_option": "5",
            },
        )

    await engine.dispose()

    assert submit_response.status_code == 200

    body = submit_response.json()
    assert body["received"] is True
    assert body["question_id"] == question_id
    assert "is_correct" not in body
    assert "score" not in body
