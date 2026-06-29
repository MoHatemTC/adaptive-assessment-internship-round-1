"""LiteLLM vision completions with Kimi/reasoning-model-safe JSON parsing."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import litellm

from app.config import get_settings
from app.core.llm_json import (
    parse_llm_json,
    prefers_raw_json_model,
    resolve_vision_model,
)
from app.core.logging import get_logger

_logger = get_logger(__name__)

_VISION_JSON_MAX_TOKENS = 768
_VISION_PROVIDER_MAX_RETRIES = 2
_VISION_RETRY_BACKOFF_SECONDS = 2.0

_JSON_SYSTEM_PROMPT = (
    "You are a silent API. Respond with a single valid JSON object only. "
    "No markdown, no code fences, no reasoning, no explanation."
)


class VisionGradingUnavailable(RuntimeError):
    """Raised when a vision grading call cannot reach the provider."""


def _with_json_system_message(
    messages: list[dict[str, Any]],
    *,
    resolved_model: str,
) -> list[dict[str, Any]]:
    if not prefers_raw_json_model(resolved_model):
        return messages
    if messages and messages[0].get("role") == "system":
        return messages
    return [{"role": "system", "content": _JSON_SYSTEM_PROMPT}, *messages]


async def acompletion_vision_json(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int = _VISION_JSON_MAX_TOKENS,
) -> dict[str, Any]:
    """Call a vision-capable model and return a parsed JSON object.

    Provider/network errors are retried briefly. JSON parse failures fail fast
    (retrying prose responses from reasoning VLMs wastes tens of seconds).
    """
    settings = get_settings()
    resolved = resolve_vision_model(model)
    payload_messages = _with_json_system_message(messages, resolved_model=resolved)
    kwargs: dict[str, Any] = {
        "model": resolved,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "api_key": settings.LITELLM_API_KEY.get_secret_value(),
        "api_base": settings.LITELLM_BASE_URL or None,
    }
    if not prefers_raw_json_model(resolved):
        kwargs["response_format"] = {"type": "json_object"}

    last_exc: Exception | None = None
    for attempt in range(_VISION_PROVIDER_MAX_RETRIES):
        try:
            response = await litellm.acompletion(**kwargs)
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
        except json.JSONDecodeError:
            raise
        except Exception as exc:
            last_exc = exc
            _logger.warning(
                "vision_completion_failed",
                model=resolved,
                error=str(exc),
                attempt=attempt + 1,
            )
            if attempt + 1 < _VISION_PROVIDER_MAX_RETRIES:
                await asyncio.sleep(_VISION_RETRY_BACKOFF_SECONDS * (attempt + 1))

    _logger.error("vision_completion_failed", model=resolved, error=str(last_exc))
    raise VisionGradingUnavailable(
        "Vision model call failed. Verify LITELLM_API_KEY, "
        "LITELLM_BASE_URL, and LITELLM_VISION_MODEL (or LITELLM_MODEL)."
    ) from last_exc


def extract_preview(content: str | list[object] | None, limit: int = 120) -> str:
    """Short preview string for logs."""
    from app.core.llm_json import extract_llm_text

    text = extract_llm_text(content)
    return text[:limit] + ("..." if len(text) > limit else "")


__all__ = [
    "VisionGradingUnavailable",
    "acompletion_vision_json",
]
