"""LangChain/LangGraph tool surface for the code execution feature."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.database import async_session
from app.features.code import tool
from app.features.code.adaptive_schemas import CodeToolInput, CodeToolOutput
from app.features.code.evaluation_memory import run_adaptive_code_turn_from_input
from app.features.code.schemas import TestCaseDTO


class SandboxTestCaseInput(BaseModel):
    """Single test case for sandbox execution."""

    input: str = Field(description="Executable Python that calls solution, e.g. print(solution('hi'))")
    expected_output: str = Field(description="Expected stripped stdout")
    is_hidden: bool = False
    weight: float = Field(default=1.0, gt=0)


class ExecuteCodeInput(BaseModel):
    """Arguments for the code_execution LangGraph tool."""

    submitted_code: str = Field(
        description="Python source defining a function named `solution`",
        min_length=1,
    )
    test_cases: list[SandboxTestCaseInput] = Field(
        min_length=1,
        description="Weighted test cases to execute inside the E2B sandbox",
    )
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    include_hidden: bool = Field(
        default=True,
        description="When false, only visible test cases are executed (practice runs)",
    )
    keep_sandbox: bool = Field(
        default=False,
        description="Keep the E2B sandbox alive for subsequent runs",
    )
    sandbox_id: str | None = Field(
        default=None,
        description="Optional existing E2B sandbox id to reconnect",
    )


async def _execute_code(**kwargs: Any) -> dict[str, Any]:
    payload = ExecuteCodeInput.model_validate(kwargs)
    dtos = [
        TestCaseDTO(
            id=str(index),
            input=tc.input,
            expected_output=tc.expected_output,
            is_hidden=tc.is_hidden,
            weight=tc.weight,
        )
        for index, tc in enumerate(payload.test_cases, start=1)
    ]
    outcome, results, error, sandbox_id = await tool.execute_submission(
        payload.submitted_code,
        dtos,
        timeout_seconds=payload.timeout_seconds,
        sandbox_id=payload.sandbox_id,
        keep_sandbox=payload.keep_sandbox,
        include_hidden=payload.include_hidden,
    )
    score = tool.compute_weighted_score(dtos, results)
    return {
        "outcome": outcome.value,
        "weighted_score": score,
        "passed_tests": sum(1 for result in results if result.passed),
        "total_tests": len(results),
        "results": [result.model_dump() for result in results],
        "error": error,
        "sandbox_id": sandbox_id,
    }


async def run_adaptive_code_turn(input: CodeToolInput) -> CodeToolOutput:
    """Orchestrate one adaptive turn: E2B → rubric → silent memory card."""
    async with async_session() as db:
        return await run_adaptive_code_turn_from_input(db, input)


def get_langchain_tools() -> list[StructuredTool]:
    """Return LangChain tools for agent graph registration."""
    return [
        StructuredTool.from_function(
            coroutine=_execute_code,
            name="code_execution",
            description=(
                "Execute learner Python in an isolated E2B sandbox against test cases. "
                "Returns per-test results and a weighted pass score."
            ),
            args_schema=ExecuteCodeInput,
        )
    ]
