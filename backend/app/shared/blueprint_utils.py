"""Helpers for reading planner blueprint limits shared across tool loops."""

from __future__ import annotations

from typing import Any


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _section(data: dict[str, Any], *names: str) -> dict[str, Any]:
    for name in names:
        value = data.get(name)
        if isinstance(value, dict):
            return value
    return {}


def tool_question_count(
    blueprint: dict[str, Any],
    tool: str,
    *,
    legacy_keys: tuple[str, ...] = (),
) -> int | None:
    tools = blueprint.get("tools")
    if isinstance(tools, dict):
        cfg = tools.get(tool)
        if isinstance(cfg, dict):
            count = _optional_int(cfg.get("question_count"))
            if count is not None:
                return max(0, count)

    for key in legacy_keys:
        section = _section(blueprint, key)
        count = _optional_int(section.get("question_count")) or _optional_int(
            section.get("max_questions")
        )
        if count is not None:
            return max(0, count)

    return None


#: Per-question learner budget when blueprint omits ``time_limit_seconds`` for code.
DEFAULT_CODE_QUESTION_TIME_SECONDS = 600


def tool_time_limit_seconds(
    blueprint: dict[str, Any],
    tool: str,
    *,
    default: int | None = None,
) -> int | None:
    """Return per-question time budget from blueprint ``tools.<tool>.time_limit_seconds``."""
    tools = blueprint.get("tools")
    if isinstance(tools, dict):
        cfg = tools.get(tool)
        if isinstance(cfg, dict):
            count = _optional_int(cfg.get("time_limit_seconds"))
            if count is not None and count > 0:
                return count
    return default


def session_time_limit_seconds(blueprint: dict[str, Any]) -> int | None:
    """Return whole-sitting time budget from blueprint ``session_time_limit_seconds``."""
    count = _optional_int(blueprint.get("session_time_limit_seconds"))
    if count is not None and count > 0:
        return count
    return None


__all__ = [
    "DEFAULT_CODE_QUESTION_TIME_SECONDS",
    "session_time_limit_seconds",
    "tool_question_count",
    "tool_time_limit_seconds",
]
