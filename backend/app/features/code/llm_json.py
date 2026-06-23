"""Fast JSON LLM helpers for the coding tool (generation + grading)."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from app.config import get_settings
from app.core.llm import get_llm_with_tracing

T = TypeVar("T", bound=BaseModel)

# Cap completion size for short JSON payloads (reduces reasoning-model latency).
_JSON_MAX_TOKENS = 1536


class LLMJsonUnavailable(RuntimeError):
    """Raised when a JSON-mode LLM call cannot reach the provider."""


def _is_llm_unavailable(exc: BaseException) -> bool:
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


def extract_llm_text(content: str | list[object]) -> str:
    """Flatten LangChain message content, skipping reasoning blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts) if parts else str(content)


def extract_json(content: str) -> str:
    """Extract a JSON object substring from model output."""
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start : end + 1]
    return content


def prefers_raw_json_model(model: str | None = None) -> bool:
    """Return True when structured output should be skipped for this model."""
    name = (model or get_settings().LITELLM_MODEL).lower()
    return "kimi" in name or "k2." in name or "k2-" in name


def compact_json_schema(model_cls: type[BaseModel]) -> str:
    """Minified JSON schema string for LLM prompts."""
    return json.dumps(model_cls.model_json_schema(), separators=(",", ":"))


async def invoke_json_model(
    *,
    model_cls: type[T],
    messages: list[tuple[str, str]],
    model: str | None = None,
) -> T:
    """Single-shot JSON generation with reasoning-model-safe text extraction."""
    llm, callbacks = get_llm_with_tracing(model)
    bound = llm.bind(max_tokens=_JSON_MAX_TOKENS)
    try:
        response = await bound.ainvoke(
            messages,
            config={"callbacks": callbacks},
        )
    except Exception as exc:
        if _is_llm_unavailable(exc):
            raise LLMJsonUnavailable(
                "LLM call is unavailable. Verify LITELLM_API_KEY, "
                "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
            ) from exc
        raise

    content = extract_llm_text(response.content)
    return model_cls.model_validate_json(extract_json(content))


__all__ = [
    "LLMJsonUnavailable",
    "compact_json_schema",
    "extract_json",
    "extract_llm_text",
    "invoke_json_model",
    "prefers_raw_json_model",
]
