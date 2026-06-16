"""Tests for Layer 3 (analysis) and Layer 4 (adaptation) of the code loop."""

from __future__ import annotations

import uuid

import pytest

from app.core.database import async_session, engine
from app.features.code import adaptation, analysis
from app.sessions.models import MemoryCard, SkillDimensionScore
from app.shared.schemas.memory import DimensionSignals


def _signals_json() -> str:
    return DimensionSignals(
        thinking=True, soft=False, work=True, digital_ai=True, growth=False
    ).model_dump_json()


def _memory_card(session_id: str, question_index: int, passed: bool) -> MemoryCard:
    return MemoryCard(
        session_id=session_id,
        tool_type="coding",
        question_index=question_index,
        difficulty="intermediate",
        evidence_summary="evidence",
        dimension_signals=_signals_json(),
        passed=passed,
    )


@pytest.mark.asyncio
async def test_analyse_session_scores_engaged_dimensions_only():
    session_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(_memory_card(session_id, 0, True))
            db.add(_memory_card(session_id, 1, True))
            await db.flush()

            row = await analysis.analyse_session(db, session_id, question_index=1)

            assert row.tool_type == "coding"
            assert row.question_index == 1
            # Both cards passed -> pass_rate 1.0 -> score 10 on engaged dims.
            assert row.thinking == 10
            assert row.work == 10
            assert row.digital_ai == 10
            # Not engaged by the coding tool.
            assert row.soft is None
            assert row.growth is None

            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compute_adaptive_contract_from_scores():
    session_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                SkillDimensionScore(
                    session_id=session_id,
                    question_index=0,
                    tool_type="coding",
                    thinking=4,
                    work=6,
                    digital_ai=5,
                    soft=None,
                    growth=None,
                )
            )
            await db.flush()

            contract = await adaptation.compute_adaptive_contract(
                db, session_id, assessment_id="assess-1"
            )

            assert contract.session_id == session_id
            assert contract.tool_type == "coding"
            assert contract.question_index == 1  # next after index 0
            assert contract.stop is False
            # avg of 4,6,5 -> 5 -> intermediate.
            assert contract.difficulty == "intermediate"
            # Weakest engaged dimension is thinking (4).
            assert contract.focus_dimension == "thinking"
            assert contract.cumulative_scores.soft is None
            assert contract.cumulative_scores.growth is None
            assert contract.cumulative_scores.thinking == 4

            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compute_adaptive_contract_stops_after_max_questions():
    session_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            for idx in range(5):
                db.add(
                    SkillDimensionScore(
                        session_id=session_id,
                        question_index=idx,
                        tool_type="coding",
                        thinking=9,
                        work=9,
                        digital_ai=9,
                        soft=None,
                        growth=None,
                    )
                )
            await db.flush()

            contract = await adaptation.compute_adaptive_contract(
                db, session_id, assessment_id="assess-1"
            )

            assert contract.stop is True
            assert contract.difficulty == "advanced"  # avg 9 -> advanced

            await db.rollback()
    finally:
        await engine.dispose()


def test_contract_extractor_loader_resolves_adaptation():
    """Layer 4 unblocks the contract extractor's lazy adaptation import."""
    from app.features.contract_extractor.tool import _load_compute_adaptive_contract

    fn = _load_compute_adaptive_contract()
    assert fn is adaptation.compute_adaptive_contract
