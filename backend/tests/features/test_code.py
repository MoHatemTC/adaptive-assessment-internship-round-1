"""Tests for the code execution feature."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from app.evaluation.schemas import CodeEvaluationContext, EvaluationResult
from app.features.code import tool
from app.features.code.models import CodeSubmission, SubmissionStatus
from app.features.code.schemas import ExecutionOutcome, SandboxResultsPayload
from app.features.code.schemas import TestCaseDTO as CodeTestCaseDTO
from app.features.code.schemas import TestCaseResult as CodeTestCaseResult

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "code"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _results_payload(raw_results: list[dict]) -> str:
    return SandboxResultsPayload(
        schema_version=tool.RESULTS_SCHEMA_VERSION,
        results=[CodeTestCaseResult(**r) for r in raw_results],
    ).model_dump_json()


def _mock_sandbox_with_results(
    raw_results: list[dict],
    *,
    exit_code: int = 0,
    stderr: str = "",
    run_side_effect: Exception | None = None,
    read_side_effect: Exception | None = None,
) -> MagicMock:
    mock_cmd = MagicMock()
    mock_cmd.exit_code = exit_code
    mock_cmd.stdout = ""
    mock_cmd.stderr = stderr

    mock_sandbox = MagicMock()
    mock_sandbox.files.write = MagicMock()
    if read_side_effect is not None:
        mock_sandbox.files.read = MagicMock(side_effect=read_side_effect)
    else:
        mock_sandbox.files.read = MagicMock(return_value=_results_payload(raw_results))

    if run_side_effect is not None:
        mock_sandbox.commands.run = MagicMock(side_effect=run_side_effect)
    else:
        mock_sandbox.commands.run = MagicMock(return_value=mock_cmd)
    mock_sandbox.kill = MagicMock()
    return mock_sandbox


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
        with patch.dict(os.environ, {}, clear=True):
            outcome, results, error, _sid = await tool.execute_submission(
                "def solution(s): return s",
                [CodeTestCaseDTO(id="1", input="print(solution('a'))", expected_output="a")],
            )
        assert outcome == ExecutionOutcome.SANDBOX_UNAVAILABLE
        assert results == []
        assert error is not None

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
        mock_sandbox = _mock_sandbox_with_results(raw)
        cases = [
            CodeTestCaseDTO(id=str(i), **tc)
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error, sandbox_id = await tool.execute_submission(
                    fixture["correct_solution"],
                    cases,
                    timeout_seconds=15,
                )

        assert outcome == ExecutionOutcome.SUCCESS
        assert error is None
        assert all(r.passed for r in results)
        mock_sandbox.files.write.assert_called()
        mock_sandbox.files.read.assert_called_once_with(tool.RESULTS_PATH)
        mock_sandbox.commands.run.assert_called_once()
        _, kwargs = mock_sandbox.commands.run.call_args
        assert kwargs["timeout"] == 15
        mock_sandbox.kill.assert_called_once()
        assert sandbox_id is not None

    @pytest.mark.asyncio
    async def test_keep_sandbox_skips_kill(self):
        mock_sandbox = _mock_sandbox_with_results(
            [
                {
                    "test_case_id": "1",
                    "passed": True,
                    "actual_output": "a",
                    "expected_output": "a",
                    "execution_time_ms": 1.0,
                    "error": None,
                }
            ]
        )
        mock_sandbox.sandbox_id = "sb-keep"
        cases = [
            CodeTestCaseDTO(
                id="1",
                input="print(solution('x'))",
                expected_output="a",
                is_hidden=False,
            )
        ]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                _, _, _, sid = await tool.execute_submission(
                    "def solution(s): return s",
                    cases,
                    keep_sandbox=True,
                )
        assert sid == "sb-keep"
        mock_sandbox.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_syntax_error_mocked(self):
        mock_sandbox = _mock_sandbox_with_results(
            [],
            exit_code=1,
            stderr="SyntaxError: invalid syntax",
        )
        cases = [CodeTestCaseDTO(id="1", input="print(solution('x'))", expected_output="y")]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error, _ = await tool.execute_submission(
                    "def solution(s:\n    return s",
                    cases,
                )

        assert outcome == ExecutionOutcome.SANDBOX_ERROR
        assert len(results) == 1
        assert results[0].passed is False
        assert error is not None
        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        cases = [CodeTestCaseDTO(id="1", input="print(solution('x'))", expected_output="y")]
        mock_sandbox = _mock_sandbox_with_results(
            [],
            run_side_effect=TimeoutError("command timed out after 5s"),
        )
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error, _ = await tool.execute_submission(
                    "def solution(s): return s",
                    cases,
                    timeout_seconds=5,
                )

        assert outcome == ExecutionOutcome.TIMEOUT
        assert len(results) == 1
        assert results[0].passed is False
        assert error is not None
        mock_sandbox.commands.run.assert_called_once()
        _, kwargs = mock_sandbox.commands.run.call_args
        assert kwargs["timeout"] == 5
        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_results_file(self):
        cases = [CodeTestCaseDTO(id="1", input="print(solution('x'))", expected_output="y")]
        mock_sandbox = _mock_sandbox_with_results(
            [],
            read_side_effect=FileNotFoundError("results.json not found"),
        )
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, error, _ = await tool.execute_submission(
                    "def solution(s): return s",
                    cases,
                )

        assert outcome == ExecutionOutcome.SANDBOX_ERROR
        assert results == []
        assert error is not None
        mock_sandbox.files.read.assert_called_once_with(tool.RESULTS_PATH)

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
        mock_sandbox = _mock_sandbox_with_results(raw)
        cases = [
            CodeTestCaseDTO(id=str(i), **tc)
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
                outcome, results, _, _ = await tool.execute_submission(
                    fixture["wrong_solution"],
                    cases,
                )

        assert outcome == ExecutionOutcome.SUCCESS
        score = tool.compute_weighted_score(cases, results)
        assert score < tool.PASS_THRESHOLD


class TestEvaluatorIntegration:
    @pytest.mark.asyncio
    async def test_submit_uses_evaluator(self):
        from app.evaluation.evaluator import _deterministic_fallback
        from app.evaluation.defaults import DEFAULT_EVALUATION_CONFIG
        from app.evaluation.schemas import CodeEvaluationContext

        ctx = CodeEvaluationContext(
            challenge_id=1,
            title="T",
            description="D",
            submitted_code="pass",
            correctness_ratio=1.0,
            performance_ratio=0.9,
            passed_tests=2,
            total_tests=2,
        )
        result = _deterministic_fallback(ctx, DEFAULT_EVALUATION_CONFIG)
        assert isinstance(result, EvaluationResult)
        assert result.breakdown.correctness >= 0


class TestSessionSubmissionsAPI:
    @pytest.mark.asyncio
    async def test_list_session_submissions_mocked(self, client):
        from app.features.code.schemas import SessionSubmissionsRead, SubmissionRead
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_payload = SessionSubmissionsRead(
            session_id="assess-mock123",
            submissions=[
                SubmissionRead(
                    id=1,
                    challenge_id=42,
                    session_id="assess-mock123",
                    submitted_code="pass",
                    status="completed",
                    score=1.0,
                    passed=True,
                    created_at=now,
                    updated_at=now,
                )
            ],
        )
        with patch(
            "app.features.code.service.list_session_submissions",
            new_callable=AsyncMock,
            return_value=mock_payload,
        ):
            response = await client.get("/api/v1/code/sessions/assess-mock123/submissions")
        assert response.status_code == 200
        assert len(response.json()["submissions"]) == 1


class TestTimedSessionAPI:
    @pytest.mark.asyncio
    async def test_start_session_mocked(self, client):
        from app.features.code.schemas import SessionChallengeRead, SessionRead
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_session = SessionRead(
            session_id="assess-mock123",
            status="active",
            total_remaining_seconds=3600,
            expires_at=now,
            generation_notes="mocked session",
            challenges=[
                SessionChallengeRead(
                    attempt_id=1,
                    challenge_id=42,
                    position=1,
                    challenge_count=1,
                    title="Mock Challenge",
                    difficulty="intermediate",
                    category="strings",
                    description="Desc",
                    requirements=[],
                    evaluation_criteria=["correctness"],
                    max_score=100,
                    estimated_duration="20 minutes",
                    candidate_time_seconds=1200,
                    remaining_seconds=1200,
                    starter_code="def solution(s): pass",
                    language="python",
                    time_limit_seconds=30,
                    test_cases=[],
                )
            ],
        )
        with patch(
            "app.features.code.service.start_assessment_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            response = await client.post(
                "/api/v1/code/sessions",
                json={
                    "name": "Alex",
                    "skills": ["Python"],
                    "experience_level": "intermediate",
                },
            )
        assert response.status_code == 201
        assert response.json()["session_id"] == "assess-mock123"

    @pytest.mark.asyncio
    async def test_run_code_mocked(self, client):
        from app.features.code.schemas import ExecutionOutcome, RunRead

        mock_run = RunRead(
            outcome=ExecutionOutcome.SUCCESS,
            passed_tests=1,
            total_tests=1,
            remaining_seconds=900,
            run_count=1,
        )
        with patch(
            "app.features.code.service.run_code",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            response = await client.post(
                "/api/v1/code/runs",
                json={
                    "session_id": "assess-mock123",
                    "challenge_id": 42,
                    "submitted_code": "def solution(s): return s[::-1]",
                },
            )
        assert response.status_code == 201
        assert response.json()["run_count"] == 1

    @pytest.mark.asyncio
    async def test_session_submit_routes_to_graded_flow(self, client):
        submission_read = {
            "id": 2,
            "challenge_id": 42,
            "session_id": "assess-mock123",
            "submitted_code": "code",
            "status": "completed",
            "score": 1.0,
            "passed": True,
            "scores": [],
            "test_results": [],
            "total_tests": 2,
            "passed_tests": 2,
            "hidden_tests_count": 1,
            "error": None,
            "created_at": "2026-06-10T00:00:00Z",
            "updated_at": "2026-06-10T00:00:00Z",
        }
        with patch(
            "app.features.code.service.submit_session_challenge",
            new_callable=AsyncMock,
            return_value=submission_read,
        ) as mock_submit:
            response = await client.post(
                "/api/v1/code/submissions",
                json={
                    "challenge_id": 42,
                    "session_id": "assess-mock123",
                    "submitted_code": "def solution(s): return s[::-1]",
                },
            )
        assert response.status_code == 201
        mock_submit.assert_awaited_once()


class TestChallengeGenerationAPI:
    @pytest.mark.asyncio
    async def test_generate_challenges_mocked(self, client):
        with patch(
            "app.features.code.service.generate_challenges_from_profile",
            new_callable=AsyncMock,
        ) as mock_gen:
            from app.features.code.schemas import GenerateChallengesResponse, GeneratedChallengeRead

            mock_gen.return_value = GenerateChallengesResponse(
                challenges=[
                    GeneratedChallengeRead(
                        challenge_id=99,
                        title="Generated Challenge",
                        difficulty="intermediate",
                        category="strings",
                        description="Reverse a string.",
                        requirements=["Use Python"],
                        evaluation_criteria=["correctness"],
                        max_score=100,
                        estimated_duration="20 minutes",
                        starter_code="def solution(s): pass",
                        language="python",
                        time_limit_seconds=20,
                        test_cases=[],
                    )
                ],
                generation_notes="mocked",
            )
            response = await client.post(
                "/api/v1/code/challenges/generate",
                json={
                    "name": "Alex",
                    "skills": ["Python"],
                    "experience_level": "intermediate",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert len(data["challenges"]) == 1
        assert data["challenges"][0]["challenge_id"] == 99


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


class TestServiceRoundTrip:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_submit_persists_grading_metadata(self, db_session):
        from app.evaluation.defaults import DEFAULT_EVALUATION_CONFIG
        from app.evaluation.evaluator import _deterministic_fallback
        from app.features.code import service
        from app.features.code.schemas import ChallengeCreate, SubmissionCreate

        fixture = load_fixture("reverse_string.json")
        create_payload = ChallengeCreate(
            title=fixture["title"],
            description=fixture["description"],
            starter_code=fixture["starter_code"],
            language="python",
            time_limit_seconds=12,
            test_cases=fixture["test_cases"],
        )

        mock_results = [
            CodeTestCaseResult(
                test_case_id=str(i),
                passed=True,
                actual_output=tc["expected_output"],
                expected_output=tc["expected_output"],
                execution_time_ms=1.0,
            )
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]

        async def _mock_execute(_code, _cases, **kwargs):
            assert kwargs["timeout_seconds"] == 12
            return ExecutionOutcome.SUCCESS, mock_results, None, None

        with patch("app.features.code.tool.execute_submission", side_effect=_mock_execute):
            with patch(
                "app.features.code.service.evaluate_code_submission",
                new_callable=AsyncMock,
            ) as mock_eval:
                mock_eval.return_value = _deterministic_fallback(
                    CodeEvaluationContext(
                        challenge_id=1,
                        title=fixture["title"],
                        description=fixture["description"],
                        submitted_code=fixture["correct_solution"],
                        correctness_ratio=1.0,
                        performance_ratio=0.95,
                        passed_tests=4,
                        total_tests=4,
                    ),
                    DEFAULT_EVALUATION_CONFIG,
                )
                challenge = await service.create_challenge(db_session, create_payload)
                submission = await service.submit_code(
                    db_session,
                    SubmissionCreate(
                        challenge_id=challenge.id,
                        session_id="db-roundtrip",
                        submitted_code=fixture["correct_solution"],
                    ),
                )

        assert submission.passed is True
        assert submission.score is not None and submission.score >= 0.6
        assert submission.evaluation_score is not None
        assert submission.status == SubmissionStatus.COMPLETED

        result = await db_session.exec(
            select(CodeSubmission).where(CodeSubmission.id == submission.id)
        )
        stored = result.one()
        assert stored.passed is True
        assert stored.score is not None and stored.score >= 0.6
        assert stored.grading_metadata is not None

        loaded = await service.get_submission(db_session, submission.id)
        assert loaded.passed is True
        assert loaded.evaluation_score is not None


class TestSessionRoundTrip:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_run_and_submit(self, db_session):
        from app.challenges.schemas import UserProfile
        from app.evaluation.defaults import DEFAULT_EVALUATION_CONFIG
        from app.evaluation.evaluator import _deterministic_fallback
        from app.features.code import service
        from app.features.code.models import CodeAssessmentSession, SessionStatus
        from app.features.code.schemas import RunCreate

        fixture = load_fixture("reverse_string.json")
        profile = UserProfile(name="Session Tester", skills=["Python"], experience_level="beginner")

        visible_results = [
            CodeTestCaseResult(
                test_case_id=str(i),
                passed=True,
                actual_output=tc["expected_output"],
                expected_output=tc["expected_output"],
                execution_time_ms=1.0,
            )
            for i, tc in enumerate(fixture["test_cases"], start=1)
            if not tc["is_hidden"]
        ]
        full_results = [
            CodeTestCaseResult(
                test_case_id=str(i),
                passed=True,
                actual_output=tc["expected_output"],
                expected_output=tc["expected_output"],
                execution_time_ms=1.0,
            )
            for i, tc in enumerate(fixture["test_cases"], start=1)
        ]

        async def _mock_execute(_code, _cases, **kwargs):
            if kwargs.get("include_hidden") is False:
                return ExecutionOutcome.SUCCESS, visible_results, None, "sb-test"
            return ExecutionOutcome.SUCCESS, full_results, None, None

        from app.challenges.schemas import PlatformChallengeConfig

        single_config = PlatformChallengeConfig()
        single_config.challenge.challenges_per_candidate = 1

        with patch("app.challenges.generator.get_settings") as mock_settings:
            mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = ""
            with patch(
                "app.features.code.service.get_platform_challenge_config",
                new_callable=AsyncMock,
                return_value=single_config,
            ):
                with patch("app.features.code.tool.execute_submission", side_effect=_mock_execute):
                    with patch(
                        "app.features.code.service.evaluate_code_submission",
                        new_callable=AsyncMock,
                    ) as mock_eval:
                        mock_eval.return_value = _deterministic_fallback(
                            CodeEvaluationContext(
                                challenge_id=1,
                                title=fixture["title"],
                                description=fixture["description"],
                                submitted_code=fixture["correct_solution"],
                                correctness_ratio=1.0,
                                performance_ratio=0.9,
                                passed_tests=4,
                                total_tests=4,
                            ),
                            DEFAULT_EVALUATION_CONFIG,
                        )
                        session = await service.start_assessment_session(db_session, profile)

        assert session.session_id.startswith("assess-")
        challenge_id = session.challenges[0].challenge_id

        with patch("app.features.code.tool.execute_submission", side_effect=_mock_execute):
            run = await service.run_code(
                db_session,
                RunCreate(
                    session_id=session.session_id,
                    challenge_id=challenge_id,
                    submitted_code=fixture["correct_solution"],
                ),
            )

        assert run.run_count == 1
        assert run.passed_tests == len(visible_results)

        with patch("app.features.code.tool.execute_submission", side_effect=_mock_execute):
            with patch(
                "app.features.code.service.evaluate_code_submission",
                new_callable=AsyncMock,
            ) as mock_eval:
                mock_eval.return_value = _deterministic_fallback(
                    CodeEvaluationContext(
                        challenge_id=challenge_id,
                        title=fixture["title"],
                        description=fixture["description"],
                        submitted_code=fixture["correct_solution"],
                        correctness_ratio=1.0,
                        performance_ratio=0.9,
                        passed_tests=4,
                        total_tests=4,
                    ),
                    DEFAULT_EVALUATION_CONFIG,
                )
                submission = await service.submit_session_challenge(
                    db_session,
                    RunCreate(
                        session_id=session.session_id,
                        challenge_id=challenge_id,
                        submitted_code=fixture["correct_solution"],
                    ),
                )

        assert submission.passed is True

        result = await db_session.exec(
            select(CodeAssessmentSession).where(
                CodeAssessmentSession.session_id == session.session_id
            )
        )
        stored_session = result.one()
        assert stored_session.status == SessionStatus.ACTIVE

        completion = await service.complete_assessment_session(
            db_session,
            session.session_id,
            confirm_unsubmitted=False,
        )
        assert completion.status == "completed"

        result = await db_session.exec(
            select(CodeAssessmentSession).where(
                CodeAssessmentSession.session_id == session.session_id
            )
        )
        stored_session = result.one()
        assert stored_session.status == SessionStatus.COMPLETED

        summary = await service.list_session_submissions(db_session, session.session_id)
        assert len(summary.submissions) == 1
        assert summary.submissions[0].passed is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multi_challenge_session(self, db_session):
        from app.challenges.schemas import PlatformChallengeConfig, UserProfile
        from app.evaluation.defaults import DEFAULT_EVALUATION_CONFIG
        from app.evaluation.evaluator import _deterministic_fallback
        from app.features.code import service
        from app.features.code.schemas import RunCreate

        profile = UserProfile(
            name="Multi Tester",
            skills=["Python"],
            experience_level="beginner",
        )
        config = PlatformChallengeConfig()
        config.challenge.challenges_per_candidate = 2

        solutions = {
            "Reverse a String": "def solution(s):\n    return s[::-1]",
            "Sum Two Numbers": "def solution(a, b):\n    return a + b",
        }

        async def _mock_execute(code, _cases, **kwargs):
            results = [
                CodeTestCaseResult(
                    test_case_id=str(index),
                    passed=True,
                    actual_output="ok",
                    expected_output="ok",
                    execution_time_ms=1.0,
                )
                for index in range(1, 4)
            ]
            visible = results[:2] if kwargs.get("include_hidden") is False else results
            return ExecutionOutcome.SUCCESS, visible, None, "sb-multi"

        with patch("app.challenges.generator.get_settings") as mock_settings:
            mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = ""
            with patch(
                "app.features.code.service.get_platform_challenge_config",
                new_callable=AsyncMock,
                return_value=config,
            ):
                with patch("app.features.code.tool.execute_submission", side_effect=_mock_execute):
                    session = await service.start_assessment_session(db_session, profile)

        assert len(session.challenges) == 2
        assert session.challenges[0].position == 1
        assert session.challenges[1].position == 2
        assert session.challenges[0].title != session.challenges[1].title

        for slot in session.challenges:
            submitted_code = solutions[slot.title]
            with patch("app.features.code.tool.execute_submission", side_effect=_mock_execute):
                with patch(
                    "app.features.code.service.evaluate_code_submission",
                    new_callable=AsyncMock,
                ) as mock_eval:
                    mock_eval.return_value = _deterministic_fallback(
                        CodeEvaluationContext(
                            challenge_id=slot.challenge_id,
                            title=slot.title,
                            description=slot.description,
                            submitted_code=submitted_code,
                            correctness_ratio=1.0,
                            performance_ratio=0.9,
                            passed_tests=2,
                            total_tests=2,
                        ),
                        DEFAULT_EVALUATION_CONFIG,
                    )
                    submission = await service.submit_session_challenge(
                        db_session,
                        RunCreate(
                            session_id=session.session_id,
                            challenge_id=slot.challenge_id,
                            submitted_code=submitted_code,
                        ),
                    )
            assert submission.passed is True

        completion = await service.complete_assessment_session(
            db_session,
            session.session_id,
            confirm_unsubmitted=False,
        )
        assert completion.challenges_submitted == 2
        assert completion.challenges_total == 2

        summary = await service.list_session_submissions(db_session, session.session_id)
        assert len(summary.submissions) == 2


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
        outcome, results, error, _ = await tool.execute_submission(
            fixture["correct_solution"],
            cases,
        )
        assert outcome == ExecutionOutcome.SUCCESS
        assert error is None
        assert all(r.passed for r in results)
