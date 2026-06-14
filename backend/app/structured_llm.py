"""Structured JSON LLM calls for challenge generation and evaluation.

The kernel :func:`app.core.llm.get_llm_with_tracing` enables ``streaming=True`` for
agent chat flows. Reasoning models such as ``azure/FW-Kimi-K2.6`` only emit the
final JSON in ``text`` blocks when ``streaming=False``. This module provides a
non-streaming gateway plus content extraction for those structured tasks.
"""

from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler
from langchain_litellm import ChatLiteLLM

from app.config import get_settings
from app.core.llm import get_langfuse_callback

_ASSESSMENT_TEMPERATURE = 0.1


def extract_llm_text(content: str | list) -> str:
    """Normalize LangChain message content to a single text string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
        if text_parts:
            return "".join(text_parts)
        thinking_parts = [
            str(block.get("thinking", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "thinking"
        ]
        if thinking_parts:
            return "".join(thinking_parts)
    return str(content)


def get_structured_llm_with_tracing(
    model: str | None = None,
) -> tuple[ChatLiteLLM, list[BaseCallbackHandler]]:
    """Return a non-streaming LLM for JSON-structured assessment calls."""
    settings = get_settings()
    llm = ChatLiteLLM(
        model=model or settings.LITELLM_MODEL,
        temperature=_ASSESSMENT_TEMPERATURE,
        streaming=False,
        max_retries=3,
        api_key=settings.LITELLM_API_KEY.get_secret_value(),
        api_base=settings.LITELLM_BASE_URL or None,
    )
    callbacks: list[BaseCallbackHandler] = [get_langfuse_callback()]
    return llm, callbacks
