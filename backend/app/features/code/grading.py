"""Layer 1 — Grading.

Combines the deterministic E2B sandbox score (already persisted on the
``code_submissions`` row) with an LLM rubric judging *approach* and
*efficiency*, then writes a single row to the platform ``grade_results`` table.

Grading output is never surfaced to the learner and is never written back to
the tool's own ``code_submissions`` row — it flows only into ``grade_results``
and downstream memory/analysis layers.
"""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm import get_llm_with_tracing
from app.core.logging import get_logger
from app.features.code.llm_json import (
    extract_json as _extract_json,
    extract_llm_text as _extract_llm_text,
)
from app.features.code.languages import get_language_config
from app.features.code.models import CodeChallenge, CodeSubmission
from app.sessions.models import GradeResult
from app.shared.schemas.memory import RubricDimension, RubricScores

_logger = get_logger(__name__)

TOOL_TYPE = "coding"


class LLMGradingUnavailable(RuntimeError):
    """Raised when the approach/efficiency rubric cannot reach the LLM provider."""


def _is_llm_unavailable(exc: BaseException) -> bool:
    """Return True when ``exc`` indicates the LLM provider is unreachable or rejected."""
    name = type(exc).__name__
    if name in {
        "AuthenticationError",
        "APIConnectionError",
        "RateLimitError",
        "ServiceUnavailableError",
    }:
        return True
    cause = exc.__cause__
    return _is_llm_unavailable(cause) if cause is not None else False

#: Weight given to the deterministic sandbox correctness signal when blending
#: it with the LLM's qualitative rubric into the overall score.
_SANDBOX_WEIGHT = 0.5

_RUBRIC_SYSTEM_PROMPT = (
    "You are a silent expert programming examiner. Judge a learner's code "
    "submission on exactly two qualitative dimensions:\n"
    "  - approach: clarity, correctness of strategy, edge-case handling\n"
    "  - efficiency: algorithmic complexity, avoidance of needless work\n\n"
    "Do NOT judge raw test pass rate — that is measured separately.\n"
    "Every score MUST be a float in [0.0, 1.0] (e.g. 0.8, not 8). "
    "Return JSON matching this schema:\n"
    '{"dimensions": [{"name": "approach", "score": 0.0, "feedback": "..."}, '
    '{"name": "efficiency", "score": 0.0, "feedback": "..."}], "overall": 0.0}'
)

_RUBRIC_RETRY_PROMPT = (
    "Your previous response used invalid scores. Use ONLY floats between 0.0 and "
    "1.0 inclusive. Never use a 1–5 or 1–10 scale. Dimension names must be "
    "exactly 'approach' and 'efficiency'."
)


def _build_rubric_prompt(
    *,
    title: str,
    description: str,
    language: str,
    submitted_code: str,
    sandbox_score: float,
    passed_tests: int,
    total_tests: int,
) -> str:
    """Compose the user prompt for the approach/efficiency rubric.

    Args:
        title: Challenge title.
        description: Challenge description.
        language: Programming language of the submission.
        submitted_code: The learner's submitted source.
        sandbox_score: Weighted sandbox score in ``[0, 1]``.
        passed_tests: Number of passing test cases.
        total_tests: Total number of test cases.

    Returns:
        The formatted prompt string.
    """
    config = get_language_config(language)
    return (
        f"Challenge: {title}\n"
        f"Language: {config.label} ({config.id})\n\n"
        f"Description:\n{description}\n\n"
        f"Sandbox result: {passed_tests}/{total_tests} tests passed "
        f"(score {sandbox_score:.2f}).\n\n"
        f"Submitted {config.label} code:\n```{config.id}\n{submitted_code}\n```\n\n"
        f"Evaluate approach and efficiency for this {config.label} solution."
    )


async def _grade_with_llm(
    *,
    title: str,
    description: str,
    language: str,
    submitted_code: str,
    sandbox_score: float,
    passed_tests: int,
    total_tests: int,
) -> RubricScores:
    """Run the approach/efficiency rubric through the traced LLM."""
    from app.config import get_settings
    from app.features.code.llm_json import (
        LLMJsonUnavailable,
        invoke_json_model,
        prefers_raw_json_model,
    )

    prompt = _build_rubric_prompt(
        title=title,
        description=description,
        language=language,
        submitted_code=submitted_code,
        sandbox_score=sandbox_score,
        passed_tests=passed_tests,
        total_tests=total_tests,
    )
    messages: list[tuple[str, str]] = [
        ("system", _RUBRIC_SYSTEM_PROMPT),
        ("human", prompt),
    ]

    model = get_settings().LITELLM_MODEL
    if prefers_raw_json_model(model):
        try:
            rubric = await invoke_json_model(
                model_cls=RubricScores,
                messages=[
                    *messages,
                    (
                        "human",
                        "Return ONLY JSON with dimensions (approach, efficiency) and "
                        "overall. Scores must be floats in [0.0, 1.0]. No reasoning.",
                    ),
                ],
            )
        except LLMJsonUnavailable as exc:
            raise LLMGradingUnavailable(str(exc)) from exc
        return _normalize_llm_rubric(rubric)

    llm, callbacks = get_llm_with_tracing()
    structured = llm.with_structured_output(RubricScores)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            result = await structured.ainvoke(
                messages,
                config={"callbacks": callbacks},
            )
            rubric = result if isinstance(result, RubricScores) else RubricScores.model_validate(result)
            return _normalize_llm_rubric(rubric)
        except (OutputParserException, ValidationError) as exc:
            last_error = exc
            _logger.warning(
                "code_llm_rubric_parse_failed",
                attempt=attempt + 1,
                error=str(exc),
            )
            messages.append(("human", _RUBRIC_RETRY_PROMPT))
        except Exception as exc:
            if _is_llm_unavailable(exc):
                raise LLMGradingUnavailable(
                    "LLM grading is unavailable. Verify LITELLM_API_KEY, "
                    "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
                ) from exc
            raise

    try:
        rubric = await invoke_json_model(
            model_cls=RubricScores,
            messages=[*messages, ("human", _RUBRIC_RETRY_PROMPT)],
        )
        return _normalize_llm_rubric(rubric)
    except LLMJsonUnavailable as exc:
        raise LLMGradingUnavailable(str(exc)) from exc
    except (ValidationError, json.JSONDecodeError) as exc:
        raise RuntimeError("LLM rubric grading failed after retries") from (last_error or exc)
    except LLMGradingUnavailable:
        raise
    except Exception as exc:
        if _is_llm_unavailable(exc):
            raise LLMGradingUnavailable(
                "LLM grading is unavailable. Verify LITELLM_API_KEY, "
                "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
            ) from exc
        raise


def _normalize_unit_score(score: float) -> float:
    """Map an LLM score into ``[0.0, 1.0]`` when the model uses the wrong scale."""
    value = float(score)
    if value > 1.0:
        if value <= 5.0:
            value /= 5.0
        elif value <= 10.0:
            value /= 10.0
    return min(1.0, max(0.0, round(value, 3)))


def _normalize_llm_rubric(rubric: RubricScores) -> RubricScores:
    """Normalise dimension names and coerce scores into the unit interval."""
    dimensions = [
        RubricDimension(
            name=dim.name.lower(),
            score=_normalize_unit_score(dim.score),
            feedback=dim.feedback,
        )
        for dim in rubric.dimensions
    ]
    overall = _normalize_unit_score(rubric.overall)
    return RubricScores(dimensions=dimensions, overall=overall)


def _compose_rubric(sandbox_score: float, llm_rubric: RubricScores) -> RubricScores:
    """Blend the deterministic sandbox signal into the LLM rubric.

    Prepends a ``correctness`` dimension sourced from the sandbox score and
    recomputes ``overall`` as a weighted blend of sandbox correctness and the
    LLM's qualitative overall.

    Args:
        sandbox_score: Weighted sandbox score in ``[0, 1]``.
        llm_rubric: The approach/efficiency rubric from the LLM.

    Returns:
        The composed :class:`RubricScores` to persist.
    """
    correctness = RubricDimension(
        name="correctness",
        score=sandbox_score,
        feedback="Weighted fraction of test cases passed in the sandbox.",
    )
    overall = round(
        _SANDBOX_WEIGHT * sandbox_score + (1 - _SANDBOX_WEIGHT) * llm_rubric.overall,
        3,
    )
    return RubricScores(
        dimensions=[correctness, *llm_rubric.dimensions],
        overall=min(1.0, max(0.0, overall)),
    )


async def grade_submission(
    db: AsyncSession,
    submission_id: int,
    session_id: str,
    question_index: int,
) -> GradeResult:
    """Grade a code submission with the full LLM rubric and persist ``grade_results``."""
    submission, challenge, sandbox_score, passed_tests, total_tests = (
        await _load_submission_grade_context(db, submission_id)
    )
    llm_rubric = await _grade_with_llm(
        title=challenge.title,
        description=challenge.description,
        language=challenge.language,
        submitted_code=submission.submitted_code,
        sandbox_score=sandbox_score,
        passed_tests=passed_tests,
        total_tests=total_tests,
    )
    rubric = _compose_rubric(sandbox_score, llm_rubric)
    return await _persist_grade_result(
        db,
        session_id=session_id,
        submission_id=submission_id,
        question_index=question_index,
        rubric=rubric,
    )


def _sandbox_heuristic_rubric(sandbox_score: float, *, passed: bool) -> RubricScores:
    """Fast rubric estimate from sandbox output while LLM grading runs in background."""
    approach = sandbox_score if passed else max(0.0, sandbox_score * 0.7)
    efficiency = max(0.0, sandbox_score * 0.9)
    pending = "Awaiting detailed LLM review."
    return RubricScores(
        dimensions=[
            RubricDimension(name="approach", score=approach, feedback=pending),
            RubricDimension(name="efficiency", score=efficiency, feedback=pending),
        ],
        overall=round((approach + efficiency) / 2, 3),
    )


async def _load_submission_grade_context(
    db: AsyncSession,
    submission_id: int,
) -> tuple[CodeSubmission, CodeChallenge, float, int, int]:
    submission = (
        await db.exec(select(CodeSubmission).where(CodeSubmission.id == submission_id))
    ).first()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )

    challenge = (
        await db.exec(
            select(CodeChallenge).where(CodeChallenge.id == submission.challenge_id)
        )
    ).first()
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found"
        )

    metadata: dict = (
        json.loads(submission.grading_metadata) if submission.grading_metadata else {}
    )
    sandbox_score = submission.score if submission.score is not None else 0.0
    passed_tests = int(metadata.get("passed_tests", 0))
    total_tests = int(metadata.get("total_tests", 0))
    return submission, challenge, sandbox_score, passed_tests, total_tests


async def _persist_grade_result(
    db: AsyncSession,
    *,
    session_id: str,
    submission_id: int,
    question_index: int,
    rubric: RubricScores,
) -> GradeResult:
    grade = GradeResult(
        session_id=session_id,
        tool_type=TOOL_TYPE,
        tool_session_id=submission_id,
        question_index=question_index,
        rubric_scores=rubric.model_dump_json(),
        llm_judge_score=None,
    )
    db.add(grade)
    await db.flush()

    _logger.info(
        "code_submission_graded",
        submission_id=submission_id,
        session_id=session_id,
        question_index=question_index,
        overall=rubric.overall,
    )
    return grade


async def grade_submission_sandbox_only(
    db: AsyncSession,
    submission_id: int,
    session_id: str,
    question_index: int,
) -> GradeResult:
    """Persist a sandbox-derived rubric immediately; LLM refines it later."""
    submission, _challenge, sandbox_score, _passed_tests, _total_tests = (
        await _load_submission_grade_context(db, submission_id)
    )
    heuristic = _sandbox_heuristic_rubric(
        sandbox_score,
        passed=bool(submission.passed),
    )
    rubric = _compose_rubric(sandbox_score, heuristic)
    return await _persist_grade_result(
        db,
        session_id=session_id,
        submission_id=submission_id,
        question_index=question_index,
        rubric=rubric,
    )


async def upgrade_grade_with_llm(db: AsyncSession, grade_id: int) -> GradeResult:
    """Replace a sandbox-heuristic grade with the full LLM rubric."""
    grade = await db.get(GradeResult, grade_id)
    if grade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grade result not found"
        )

    submission, challenge, sandbox_score, passed_tests, total_tests = (
        await _load_submission_grade_context(db, int(grade.tool_session_id))
    )
    llm_rubric = await _grade_with_llm(
        title=challenge.title,
        description=challenge.description,
        language=challenge.language,
        submitted_code=submission.submitted_code,
        sandbox_score=sandbox_score,
        passed_tests=passed_tests,
        total_tests=total_tests,
    )
    rubric = _compose_rubric(sandbox_score, llm_rubric)
    grade.rubric_scores = rubric.model_dump_json()
    db.add(grade)
    await db.flush()

    _logger.info(
        "code_submission_grade_upgraded",
        grade_id=grade_id,
        submission_id=submission.id,
        overall=rubric.overall,
    )
    return grade


__all__ = [
    "LLMGradingUnavailable",
    "grade_submission",
    "grade_submission_sandbox_only",
    "upgrade_grade_with_llm",
]
