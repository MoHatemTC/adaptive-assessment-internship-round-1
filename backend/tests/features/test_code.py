"""Tests for the code execution feature."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.code import tool
from app.features.code.schemas import AdaptiveSubmitResponse, ExecutionOutcome
from app.features.code.schemas import TestCaseDTO as CodeTestCaseDTO
from app.features.code.schemas import TestCaseResult as CodeTestCaseResult
from app.shared.schemas.memory import AdaptiveContract, DimensionScore

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "code"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _mock_sandbox_results(raw_results: list[dict], *, error: str | None = None):
    execution = MagicMock()
    if error:
        execution.error = MagicMock(value=error, name="Error")
        execution.logs = MagicMock(stdout=[])
        execution.text = ""
    else:
        execution.error = None
        payload = json.dumps(raw_results)
        execution.logs = MagicMock(stdout=[payload])
        execution.text = payload
    return execution


class TestToolExecution:
    def test_compute_weighted_score_full_pass(self):
        cases = [
            CodeTestCaseDTO(id="1", input="", expected_output="a", weight=1.0),
            CodeTestCaseDTO(id="2", input="", expected_output="b", weight=2.0),
        ]
        results = [
            CodeTestCaseResult(
                test_case_id="1", passed=True, actual_output="a",
                expected_output="a", execution_time_ms=1.0,
            ),
            CodeTestCaseResult(
                test_case_id="2", passed=True, actual_output="b",
                expected_output="b", execution_time_ms=2.0,
            ),
        ]
        assert tool.compute_weighted_score(cases, results) == 1.0

    def test_compute_weighted_score_partial(self):
        cases = [
            CodeTestCaseDTO(id="1", input="", expected_output="a", weight=1.0),
            CodeTestCaseDTO(id="2", input="", expected_output="b", weight=1.0),
        ]
        results = [
            CodeTestCaseResult(
                test_case_id="1", passed=True, actual_output="a",
                expected_output="a", execution_time_ms=1.0,
            ),
            CodeTestCaseResult(
                test_case_id="2", passed=False, actual_output="x",
                expected_output="b", execution_time_ms=1.0,
            ),
        ]
        assert tool.compute_weighted_score(cases, results) == 0.5

    def test_filter_hidden_test_details(self):
        cases = [
            CodeTestCaseDTO(id="1", input="i", expected_output="a", is_hidden=False),
            CodeTestCaseDTO(id="2", input="i", expected_output="secret", is_hidden=True),
        ]
        results = [
            CodeTestCaseResult(
                test_case_id="1", passed=True, actual_output="a",
                expected_output="a", execution_time_ms=1.0,
            ),
            CodeTestCaseResult(
                test_case_id="2", passed=False, actual_output="x",
                expected_output="secret", execution_time_ms=1.0, error="fail",
            ),
        ]
        visible = tool.filter_visible_results(cases, results)
        assert visible[0].expected_output == "a"
        assert visible[1].expected_output == ""

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Without E2B_API_KEY execution routes to the local dev fallback."""
        expected_result = CodeTestCaseResult(
            test_case_id="1",
            passed=True,
            actual_output="a",
            expected_output="a",
            execution_time_ms=1.0,
        )
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "app.features.code.tool._run_locally",
                return_value=(ExecutionOutcome.SUCCESS, [expected_result], None),
            ) as mock_local:
                outcome, results, error = await tool.execute_submission(
                    "def solution(s): return s",
                    [
                        CodeTestCaseDTO(
                            id="1",
                            input="print(solution('a'))",
                            expected_output="a",
                        )
                    ],
                )
        mock_local.assert_called_once()
        assert outcome == ExecutionOutcome.SUCCESS
        assert results == [expected_result]
        assert error is None

    @pytest.mark.asyncio
    async def test_successful_solution_mocked(self):
        fixture = load_fixture("reverse_string.json")
        raw = [
            {
                "test_case_id": str(i),
                "passed": True,
                "actual_output": tc["expected_output"],
                "expected_output": tc["expected_output"],
                "execution_time_ms": 1.0,
                "error": None,
            }
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]
        mock_cmd = MagicMock()
        mock_cmd.exit_code = 0
        mock_cmd.stdout = json.dumps(raw)
        mock_cmd.stderr = ""
        mock_sandbox = MagicMock()
        mock_sandbox.files.write = MagicMock()
        mock_sandbox.commands.run = MagicMock(return_value=mock_cmd)
        mock_sandbox.kill = MagicMock()

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error = await tool.execute_submission(
                    fixture["correct_solution"],
                    [
                        CodeTestCaseDTO(id=str(i), **tc)
                        for i, tc in enumerate(fixture["test_cases"], start=1)
                    ],
                )

        assert outcome == ExecutionOutcome.SUCCESS
        assert error is None
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_syntax_error_mocked(self):
        mock_cmd = MagicMock()
        mock_cmd.exit_code = 1
        mock_cmd.stdout = ""
        mock_cmd.stderr = "SyntaxError: invalid syntax"
        mock_sandbox = MagicMock()
        mock_sandbox.files.write = MagicMock()
        mock_sandbox.commands.run = MagicMock(return_value=mock_cmd)
        mock_sandbox.kill = MagicMock()

        cases = [CodeTestCaseDTO(id="1", input="x", expected_output="y")]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error = await tool.execute_submission(
                    "def solution(s:\n    return s",
                    cases,
                )

        assert outcome == ExecutionOutcome.SANDBOX_ERROR
        assert len(results) == 1
        assert results[0].passed is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_command_timeout_is_bounded_and_reported(self):
        mock_sandbox = MagicMock()
        mock_sandbox.files.write = MagicMock()
        mock_sandbox.commands.run = MagicMock(
            side_effect=TimeoutError("command timed out")
        )
        mock_sandbox.kill = MagicMock()

        cases = [CodeTestCaseDTO(id="1", input="x", expected_output="y")]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error = await tool.execute_submission(
                    "while True: pass",
                    cases,
                    timeout_seconds=1,
                )

        assert outcome == ExecutionOutcome.SANDBOX_TIMEOUT
        assert len(results) == 1
        assert results[0].passed is False
        assert error is not None
        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_cold_start_timeout_is_reported(self):
        cases = [
            CodeTestCaseDTO(
                id="1",
                input="print(solution())",
                expected_output="ok",
            )
        ]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch(
                "e2b_code_interpreter.Sandbox.create",
                side_effect=TimeoutError("sandbox cold start timeout"),
            ):
                outcome, results, error = await tool.execute_submission(
                    "def solution(): return 'ok'",
                    cases,
                    timeout_seconds=1,
                )

        assert outcome == ExecutionOutcome.SANDBOX_TIMEOUT
        assert results
        assert results[0].passed is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_partial_solution_mocked(self):
        fixture = load_fixture("reverse_string.json")
        raw = [
            {
                "test_case_id": "1",
                "passed": False,
                "actual_output": "hello",
                "expected_output": "olleh",
                "execution_time_ms": 1.0,
                "error": None,
            },
            {
                "test_case_id": "2",
                "passed": False,
                "actual_output": "abc",
                "expected_output": "cba",
                "execution_time_ms": 1.0,
                "error": None,
            },
            {
                "test_case_id": "3",
                "passed": True,
                "actual_output": "",
                "expected_output": "",
                "execution_time_ms": 1.0,
                "error": None,
            },
            {
                "test_case_id": "4",
                "passed": True,
                "actual_output": "a",
                "expected_output": "a",
                "execution_time_ms": 1.0,
                "error": None,
            },
        ]
        mock_cmd = MagicMock()
        mock_cmd.exit_code = 0
        mock_cmd.stdout = json.dumps(raw)
        mock_cmd.stderr = ""
        mock_sandbox = MagicMock()
        mock_sandbox.files.write = MagicMock()
        mock_sandbox.commands.run = MagicMock(return_value=mock_cmd)
        mock_sandbox.kill = MagicMock()

        cases = [
            CodeTestCaseDTO(id=str(i), **tc)
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, _ = await tool.execute_submission(
                    fixture["wrong_solution"],
                    cases,
                )

        assert outcome == ExecutionOutcome.SUCCESS
        score = tool.compute_weighted_score(cases, results)
        assert score < tool.PASS_THRESHOLD


class TestCodeBaseTool:
    @pytest.mark.asyncio
    async def test_code_tool_returns_silent_structured_output(self, monkeypatch):
        contract = AdaptiveContract(
            session_id="session-1",
            question_index=1,
            tool_type="coding",
            difficulty="intermediate",
            focus_dimension="thinking",
            stop=False,
            memory_summary="",
            cumulative_scores=DimensionScore(),
        )

        async def _fake_adaptive_submit(db, payload):
            assert payload.session_id == "session-1"
            return AdaptiveSubmitResponse(
                submission_id=42,
                passed=None,
                score=None,
                llm_rubric=None,
                contract=contract,
                next_challenge=None,
            )

        class _Session:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return None

        monkeypatch.setattr(tool, "async_session", lambda: _Session())
        from app.features.code import service

        monkeypatch.setattr(service, "adaptive_submit", _fake_adaptive_submit)

        graph = tool.CodeTool().build_graph()
        result = await graph.ainvoke(
            {
                "challenge_id": 7,
                "session_id": "session-1",
                "assessment_id": "assessment-1",
                "submitted_code": "def solution(): pass",
                "question_index": 0,
                "difficulty": "beginner",
            }
        )

        assert result["received"] is True
        assert result["submission_id"] == 42
        assert result["contract"]["difficulty"] == "intermediate"
        assert "score" not in result
        assert "llm_rubric" not in result


class TestAPI:
    @pytest.mark.asyncio
    async def test_create_challenge_invalid_payload(self, client):
        response = await client.post(
            "/api/v1/code/challenges",
            json={"title": "", "description": "x", "starter_code": "pass", "test_cases": []},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_challenge_not_found(self, client):
        with patch("app.features.code.service.get_challenge") as mock_get:
            from fastapi import HTTPException

            mock_get.side_effect = HTTPException(status_code=404, detail="Challenge not found")
            response = await client.get("/api/v1/code/challenges/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_and_submit_flow_mocked(self, client):
        fixture = load_fixture("reverse_string.json")
        challenge_read = {
            "id": 1,
            "title": fixture["title"],
            "description": fixture["description"],
            "starter_code": fixture["starter_code"],
            "language": "python",
            "time_limit_seconds": 20,
            "test_cases": [
                {
                    "id": i,
                    "input": tc["input"],
                    "expected_output": tc["expected_output"] if not tc["is_hidden"] else None,
                    "is_hidden": tc["is_hidden"],
                    "weight": tc["weight"],
                }
                for i, tc in enumerate(fixture["test_cases"], start=1)
            ],
            "created_at": "2026-06-10T00:00:00Z",
            "updated_at": "2026-06-10T00:00:00Z",
        }
        submission_read = {
            "id": 1,
            "challenge_id": 1,
            "session_id": "test-session",
            "submitted_code": fixture["correct_solution"],
            "status": "completed",
            "score": 1.0,
            "passed": True,
            "scores": [
                {"dimension": "correctness", "score": 1.0, "feedback": "All 4 test cases passed."},
                {"dimension": "efficiency", "score": 1.0, "feedback": "Average execution: 1.0ms"},
            ],
            "test_results": [],
            "total_tests": 4,
            "passed_tests": 4,
            "hidden_tests_count": 2,
            "error": None,
            "created_at": "2026-06-10T00:00:00Z",
            "updated_at": "2026-06-10T00:00:00Z",
        }

        with patch("app.features.code.service.create_challenge", return_value=challenge_read):
            create_resp = await client.post("/api/v1/code/challenges", json=fixture)
        assert create_resp.status_code == 201

        with patch("app.features.code.service.submit_code", return_value=submission_read):
            submit_resp = await client.post(
                "/api/v1/code/submissions",
                json={
                    "challenge_id": 1,
                    "session_id": "test-session",
                    "submitted_code": fixture["correct_solution"],
                },
            )
        assert submit_resp.status_code == 201
        data = submit_resp.json()
        assert data["passed"] is True
        assert data["score"] == 1.0

        with patch("app.features.code.service.get_submission", return_value=submission_read):
            get_resp = await client.get("/api/v1/code/submissions/1")
        assert get_resp.status_code == 200


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("E2B_API_KEY") or os.environ.get("RUN_E2B_INTEGRATION") != "1",
    reason="Set E2B_API_KEY and RUN_E2B_INTEGRATION=1 for live E2B tests",
)
class TestE2BIntegration:
    @pytest.mark.asyncio
    async def test_reverse_string_live(self):
        fixture = load_fixture("reverse_string.json")
        cases = [
            CodeTestCaseDTO(id=str(i), **tc)
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]
        outcome, results, error = await tool.execute_submission(
            fixture["correct_solution"],
            cases,
        )
        assert outcome == ExecutionOutcome.SUCCESS
        assert error is None
        assert all(r.passed for r in results)
