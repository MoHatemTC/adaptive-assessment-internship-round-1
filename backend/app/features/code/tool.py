"""E2B sandbox execution — pure execution layer (no DB, no HTTP, no LLM)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.features.code.languages import build_runner_script, runner_path, solution_path
from app.features.code.schemas import ExecutionOutcome, TestCaseDTO, TestCaseResult

PASS_THRESHOLD = 0.6


def _run_in_sandbox(
    submitted_code: str,
    test_cases: list[TestCaseDTO],
    timeout_seconds: int,
    *,
    language: str,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None]:
    from e2b_code_interpreter import Sandbox

    api_key = os.environ.get("E2B_API_KEY", "")
    if not api_key:
        return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], "E2B_API_KEY not configured"

    try:
        config, runner_template = build_runner_script(language)
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc)

    tc_json_literal = repr(json.dumps([tc.model_dump() for tc in test_cases]))
    runner_script = runner_template.replace("__TEST_CASES_JSON__", tc_json_literal)

    sandbox = None
    try:
        sandbox = Sandbox.create(timeout=timeout_seconds + 10, api_key=api_key)
        sandbox.files.write(solution_path(config), submitted_code)
        sandbox.files.write(runner_path(config), runner_script)

        command_result = sandbox.commands.run(
            config.run_command,
            timeout=timeout_seconds,
        )

        if command_result.exit_code != 0:
            error_msg = command_result.stderr or f"Process exited with {command_result.exit_code}"
            results = [
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
            return ExecutionOutcome.SANDBOX_ERROR, results, error_msg

        stdout = (command_result.stdout or "").strip()
        if not stdout:
            return ExecutionOutcome.SANDBOX_ERROR, [], "Empty runner output"

        raw_results: list[dict[str, Any]] = json.loads(stdout)
        results = [TestCaseResult(**r) for r in raw_results]
        return ExecutionOutcome.SUCCESS, results, None
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc)
    except Exception as exc:  # noqa: BLE001 — surface sandbox failures to caller
        return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], str(exc)
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass


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

    return await asyncio.to_thread(
        _run_in_sandbox,
        submitted_code,
        test_cases,
        timeout_seconds,
        language=language,
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
        tc.weight for tc, result in zip(test_cases, results, strict=False) if result.passed
    )
    return round(passed_weight / total_weight, 3)


def build_rubric_scores(results: list[TestCaseResult], overall_score: float) -> list[dict[str, Any]]:
    avg_exec_ms = (
        sum(r.execution_time_ms for r in results) / len(results) if results else 0.0
    )
    efficiency_score = max(0.0, round(1.0 - (avg_exec_ms / 5000), 3))
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    if passed == total:
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
