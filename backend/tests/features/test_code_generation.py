"""Tests for LLM challenge generation."""

from __future__ import annotations

import uuid

import pytest

from app.features.code import generation, service
from app.features.code.generation import GeneratedChallengeSpec, GeneratedTestCase
from app.features.code.schemas import GenerateChallengeRequest
from app.shared.schemas.memory import AdaptiveContract, DimensionScore


def _fake_spec() -> GeneratedChallengeSpec:
    return GeneratedChallengeSpec(
        title="Count Vowels",
        description="Return how many vowels appear in the input string.",
        starter_code="def solution(s: str) -> int:\n    # TODO\n    return 0\n",
        test_cases=[
            GeneratedTestCase(
                input="print(solution('hello'))",
                expected_output="2",
                is_hidden=False,
            ),
            GeneratedTestCase(
                input="print(solution('xyz'))",
                expected_output="0",
                is_hidden=False,
            ),
            GeneratedTestCase(
                input="print(solution('aeiou'))",
                expected_output="5",
                is_hidden=True,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_generate_challenge_persists_llm_spec(monkeypatch):
    async def _fake_generate(**kwargs) -> GeneratedChallengeSpec:
        return _fake_spec()

    monkeypatch.setattr(generation, "generate_challenge_spec", _fake_generate)
    session_id = str(uuid.uuid4())

    from app.core.database import async_session, engine

    try:
        async with async_session() as db:
            result = await service.generate_challenge(
                db,
                GenerateChallengeRequest(
                    session_id=session_id,
                    assessment_id="assess-gen",
                ),
            )
            assert result.challenge.title == "Count Vowels"
            assert result.challenge.starter_code.startswith("def solution")
            assert len(result.challenge.test_cases) == 3
            assert result.contract.question_index == 0
            assert result.contract.difficulty == "beginner"
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generate_challenge_rejects_stop_contract():
    from app.core.database import async_session, engine

    contract = AdaptiveContract(
        session_id=str(uuid.uuid4()),
        question_index=5,
        tool_type="coding",
        difficulty="advanced",
        focus_dimension="thinking",
        stop=True,
        memory_summary="Done.",
        cumulative_scores=DimensionScore(),
    )
    try:
        async with async_session() as db:
            with pytest.raises(Exception) as exc:
                await service.generate_challenge(
                    db,
                    GenerateChallengeRequest(
                        session_id=contract.session_id,
                        assessment_id="assess-gen",
                        contract=contract,
                    ),
                )
            assert exc.value.status_code == 422
            await db.rollback()
    finally:
        await engine.dispose()
