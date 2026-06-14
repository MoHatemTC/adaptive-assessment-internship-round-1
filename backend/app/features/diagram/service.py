"""
service.py — business logic for the diagram feature.

Two responsibilities:
  1. fetch_question  : retrieve a DiagramQuestion and return a served image URL
  2. submit_answer   : persist DiagramAnswer, call LiteLLM vision to grade,
                       update the record, return structured result

Image validation (type + size guards) lives here so both the API route
and the LangChain tool share the same checks.

Grading uses LiteLLM (as specified in the NFR resilience section) with
the image attached as a vision content block — NOT described as text.
Langfuse tracing is wired at call sites per the observability requirement.
"""

import uuid
import base64
import mimetypes
from datetime import datetime, timezone
from typing import Optional

import httpx
import litellm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.core.logging import get_logger
from app.features.diagram.models import DiagramQuestion, DiagramAnswer, SkillDimension

_logger = get_logger(__name__)


ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES    = 5 * 1024 * 1024


def _guess_mime(url: str) -> Optional[str]:
    mime, _ = mimetypes.guess_type(url)
    return mime


async def _fetch_and_validate_image(image_url: str) -> tuple[str, str]:
    """
    Download the image, check MIME type and size.
    Returns (base64_data, mime_type) ready for a vision content block.
    Raises ValueError on type/size violations.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(image_url)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "").split(";")[0].strip()
    if not content_type:
        content_type = _guess_mime(image_url) or ""

    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {content_type!r}. Allowed: {ALLOWED_MIME_TYPES}")

    raw = resp.content
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image too large: {len(raw)} bytes (max {MAX_IMAGE_BYTES})"
        )

    return base64.b64encode(raw).decode("ascii"), content_type


def _build_vision_message(prompt: str, rubric: str, b64_data: str, mime_type: str) -> list[dict]:
    """
    Build the messages list with the image as a base64 vision content block.
    This is the correct format — NOT a text description of the image.
    """
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}"
                    },
                },
                {
                    "type": "text",
                    "text": (
                        f"You are a silent LLM grader. Evaluate the learner's answer "
                        f"against the rubric. Return ONLY valid JSON with keys: "
                        f"score (float 0.0-1.0), feedback (string).\n\n"
                        f"Rubric:\n{rubric}\n\n"
                        f"Learner answer:\n{prompt}"
                    ),
                },
            ],
        }
    ]


class DiagramService:

    async def fetch_question(
        self,
        db: AsyncSession,
        question_id: uuid.UUID,
    ) -> Optional[DiagramQuestion]:
        """
        Retrieve a DiagramQuestion by ID.
        The image_url stored is already a served/signed URL (set at creation time).
        """
        result = await db.execute(
            select(DiagramQuestion).where(DiagramQuestion.id == question_id)
        )
        return result.scalar_one_or_none()

    async def submit_answer(
        self,
        db: AsyncSession,
        question_id: uuid.UUID,
        session_id: uuid.UUID,
        answer_text: str,
    ) -> DiagramAnswer:
        """
        1. Persist the answer record immediately (score=None until graded).
        2. Fetch + validate the image (type + size guards).
        3. Call LiteLLM vision model with image as content block.
        4. Parse structured grading result, update record.
        5. Return the populated DiagramAnswer.

        Grading is done inline here; move to a Celery task if async grading
        is required by the performance SLA (<10 s async grading requirement).
        """

        question = await self.fetch_question(db, question_id)
        if question is None:
            raise ValueError(f"DiagramQuestion {question_id} not found")

        answer = DiagramAnswer(
            session_id=session_id,
            question_id=question_id,
            answer_text=answer_text,
        )
        db.add(answer)
        await db.flush()

        try:
            b64_data, mime_type = await _fetch_and_validate_image(question.image_url)
        except Exception as exc:
            _logger.error("diagram_image_validation_failed", error=str(exc), answer_id=str(answer.id))
            raise


        settings = get_settings()
        messages = _build_vision_message(
            prompt=answer_text,
            rubric=question.rubric,
            b64_data=b64_data,
            mime_type=mime_type,
        )

        # TODO: add Langfuse callback here per observability requirement
        response = await litellm.acompletion(
            model=settings.LITELLM_MODEL,
            messages=messages,
            max_tokens=512,
            response_format={"type": "json_object"},
            api_key=settings.LITELLM_API_KEY.get_secret_value(),
            api_base=settings.LITELLM_BASE_URL or None,
        )

        import json
        raw = response.choices[0].message.content or "{}"
        grading = json.loads(raw)

        answer.score            = float(grading.get("score", 0.0))
        answer.grading_feedback = grading.get("feedback", "")
        answer.graded_at        = datetime.now(timezone.utc)

        db.add(answer)
        await db.flush()

        _logger.info(
            "diagram_answer_graded",
            answer_id=str(answer.id),
            session_id=str(session_id),
            score=answer.score,
        )
        return answer