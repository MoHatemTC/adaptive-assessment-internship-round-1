"""Langfuse trace context helpers for LLM invocations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


@dataclass(frozen=True)
class LangfuseTraceContext:
    """Metadata attached to LangChain LLM calls for Langfuse grouping."""

    session_id: str | None = None
    user_id: str | None = None
    operation: str | None = None
    tool: str | None = None
    question_index: int | None = None


def build_langfuse_metadata(ctx: LangfuseTraceContext | None) -> dict[str, Any]:
    """Build LangChain metadata keys consumed by Langfuse CallbackHandler."""
    if ctx is None:
        return {}

    metadata: dict[str, Any] = {}
    if ctx.session_id:
        metadata["langfuse_session_id"] = ctx.session_id
    if ctx.user_id:
        metadata["langfuse_user_id"] = ctx.user_id

    tags: list[str] = []
    if ctx.operation:
        tags.append(f"op:{ctx.operation}")
        metadata["langfuse_trace_name"] = ctx.operation
    if ctx.tool:
        tags.append(f"tool:{ctx.tool}")
    if ctx.question_index is not None:
        tags.append(f"q:{ctx.question_index}")
    if tags:
        metadata["langfuse_tags"] = tags

    extra: dict[str, str] = {}
    if ctx.operation:
        extra["operation"] = ctx.operation
    if ctx.tool:
        extra["tool"] = ctx.tool
    if ctx.question_index is not None:
        extra["question_index"] = str(ctx.question_index)
    if extra:
        metadata.update(extra)

    return metadata


def llm_invoke_config(
    callbacks: list[BaseCallbackHandler],
    *,
    trace: LangfuseTraceContext | None = None,
) -> dict[str, Any]:
    """Standard LangChain invoke config with Langfuse session/tool tags."""
    config: dict[str, Any] = {"callbacks": callbacks}
    metadata = build_langfuse_metadata(trace)
    if metadata:
        config["metadata"] = metadata
    return config


__all__ = ["LangfuseTraceContext", "build_langfuse_metadata", "llm_invoke_config"]
