"""E2B sandbox execution — pure execution layer (no DB, no HTTP, no LLM)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.features.code.constants import validate_language
from app.features.code.languages import build_runner_script, get_language_runtime
from app.features.code.schemas import (
    ExecutionOutcome,
    SandboxResultsPayload,
    TestCaseDTO,
    TestCaseResult,
)
from app.features.code.test_invocation import InvocationParseError, normalize_test_invocation

PASS_THRESHOLD = 0.6
RESULTS_SCHEMA_VERSION = 1
RESULTS_PATH = "/home/user/.masaar/results.json"


def _failed_results(
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


def _is_timeout_error(exc: Exception | None = None, message: str | None = None) -> bool:
    text = message or (str(exc) if exc else "")
    lowered = text.lower()
    return "timeout" in lowered or "timed out" in lowered


def _parse_results_file(raw: str) -> list[TestCaseResult]:
    payload = SandboxResultsPayload.model_validate_json(raw)
    if payload.schema_version != RESULTS_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported results schema version: {payload.schema_version}"
        )
    return payload.results


def _resolve_sandbox_id(sandbox: object) -> str | None:
    for attr in ("sandbox_id", "id"):
        value = getattr(sandbox, attr, None)
        if value:
            return str(value)
    return None


def _open_sandbox(
    *,
    api_key: str,
    sandbox_id: str | None,
    timeout_seconds: int,
    template: str | None,
):
    from e2b_code_interpreter import Sandbox

    create_kwargs: dict[str, object] = {"timeout": timeout_seconds + 10, "api_key": api_key}
    if template:
        create_kwargs["template"] = template
    if sandbox_id:
        try:
            return Sandbox.connect(sandbox_id, api_key=api_key)
        except Exception:  # noqa: BLE001 — stale sandbox, create fresh
            pass
    return Sandbox.create(**create_kwargs)


def _run_in_sandbox(
    submitted_code: str,
    test_cases: list[TestCaseDTO],
    timeout_seconds: int,
    *,
    language: str = "python",
    sandbox_id: str | None = None,
    keep_sandbox: bool = False,
    include_hidden: bool = True,
    template: str | None = None,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None, str | None]:
    api_key = os.environ.get("E2B_API_KEY", "")
    if not api_key:
        return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], "E2B_API_KEY not configured", None

    try:
        validated = validate_language(language)
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc), sandbox_id

    runtime = get_language_runtime(validated)
    if not runtime.executable:
        return (
            ExecutionOutcome.SANDBOX_ERROR,
            [],
            f"Language '{validated.value}' is not yet executable in the sandbox.",
            sandbox_id,
        )

    cases = test_cases if include_hidden else [tc for tc in test_cases if not tc.is_hidden]
    if not cases:
        return ExecutionOutcome.SANDBOX_ERROR, [], "No test cases to run", sandbox_id

    sandbox_cases: list[dict] = []
    for tc in cases:
        try:
            invocation = normalize_test_invocation(tc.input, language=validated)
        except InvocationParseError as exc:
            return (
                ExecutionOutcome.SANDBOX_ERROR,
                _failed_results(cases, str(exc)),
                str(exc),
                sandbox_id,
            )
        sandbox_cases.append(
            {
                "id": tc.id,
                "invocation": invocation,
                "expected_output": tc.expected_output,
            }
        )

    runner_script = build_runner_script(
        runtime,
        test_cases_json=json.dumps(sandbox_cases),
    )
    effective_template = template or runtime.e2b_template

    sandbox = None
    active_sandbox_id = sandbox_id
    try:
        sandbox = _open_sandbox(
            api_key=api_key,
            sandbox_id=sandbox_id,
            timeout_seconds=timeout_seconds,
            template=effective_template,
        )
        active_sandbox_id = _resolve_sandbox_id(sandbox) or sandbox_id
        sandbox.files.write(runtime.solution_path, submitted_code)
        sandbox.files.write(runtime.runner_path, runner_script)

        try:
            command_result = sandbox.commands.run(
                runtime.run_command,
                timeout=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 — E2B command failures
            if _is_timeout_error(exc):
                error_msg = str(exc)
                return (
                    ExecutionOutcome.TIMEOUT,
                    _failed_results(cases, error_msg),
                    error_msg,
                    active_sandbox_id if keep_sandbox else None,
                )
            return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], str(exc), None

        if command_result.exit_code != 0:
            error_msg = command_result.stderr or f"Process exited with {command_result.exit_code}"
            if _is_timeout_error(message=error_msg):
                return (
                    ExecutionOutcome.TIMEOUT,
                    _failed_results(cases, error_msg),
                    error_msg,
                    active_sandbox_id if keep_sandbox else None,
                )
            return (
                ExecutionOutcome.SANDBOX_ERROR,
                _failed_results(cases, error_msg),
                error_msg,
                active_sandbox_id if keep_sandbox else None,
            )

        try:
            raw_results = sandbox.files.read(RESULTS_PATH)
        except Exception as exc:  # noqa: BLE001 — missing or unreadable artifact
            error_msg = f"Results file missing or unreadable: {exc}"
            return ExecutionOutcome.SANDBOX_ERROR, [], error_msg, active_sandbox_id if keep_sandbox else None

        try:
            results = _parse_results_file(raw_results)
        except Exception as exc:  # noqa: BLE001 — malformed structured payload
            error_msg = f"Invalid results payload: {exc}"
            return ExecutionOutcome.SANDBOX_ERROR, [], error_msg, active_sandbox_id if keep_sandbox else None

        return ExecutionOutcome.SUCCESS, results, None, active_sandbox_id
    except Exception as exc:  # noqa: BLE001 — surface sandbox failures to caller
        if _is_timeout_error(exc):
            return (
                ExecutionOutcome.TIMEOUT,
                _failed_results(cases, str(exc)),
                str(exc),
                active_sandbox_id if keep_sandbox else None,
            )
        return ExecutionOutcome.SANDBOX_UNAVAILABLE, [], str(exc), None
    finally:
        if sandbox is not None and not keep_sandbox:
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
    sandbox_id: str | None = None,
    keep_sandbox: bool = False,
    include_hidden: bool = True,
    template: str | None = None,
) -> tuple[ExecutionOutcome, list[TestCaseResult], str | None, str | None]:
    """Execute learner code against test cases in an isolated E2B sandbox.

    Returns:
        ``(outcome, per-test results, optional error message, sandbox_id)``.
    """
    try:
        validate_language(language)
    except ValueError as exc:
        return ExecutionOutcome.SANDBOX_ERROR, [], str(exc), None

    if not test_cases:
        return ExecutionOutcome.SANDBOX_ERROR, [], "No test cases provided", None

    return await asyncio.to_thread(
        _run_in_sandbox,
        submitted_code,
        test_cases,
        timeout_seconds,
        language=language,
        sandbox_id=sandbox_id,
        keep_sandbox=keep_sandbox,
        include_hidden=include_hidden,
        template=template,
    )


async def kill_sandbox(sandbox_id: str | None) -> None:
    """Best-effort kill for a persisted sandbox id."""
    if not sandbox_id:
        return
    api_key = os.environ.get("E2B_API_KEY", "")
    if not api_key:
        return

    def _kill() -> None:
        from e2b_code_interpreter import Sandbox

        try:
            sandbox = Sandbox.connect(sandbox_id, api_key=api_key)
            sandbox.kill()
        except Exception:  # noqa: BLE001
            pass

    await asyncio.to_thread(_kill)


def compute_weighted_score(
    test_cases: list[TestCaseDTO],
    results: list[TestCaseResult],
) -> float:
    """Compute a weighted pass ratio in ``[0.0, 1.0]`` from per-test results."""
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
    """Build correctness and efficiency rubric scores for API responses."""
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
    """Strip hidden test expected outputs from learner-visible results."""
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
