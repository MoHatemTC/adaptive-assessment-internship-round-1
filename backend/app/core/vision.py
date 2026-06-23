"""LiteLLM vision completions with Kimi/reasoning-model-safe JSON parsing."""

from __future__ import annotations

import json
from typing import Any

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.llm_json import (
    parse_llm_json,
    prefers_raw_json_model,
    resolve_vision_model,
)
from app.core.logging import get_logger

_logger = get_logger(__name__)

_VISION_JSON_MAX_TOKENS = 768
_VISION_MAX_RETRIES = 3


class VisionGradingUnavailable(RuntimeError):
    """Raised when a vision grading call cannot reach the provider."""


@retry(
    stop=stop_after_attempt(_VISION_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
async def acompletion_vision_json(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int = _VISION_JSON_MAX_TOKENS,
) -> dict[str, Any]:
    """Call a vision-capable model and return a parsed JSON object.

    Kimi K2.6 and similar reasoning VLMs may ignore ``response_format`` or wrap
    JSON in markdown fences — those cases are handled via raw extraction.
    """
    settings = get_settings()
    resolved = resolve_vision_model(model)
    kwargs: dict[str, Any] = {
        "model": resolved,
        "messages": messages,
        "max_tokens": max_tokens,
        "api_key": settings.LITELLM_API_KEY.get_secret_value(),
        "api_base": settings.LITELLM_BASE_URL or None,
    }
    if not prefers_raw_json_model(resolved):
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:
        _logger.error("vision_completion_failed", model=resolved, error=str(exc))
        raise VisionGradingUnavailable(
            "Vision model call failed. Verify LITELLM_API_KEY, "
            "LITELLM_BASE_URL, and LITELLM_VISION_MODEL (or LITELLM_MODEL)."
        ) from exc

    content = response.choices[0].message.content
    try:
        return parse_llm_json(content)
    except json.JSONDecodeError as exc:
        _logger.warning(
            "vision_json_parse_failed",
            model=resolved,
            preview=extract_preview(content),
        )
        raise


def extract_preview(content: str | list[object] | None, limit: int = 120) -> str:
    """Short preview string for logs."""
    from app.core.llm_json import extract_llm_text

    text = extract_llm_text(content)
    return text[:limit] + ("..." if len(text) > limit else "")


__all__ = [
    "VisionGradingUnavailable",
    "acompletion_vision_json",
]
