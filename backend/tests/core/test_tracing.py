"""Tests for Langfuse trace metadata helpers."""

from __future__ import annotations

from app.core.tracing import LangfuseTraceContext, build_langfuse_metadata, llm_invoke_config


def test_build_langfuse_metadata_includes_session_and_tags():
    metadata = build_langfuse_metadata(
        LangfuseTraceContext(
            session_id="sess-1",
            user_id="learner-1",
            operation="session_judge",
            tool="mcq",
            question_index=2,
        )
    )
    assert metadata["langfuse_session_id"] == "sess-1"
    assert metadata["langfuse_user_id"] == "learner-1"
    assert metadata["langfuse_trace_name"] == "session_judge"
    assert "op:session_judge" in metadata["langfuse_tags"]
    assert "tool:mcq" in metadata["langfuse_tags"]
    assert "q:2" in metadata["langfuse_tags"]


def test_llm_invoke_config_attaches_metadata():
    config = llm_invoke_config([], trace=LangfuseTraceContext(operation="planner"))
    assert config["callbacks"] == []
    assert config["metadata"]["langfuse_trace_name"] == "planner"
