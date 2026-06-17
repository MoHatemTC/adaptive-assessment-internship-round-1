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
    if name in {"AuthenticationError", "APIConnectionError", "RateLimitError", "ServiceUnavailableError"}:
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
    return (
        f"Challenge: {title}\n"
        f"Language: {language}\n\n"
        f"Description:\n{description}\n\n"
        f"Sandbox result: {passed_tests}/{total_tests} tests passed "
        f"(score {sandbox_score:.2f}).\n\n"
        f"Submitted code:\n```\n{submitted_code}\n```\n\n"
        "Evaluate approach and efficiency now."
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
    """Run the approach/efficiency rubric through the traced LLM.

    Uses LangChain structured output for reliable JSON, normalises scores that
    arrive on a 1–5 or 1–10 scale, and retries once on parse failure. Isolated
    so tests can substitute a deterministic result without a live model call.

    Returns:
        The parsed :class:`RubricScores` from the model.
    """
    llm, callbacks = get_llm_with_tracing()
    # Structured output is unreliable with streaming enabled on some providers.
    structured = llm.bind(streaming=False).with_structured_output(RubricScores)
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

    # Fallback: raw invoke + best-effort JSON extraction (older code path).
    try:
        response = await llm.bind(streaming=False).ainvoke(
            messages, config={"callbacks": callbacks}
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        rubric = RubricScores.model_validate_json(_extract_json(content))
        return _normalize_llm_rubric(rubric)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise RuntimeError("LLM rubric grading failed after retries") from (last_error or exc)
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


def _extract_json(content: str) -> str:
    """Best-effort extraction of a JSON object from an LLM response.

    Tolerates models that wrap JSON in markdown fences or surrounding prose.

    Args:
        content: Raw model output.

    Returns:
        The JSON substring (from the first ``{`` to the last ``}``), or the
        original content if no braces are found.
    """
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start : end + 1]
    return content


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
    """Grade a code submission and persist one ``grade_results`` row.

    Combines the E2B sandbox score (already stored on the submission) with an
    LLM rubric on approach/efficiency. The score is never surfaced to the
    learner.

    Args:
        db: Active async database session.
        submission_id: PK of the ``code_submissions`` row to grade.
        session_id: Platform assessment session UUID.
        question_index: Zero-based position in the assessment blueprint.

    Returns:
        The persisted :class:`~app.sessions.models.GradeResult` row.

    Raises:
        HTTPException: 404 if the submission or its challenge is missing.
    """
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


__all__ = ["LLMGradingUnavailable", "grade_submission"]
