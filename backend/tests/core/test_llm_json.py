"""Unit tests for shared LLM JSON helpers."""

import json

from app.core.llm_json import (
    extract_json,
    extract_llm_text,
    parse_llm_json,
    prefers_raw_json_model,
    resolve_vision_model,
)


def test_extract_json_handles_trailing_prose():
    raw = 'note {"score": 0.8, "feedback": "ok"} trailing text'
    assert json.loads(extract_json(raw)) == {"score": 0.8, "feedback": "ok"}


def test_parse_llm_json_handles_trailing_prose():
    assert parse_llm_json('prefix {"score": 0.5, "feedback": "x"} suffix') == {
        "score": 0.5,
        "feedback": "x",
    }


def test_extract_json_handles_markdown_fence():
    raw = '```json\n{"score": 0.8, "feedback": "ok"}\n```'
    assert json.loads(extract_json(raw)) == {"score": 0.8, "feedback": "ok"}


def test_extract_llm_text_skips_reasoning_blocks():
    blocks = [
        {"type": "reasoning", "text": "thinking..."},
        {"type": "text", "text": '{"score": 1.0}'},
    ]
    assert extract_llm_text(blocks) == '{"score": 1.0}'


def test_parse_llm_json_from_block_content():
    blocks = [{"type": "text", "text": 'prefix {"score": 0.5} suffix'}]
    assert parse_llm_json(blocks) == {"score": 0.5}


def test_prefers_raw_json_model_for_kimi():
    assert prefers_raw_json_model("openai/FW-Kimi-K2.6") is True
    assert prefers_raw_json_model("gpt-4o") is False


def test_resolve_vision_model_explicit_override():
    assert resolve_vision_model("custom/vision-model") == "custom/vision-model"
