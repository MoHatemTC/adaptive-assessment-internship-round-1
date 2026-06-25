"""FastAPI routes for the MCQ feature.

Exposes three endpoints — create a question, fetch a question (without its
answer), and submit an answer. Submission is silent: the response only
acknowledges receipt and never reveals correctness or score. The router is
named ``router`` so the application factory's auto-discovery registers it.
"""

from typing import Dict

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.core.logging import get_logger
from app.features.mcq.llm_generation import generate_and_store_next_mcq
from app.features.mcq.loop import run_mcq_loop
from app.features.mcq.models import MCQResponse
from app.features.mcq.schemas import (
    MCQAnswerRequest,
    MCQAnswerResponse,
    MCQCreateRequest,
    MCQNextOption,
    MCQNextQuestion,
    MCQQuestionResponse,
    MCQSubmitRequest,
    MCQSubmitResponse,
)
from app.features.mcq.service import (
    build_submit_response,
    create_question,
    get_correct_option,
    get_question,
    grade_answer,
    normalize_option_id,
)

_logger = get_logger(__name__)

router = APIRouter(prefix="/mcq", tags=["mcq"])


@router.get("/health")
def mcq_health_check() -> Dict[str, str]:
    """Report that the MCQ feature is ready.

    Returns:
        A small status payload identifying the feature.
    """
    return {
        "status": "ready",
        "feature": "mcq",
    }


@router.post("/questions", response_model=MCQQuestionResponse)
async def create_mcq_question(
    payload: MCQCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """Create an MCQ question and return it without the correct answer.

    Args:
        payload: Question text, difficulty, correct option, and options.
        db: Async database session dependency.

    Returns:
        The created question serialized without ``correct_option``.
    """
    return await create_question(
        db=db,
        question_text=payload.question_text,
        correct_option=payload.correct_option,
        options=[{"label": o.label, "text": o.text} for o in payload.options],
        difficulty=payload.difficulty,
    )


@router.get("/questions/{question_id}", response_model=MCQQuestionResponse)
async def get_mcq_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """Return an MCQ question without exposing the correct answer.

    Args:
        question_id: Primary key of the question to fetch.
        db: Async database session dependency.

    Returns:
        The question serialized without ``correct_option``.

    Raises:
        HTTPException: 404 if the question does not exist.
    """
    return await get_question(db=db, question_id=question_id)


@router.post("/submit", response_model=MCQSubmitResponse)
async def submit_mcq_answer(
    payload: MCQSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQSubmitResponse:
    """Submit, silently grade, and persist an MCQ answer.

    Grading is silent: the response only acknowledges receipt. Correctness and
    score are persisted server-side but never returned to the learner.

    Args:
        payload: Question id, session id, selected option, and optional learner.
        db: Async database session dependency.

    Returns:
        A silent acknowledgement carrying only ``received`` and ``question_id``.

    Raises:
        HTTPException: 404 if the question does not exist.
    """
    await build_submit_response(
        db=db,
        question_id=payload.question_id,
        selected_option=payload.selected_option,
        session_id=payload.session_id,
        learner_id=payload.learner_id,
    )
    return MCQSubmitResponse(received=True, question_id=payload.question_id)


@router.post(
    "/sessions/{session_id}/answer",
    response_model=MCQAnswerResponse,
)
async def submit_adaptive_mcq_answer(
    session_id: str,
    payload: MCQAnswerRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQAnswerResponse:
    """Submit an adaptive MCQ answer, grade it silently, and return the next item.

    Persists the answer, runs the adaptive loop (silent grading + memory card
    extraction), and — unless the assessment is complete — generates and stores
    the next question. The response is learner-safe: it contains only the next
    question (label/text options, no answer key) and ``is_complete``. It never
    carries score, correctness, pass/fail, grading feedback, dimension scores, or
    memory card contents.

    Args:
        session_id: Platform assessment session UUID from the path.
        payload: The answered question, selected option label, position, and
            optional generation context.
        db: Async database session dependency.

    Returns:
        A :class:`MCQAnswerResponse` with the next question (or ``None``) and the
        completion flag.

    Raises:
        HTTPException: 404 if the answered question does not exist.
    """
    # Persist the answer. ``is_correct`` is required (non-null); the float
    # ``score`` is left NULL here and set by the evaluation layer inside the loop.
    correct_option = await get_correct_option(db=db, question_id=payload.question_id)
    grading = grade_answer(
        correct_option=correct_option,
        selected_option=payload.selected_option,
    )
    response = MCQResponse(
        question_id=payload.question_id,
        session_id=session_id,
        learner_id=payload.learner_id,
        selected_option=normalize_option_id(payload.selected_option),
        is_correct=grading["is_correct"],
        score=None,
    )
    db.add(response)
    await db.flush()
    mcq_response_id = response.id

    # Adaptive loop: grade silently, persist score/feedback, extract memory card.
    loop_result = await run_mcq_loop(
        session_id=session_id,
        question_index=payload.question_index,
        mcq_response_id=mcq_response_id,
        total_questions=payload.total_questions,
        db=db,
    )
    is_complete = loop_result["is_complete"]

    next_question: MCQNextQuestion | None = None
    if not is_complete:
        next_plan = {
            "next_question_index": payload.question_index + 1,
            "memory_summary": loop_result.get("memory_summary", ""),
        }
        try:
            generated = await generate_and_store_next_mcq(
                db=db,
                next_plan=next_plan,
                learner_profile=payload.learner_profile,
                admin_config=payload.admin_config,
            )
            next_question = MCQNextQuestion(
                id=generated["id"],
                question_text=generated["question_text"],
                difficulty=generated["difficulty"],
                dimension=generated.get("dimension"),
                options=[
                    MCQNextOption(label=o["label"], text=o["text"])
                    for o in generated["options"]
                ],
            )
        except Exception as exc:  # noqa: BLE001 - generation must not break the flow
            _logger.error("mcq_next_generation_failed", error=str(exc))
            next_question = None

    return MCQAnswerResponse(next_question=next_question, is_complete=is_complete)
