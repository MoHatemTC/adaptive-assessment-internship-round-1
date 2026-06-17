"""
app/features/adaptation/agent.py
Tool-agnostic. Takes a list of AnswerRecord (already normalized by
each feature's repository function) — never imports a feature model.
"""

import json
import uuid

import litellm

from app.config import get_settings
from app.core.logging import get_logger
from app.features.adaptation.prompts import SYSTEM_PROMPT, build_user_message
from app.features.adaptation.schemas import AnswerRecord, AdaptationResult, DimensionScore

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
    response = await litellm.acompletion(
        model=settings.LITELLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=512,
        response_format={"type": "json_object"},
        api_key=settings.LITELLM_API_KEY.get_secret_value(),
        api_base=settings.LITELLM_BASE_URL or None,
    )

    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)

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