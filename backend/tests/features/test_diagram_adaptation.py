from unittest.mock import AsyncMock, patch

import pytest

from app.features.diagram.loop import run_diagram_loop


@pytest.mark.asyncio
async def test_loop_not_complete():
    with patch(
        "app.features.diagram.loop.evaluate_diagram_answer",
        new=AsyncMock(return_value={"memory_card": None, "memory_summary": "s"}),
    ):
        result = await run_diagram_loop("s1", 0, 1, 2, AsyncMock())
    assert result["is_complete"] is False


@pytest.mark.asyncio
async def test_loop_complete():
    with patch(
        "app.features.diagram.loop.evaluate_diagram_answer",
        new=AsyncMock(return_value={"memory_card": None, "memory_summary": "s"}),
    ):
        result = await run_diagram_loop("s1", 1, 1, 2, AsyncMock())
    assert result["is_complete"] is True


@pytest.mark.asyncio
async def test_loop_forwards_summary():
    with patch(
        "app.features.diagram.loop.evaluate_diagram_answer",
        new=AsyncMock(return_value={"memory_card": None, "memory_summary": "forwarded"}),
    ):
        result = await run_diagram_loop("s1", 0, 1, 2, AsyncMock())
    assert result["memory_summary"] == "forwarded"
