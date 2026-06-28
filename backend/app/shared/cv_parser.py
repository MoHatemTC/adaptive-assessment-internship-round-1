"""CV parsing utility — extracts structured context from a PDF CV.

The CV is always optional. Every failure mode (no text, malformed PDF, LLM error,
unparseable JSON) degrades to an empty dict so sign-in never breaks because of a
bad or missing CV. The extracted context is merged into the learner profile and
consumed by the tool generators to calibrate difficulty and topic relevance.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pypdf import PdfReader

from app.core.llm import get_llm_with_tracing
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Cap the CV text handed to the LLM so a long document cannot blow the prompt.
_MAX_CV_CHARS = 8000

_SYSTEM_PROMPT = (
    "You are a CV parser. Extract key information from this CV text and "
    "return ONLY valid JSON with these exact keys: skills (list of strings), "
    "experience_years (int), current_role (string), technologies (list), "
    "education (string), cv_summary (string, one sentence). "
    "No markdown, no explanation."
)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract concatenated text from a PDF's pages.

    This is CPU-bound (pypdf parses the document synchronously) and must be run
    via :func:`asyncio.to_thread` from async callers.

    Args:
        pdf_bytes: Raw bytes of the uploaded PDF file.

    Returns:
        The concatenated page text, stripped. Empty string if no text is found.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_answer(content: Any) -> str:
    """Extract the final answer string from an LLM response.

    Kimi K2 is a reasoning model: ``response.content`` is a list of thinking
    blocks followed by the answer string. The answer is recovered by scanning the
    list in reverse for the first usable text item.

    Args:
        content: The ``response.content`` returned by the LLM.

    Returns:
        The answer string, or an empty string if none could be recovered.
    """
    if isinstance(content, list):
        for item in reversed(content):
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "").strip()
                if text:
                    return text
        return ""
    return str(content).strip()


def _json_from_answer(answer: str) -> dict[str, Any]:
    """Parse a JSON object out of the LLM answer, tolerating stray code fences.

    Args:
        answer: The raw answer text returned by the LLM.

    Returns:
        The parsed JSON object as a dict.

    Raises:
        ValueError: If no JSON object can be located in the answer.
        json.JSONDecodeError: If the located text is not valid JSON.
    """
    cleaned = answer.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM response does not contain a valid JSON object")

    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON is not an object")
    return parsed


async def extract_cv_context(pdf_bytes: bytes) -> dict[str, Any]:
    """Parse a PDF CV and extract structured context via the LLM.

    Extracts raw text from the PDF (off the event loop), then asks the LLM to
    return a structured JSON summary. Deterministic extraction runs at
    temperature 0.0. Any failure logs a warning and returns an empty dict — the
    CV is optional and must never block sign-in.

    Args:
        pdf_bytes: Raw bytes of the uploaded PDF file.

    Returns:
        A dict with keys ``skills``, ``experience_years``, ``current_role``,
        ``technologies``, ``education``, and ``cv_summary``; or an empty dict on
        any extraction or parsing failure.
    """
    try:
        raw_text = await asyncio.to_thread(_extract_pdf_text, pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - CV is optional; never raise
        logger.warning("cv_pdf_extraction_failed", reason=str(exc))
        return {}

    if not raw_text:
        logger.warning("cv_pdf_empty")
        return {}

    excerpt = raw_text[:_MAX_CV_CHARS]
    human = (
        "Extract structured information from the following CV text and return "
        "ONLY the JSON object described.\n\n"
        f"CV text:\n{excerpt}\n\n"
        "Return the JSON now:"
    )

    try:
        llm, callbacks = get_llm_with_tracing()
        # Deterministic extraction — override the gateway's assessment default.
        if hasattr(llm, "temperature"):
            llm.temperature = 0.0
        response = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)],
            config={"callbacks": callbacks},
        )
        answer = _parse_answer(response.content)
        if not answer:
            logger.warning("cv_llm_empty_answer")
            return {}
        context = _json_from_answer(answer)
        logger.info(
            "cv_context_extracted",
            current_role=context.get("current_role"),
            experience_years=context.get("experience_years"),
            skill_count=len(context.get("skills") or []),
        )
        return context
    except Exception as exc:  # noqa: BLE001 - CV is optional; never raise
        logger.warning("cv_llm_extraction_failed", reason=str(exc))
        return {}


__all__ = ["extract_cv_context"]
