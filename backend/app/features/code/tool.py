"""Coding tool execution and examiner-agent wrapper.

The low-level helpers in this module run learner code in E2B. ``CodeTool`` wraps
the adaptive submit flow as a LangGraph ``BaseTool`` for the examiner agent and
returns only a silent acknowledgement plus the next-question contract.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.base_tool import BaseTool
from app.core.database import async_session
from app.features.code.languages import build_runner_script, runner_path, solution_path
from app.features.code.schemas import (
    AdaptiveSubmitRequest,
    CodeToolInput,
    CodeToolOutput,
    ExecutionOutcome,
    TestCaseDTO,
    TestCaseResult,
)

PASS_THRESHOLD = 0.6


class CodeToolState(TypedDict, total=False):
    """LangGraph state for the examiner-agent coding tool."""

    challenge_id: int
    session_id: str
    assessment_id: str
    submitted_code: str
    question_index: int
    difficulty: str
    received: bool
    submission_id: int
    contract: dict[str, Any]


def _timeout_results(test_cases: list[TestCaseDTO], error: str) -> list[TestCaseResult]:
    return [
        TestCaseResult(
            test_case_id=tc.id,
            passed=False,
            actual_output="",
            expected_output=tc.expected_output,
            execution_time_ms=0.0,
            error=error,
        )
        for tc in test_cases
    ]


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc).lower()
    return "timed out" in message or "timeout" in message


def _parse_runner_stdout(
    stdout: str,
    test_cases: list[TestCaseDTO],
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None]:
    if not stdout.strip():
        return ExecutionOutcome.SANDBOX_ERROR, [], "Empty runner output"
    try:
        raw_results: list[dict[str, Any]] = json.loads(stdout)
        results = [TestCaseResult(**r) for r in raw_results]
        return ExecutionOutcome.SUCCESS, results, None
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc)


def _sandbox_error_results(
    test_cases: list[TestCaseDTO],
    error_msg: str,
) -> list[TestCaseResult]:
    return [
        TestCaseResult(
            test_case_id=tc.id,
            passed=False,
            actual_output="",
            expected_output=tc.expected_output,
            execution_time_ms=0.0,
            error=error_msg,
        )
        for tc in test_cases
    ]


def _use_local_sandbox_fallback() -> bool:
    """Allow local execution when cloud sandbox is unavailable (dev only)."""
    return os.environ.get("ENVIRONMENT", "development") == "development"


def _create_e2b_sandbox(timeout_seconds: int, api_key: str):
    """Create an E2B sandbox across SDK v1 (constructor) and v2 (``.create()``)."""
    from e2b_code_interpreter import Sandbox

    sandbox_timeout = timeout_seconds + 10
    if hasattr(Sandbox, "create"):
        return Sandbox.create(timeout=sandbox_timeout, api_key=api_key)
    return Sandbox(timeout=sandbox_timeout, api_key=api_key)


def _run_locally(
    submitted_code: str,
    test_cases: list[TestCaseDTO],
    timeout_seconds: int,
    *,
    language: str,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None]:
    """Execute learner code in a local subprocess (development fallback)."""
    try:
        config, runner_template = build_runner_script(language)
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc)

    tc_json_literal = repr(json.dumps([tc.model_dump() for tc in test_cases]))
    runner_script = runner_template.replace("__TEST_CASES_JSON__", tc_json_literal)
    if config.id == "javascript":
        runner_script = runner_script.replace(
            'require("/home/user/solution.js")',
            'require("./solution.js")',
        )

    command = (
        ["python", "runner.py"]
        if config.id == "python"
        else ["node", "runner.js"]
    )

    try:
        with tempfile.TemporaryDirectory(prefix="masaar-code-") as tmpdir:
            workdir = Path(tmpdir)
            solution_file = workdir / config.solution_filename
            runner_file = workdir / config.runner_filename
            solution_file.write_text(submitted_code, encoding="utf-8")
            runner_file.write_text(runner_script, encoding="utf-8")

            completed = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=max(1, timeout_seconds),
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        message = str(exc) or "Sandbox execution timed out"
        return (
            ExecutionOutcome.SANDBOX_TIMEOUT,
            _timeout_results(test_cases, message),
            message,
        )
    except OSError as exc:
        return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], str(exc)

    if completed.returncode != 0:
        error_msg = completed.stderr.strip() or f"Process exited with {completed.returncode}"
        return (
            ExecutionOutcome.SANDBOX_ERROR,
            _sandbox_error_results(test_cases, error_msg),
            error_msg,
        )

    return _parse_runner_stdout(completed.stdout, test_cases)


def _run_in_e2b(
    submitted_code: str,
    test_cases: list[TestCaseDTO],
    timeout_seconds: int,
    *,
    language: str,
    api_key: str,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None]:
    try:
        config, runner_template = build_runner_script(language)
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc)

    tc_json_literal = repr(json.dumps([tc.model_dump() for tc in test_cases]))
    runner_script = runner_template.replace("__TEST_CASES_JSON__", tc_json_literal)

    sandbox = None
    try:
        sandbox = _create_e2b_sandbox(timeout_seconds, api_key)
        sandbox.files.write(solution_path(config), submitted_code)
        sandbox.files.write(runner_path(config), runner_script)

        command_result = sandbox.commands.run(
            config.run_command,
            timeout=timeout_seconds,
        )

        if command_result.exit_code != 0:
            error_msg = (
                command_result.stderr
                or f"Process exited with {command_result.exit_code}"
            )
            return (
                ExecutionOutcome.SANDBOX_ERROR,
                _sandbox_error_results(test_cases, error_msg),
                error_msg,
            )

        return _parse_runner_stdout((command_result.stdout or "").strip(), test_cases)
    except TimeoutError as exc:
        message = str(exc) or "Sandbox execution timed out"
        return (
            ExecutionOutcome.SANDBOX_TIMEOUT,
            _timeout_results(test_cases, message),
            message,
        )
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc)
    except Exception as exc:  # noqa: BLE001 — surface sandbox failures to caller
        if _is_timeout_error(exc):
            message = str(exc) or "Sandbox execution timed out"
            return (
                ExecutionOutcome.SANDBOX_TIMEOUT,
                _timeout_results(test_cases, message),
                message,
            )
        return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], str(exc)
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass


def _run_in_sandbox(
    submitted_code: str,
    test_cases: list[TestCaseDTO],
    timeout_seconds: int,
    *,
    language: str,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None]:
    api_key = os.environ.get("E2B_API_KEY", "")
    if not api_key:
        return _run_locally(
            submitted_code,
            test_cases,
            timeout_seconds,
            language=language,
        )

    try:
        outcome, results, error = _run_in_e2b(
            submitted_code,
            test_cases,
            timeout_seconds,
            language=language,
            api_key=api_key,
        )
        if (
            outcome == ExecutionOutcome.SANDBOX_UNAVAILABLE
            and _use_local_sandbox_fallback()
        ):
            return _run_locally(
                submitted_code,
                test_cases,
                timeout_seconds,
                language=language,
            )
        return outcome, results, error
    except ImportError:
        return _run_locally(
            submitted_code,
            test_cases,
            timeout_seconds,
            language=language,
        )
    except AttributeError:
        if _use_local_sandbox_fallback():
            return _run_locally(
                submitted_code,
                test_cases,
                timeout_seconds,
                language=language,
            )
        raise


async def execute_submission(
    submitted_code: str,
    test_cases: list[TestCaseDTO],
    *,
    language: str = "python",
    timeout_seconds: int = 20,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None]:
    """Execute learner code against test cases in an E2B sandbox."""
    if not test_cases:
        return ExecutionOutcome.SANDBOX_ERROR, [], "No test cases provided"

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _run_in_sandbox,
                submitted_code,
                test_cases,
                timeout_seconds,
                language=language,
            ),
            timeout=max(1, timeout_seconds) + 15,
        )
    except TimeoutError as exc:
        message = str(exc) or "Sandbox execution timed out"
        return (
            ExecutionOutcome.SANDBOX_TIMEOUT,
            _timeout_results(test_cases, message),
            message,
        )


def compute_weighted_score(
    test_cases: list[TestCaseDTO],
    results: list[TestCaseResult],
) -> float:
    if not test_cases:
        return 0.0
    total_weight = sum(tc.weight for tc in test_cases)
    if total_weight <= 0:
        return 0.0
    passed_weight = sum(
        tc.weight
        for tc, result in zip(test_cases, results, strict=False)
        if result.passed
    )
    return round(passed_weight / total_weight, 3)


def build_rubric_scores(
    results: list[TestCaseResult],
    overall_score: float,
) -> list[dict[str, Any]]:
    avg_exec_ms = (
        sum(r.execution_time_ms for r in results) / len(results) if results else 0.0
    )
    efficiency_score = max(0.0, round(1.0 - (avg_exec_ms / 5000), 3))
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    if total == 0:
        correctness_feedback = "Sandbox execution failed before tests could run."
    elif passed == total:
        correctness_feedback = f"All {total} test cases passed."
    else:
        failed = next(r for r in results if not r.passed)
        correctness_feedback = (
            f"{passed}/{total} tests passed. First failure: "
            f"Expected '{failed.expected_output}', got '{failed.actual_output}'"
        )
        if failed.error:
            correctness_feedback = (
                f"{passed}/{total} tests passed. Runtime error: {failed.error[:120]}"
            )

    return [
        {
            "dimension": "correctness",
            "score": overall_score,
            "feedback": correctness_feedback,
        },
        {
            "dimension": "efficiency",
            "score": efficiency_score,
            "feedback": f"Average execution: {avg_exec_ms:.1f}ms",
        },
    ]


def filter_visible_results(
    test_cases: list[TestCaseDTO],
    results: list[TestCaseResult],
) -> list[TestCaseResult]:
    visible: list[TestCaseResult] = []
    for tc, result in zip(test_cases, results, strict=False):
        if tc.is_hidden:
            visible.append(
                TestCaseResult(
                    test_case_id=result.test_case_id,
                    passed=result.passed,
                    actual_output=result.actual_output if result.passed else "",
                    expected_output="",
                    execution_time_ms=result.execution_time_ms,
                    error=result.error if not result.passed else None,
                )
            )
        else:
            visible.append(result)
    return visible


class CodeTool(BaseTool):
    """Examiner-agent tool for adaptive coding submissions."""

    @property
    def tool_name(self) -> str:
        return "code_tool"

    @property
    def tool_description(self) -> str:
        return (
            "Executes a coding answer in the E2B sandbox, silently persists grading "
            "and memory records, and returns the next adaptive contract."
        )

    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(CodeToolState)
        graph.add_node("submit_code", self._submit_code)
        graph.set_entry_point("submit_code")
        graph.add_edge("submit_code", END)
        return graph.compile()

    async def _submit_code(self, state: CodeToolState) -> dict[str, Any]:
        from app.features.code import service

        input_state = CodeToolInput.model_validate(state)
        async with async_session() as db:
            response = await service.adaptive_submit(
                db,
                AdaptiveSubmitRequest(**input_state.model_dump()),
            )

        output = CodeToolOutput(
            received=True,
            submission_id=response.submission_id,
            contract=response.contract,
        )
        return output.model_dump()
