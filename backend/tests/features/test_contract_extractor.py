"""Tests for the contract extractor agent."""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

import app.shared.schemas.memory as shared_memory
from app.core.base_tool import BaseTool
from app.features.contract_extractor import tool as ce_tool
from app.features.contract_extractor.schemas import (
    AdaptiveContract,
    ToolHandoffContext,
)
from app.features.contract_extractor.tool import (
    ContractExtractorTool,
    run_contract_extractor,
)


def _sample_contract(session_id: str = "sess-1") -> AdaptiveContract:
    return AdaptiveContract(
        session_id=session_id,
        question_index=1,
        tool_type="coding",
        difficulty="intermediate",
        focus_dimension="thinking",
        stop=False,
        memory_summary="Strong reasoning, room to grow on efficiency.",
    )


def test_adaptive_contract_is_the_shared_type():
    """The feature re-exports the canonical contract, never a copy of it."""
    assert AdaptiveContract is shared_memory.AdaptiveContract


def test_tool_conforms_to_base_tool():
    tool = ContractExtractorTool()
    assert isinstance(tool, BaseTool)
    assert tool.tool_name == "contract_extractor"
    assert tool.tool_description
    assert tool.build_graph() is not None


def test_handoff_context_validates_tool_type():
    ctx = ToolHandoffContext(
        session_id="sess-1", assessment_id="assess-1", last_tool_type="coding"
    )
    assert ctx.last_tool_type == "coding"

    with pytest.raises(ValueError):
        ToolHandoffContext(
            session_id="sess-1", assessment_id="assess-1", last_tool_type="banana"
        )


@pytest.mark.asyncio
async def test_run_contract_extractor_delegates_to_adaptation(monkeypatch):
    """The graph node delegates to compute_adaptive_contract and surfaces it."""
    captured: dict[str, object] = {}

    async def fake_compute(
        db: AsyncSession, session_id: str, assessment_id: str
    ) -> AdaptiveContract:
        captured["db_is_session"] = isinstance(db, AsyncSession)
        captured["session_id"] = session_id
        captured["assessment_id"] = assessment_id
        return _sample_contract(session_id)

    monkeypatch.setattr(
        ce_tool, "_load_compute_adaptive_contract", lambda: fake_compute
    )

    contract = await run_contract_extractor(
        session_id="sess-1", assessment_id="assess-1", last_tool_type="coding"
    )

    assert contract.session_id == "sess-1"
    assert contract.tool_type == "coding"
    assert contract.difficulty == "intermediate"
    assert contract.question_index == 1
    assert captured["session_id"] == "sess-1"
    assert captured["assessment_id"] == "assess-1"
    assert captured["db_is_session"] is True


@pytest.mark.asyncio
async def test_load_compute_adaptive_contract_errors_clearly(monkeypatch):
    """Before the adaptation layer exists, the loader fails with guidance."""

    def _boom() -> object:
        raise RuntimeError("adaptation layer not available")

    monkeypatch.setattr(ce_tool, "_load_compute_adaptive_contract", _boom)

    with pytest.raises(RuntimeError):
        await run_contract_extractor(
            session_id="sess-1", assessment_id="assess-1", last_tool_type="coding"
        )
