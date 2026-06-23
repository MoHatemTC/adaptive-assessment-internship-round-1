"""Shared helpers for JSON-shaped LLM responses (text and vision)."""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


def extract_llm_text(content: str | list[object] | None) -> str:
    """Flatten model message content, skipping reasoning blocks."""
    if content is None:
        return ""
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
    if start == -1:
        return content
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(content[start:])
        return content[start : start + end]
    except json.JSONDecodeError:
        end = content.rfind("}")
        if end > start:
            return content[start : end + 1]
        return content


def parse_llm_json(content: str | list[object] | None) -> dict[str, Any]:
    """Parse JSON from raw or block-structured LLM output."""
    text = extract_llm_text(content)
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("Expected JSON object", text, start)
    return obj


def prefers_raw_json_model(model: str | None = None) -> bool:
    """Return True when structured output should be skipped for this model."""
    name = (model or get_settings().LITELLM_MODEL).lower()
    return "kimi" in name or "k2." in name or "k2-" in name


def resolve_vision_model(model: str | None = None) -> str:
    """Return the vision model id, falling back to the default LLM model."""
    settings = get_settings()
    return model or settings.LITELLM_VISION_MODEL or settings.LITELLM_MODEL


__all__ = [
    "extract_json",
    "extract_llm_text",
    "parse_llm_json",
    "prefers_raw_json_model",
    "resolve_vision_model",
]
