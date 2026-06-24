"""
app/features/adaptation/agent.py
Tool-agnostic. Takes a list of AnswerRecord (already normalized by
each feature's repository function) — never imports a feature model.
"""

import json
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.core.llm import get_llm_with_tracing
from app.core.llm_json import extract_json, extract_llm_text, prefers_raw_json_model
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.features.adaptation.prompts import SYSTEM_PROMPT, build_user_message
from app.features.adaptation.schemas import AdaptationResult, AnswerRecord, DimensionScore

_logger = get_logger(__name__)


def _score_to_difficulty(scores: dict) -> str:
    avg = sum(v["score"] for v in scores.values()) / len(scores)
    if avg <= 3:
        return "easy"
    if avg <= 6:
        return "medium"
    return "hard"


async def run_adaptation(
    session_id: uuid.UUID,
    answers: list[AnswerRecord],
) -> AdaptationResult:
    """
    answers must already be normalized — gathering them from each tool's
    table is the caller's job (see repository.py), not this agent's.
    """
    if not answers:
        raise ValueError(f"No answers provided for session {session_id}")

    answer_dicts = [a.model_dump() for a in answers]
    user_message = build_user_message(answer_dicts)

    settings = get_settings()
    model = settings.LITELLM_MODEL
    llm, callbacks = get_llm_with_tracing(model)
    bound = llm.bind(max_tokens=512)
    if not prefers_raw_json_model(model):
        bound = bound.bind(response_format={"type": "json_object"})

    start = time.perf_counter()
    try:
        response = await bound.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ],
            config={"callbacks": callbacks},
        )
        record_llm_call(model, "adaptation", "success", time.perf_counter() - start)
    except Exception:
        record_llm_call(model, "adaptation", "error", time.perf_counter() - start)
        raise

    raw = extract_llm_text(response.content)
    parsed = json.loads(extract_json(raw))

    dim_scores = {
        k: DimensionScore(**v)
        for k, v in parsed["dimension_scores"].items()
    }

    next_diff = parsed.get("next_difficulty")
    if next_diff not in ("easy", "medium", "hard"):
        next_diff = _score_to_difficulty(parsed["dimension_scores"])

    _logger.info(
        "adaptation_complete",
        session_id=str(session_id),
        tools_seen=list({a.tool for a in answers}),
        next_difficulty=next_diff,
    )

    return AdaptationResult(
        session_id=session_id,
        next_difficulty=next_diff,
        dimension_scores=dim_scores,
    )
