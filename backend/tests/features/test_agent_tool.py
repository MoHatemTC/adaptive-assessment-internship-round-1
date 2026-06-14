"""Tests for LangChain agent tool wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.features.code.agent_tool import ExecuteCodeInput, get_langchain_tools
from app.features.code.schemas import ExecutionOutcome
from app.features.code.schemas import TestCaseResult as CodeTestCaseResult
from app.features.registry import discover_langchain_tools


class TestAgentTool:
    def test_get_langchain_tools_exports_code_execution(self):
        tools = get_langchain_tools()
        assert len(tools) == 1
        assert tools[0].name == "code_execution"

    def test_discover_langchain_tools_from_registry(self):
        tools = discover_langchain_tools()
        names = {tool.name for tool in tools}
        assert "code_execution" in names

    @pytest.mark.asyncio
    async def test_execute_code_tool_mocked(self):
        mock_results = [
            CodeTestCaseResult(
                test_case_id="1",
                passed=True,
                actual_output="olleh",
                expected_output="olleh",
                execution_time_ms=1.0,
            )
        ]
        with patch(
            "app.features.code.agent_tool.tool.execute_submission",
            new_callable=AsyncMock,
            return_value=(ExecutionOutcome.SUCCESS, mock_results, None, "sb-1"),
        ):
            tools = get_langchain_tools()
            payload = ExecuteCodeInput(
                submitted_code="def solution(s): return s[::-1]",
                test_cases=[
                    {
                        "input": "print(solution('hello'))",
                        "expected_output": "olleh",
                    }
                ],
            )
            result = await tools[0].ainvoke(payload.model_dump())

        assert result["outcome"] == "success"
        assert result["weighted_score"] == 1.0
        assert result["sandbox_id"] == "sb-1"
