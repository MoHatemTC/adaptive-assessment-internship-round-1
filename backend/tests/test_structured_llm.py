"""Tests for structured LLM content extraction."""

from app.structured_llm import extract_llm_text


def test_extract_llm_text_from_string():
    assert extract_llm_text('{"ok": true}') == '{"ok": true}'


def test_extract_llm_text_from_text_blocks():
    content = [
        {"type": "thinking", "thinking": "reasoning..."},
        {"type": "text", "text": '{"challenges": []}'},
    ]
    assert extract_llm_text(content) == '{"challenges": []}'


def test_extract_llm_text_falls_back_to_thinking():
    content = [{"type": "thinking", "thinking": '{"ok": true}'}]
    assert extract_llm_text(content) == '{"ok": true}'
