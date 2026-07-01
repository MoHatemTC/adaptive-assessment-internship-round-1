"""Blueprint planner agent.

Converts an admin's free-text prompt plus the list of enabled tools into a
structured :class:`~app.shared.schemas.blueprint.Blueprint` via the kernel LLM
gateway. Mirrors the generator pattern in
:mod:`app.features.code.generation`: it goes through
:func:`app.core.llm.get_llm_with_tracing`, parses Kimi K2's list content with the
``reversed()`` pattern, and records the call via
:func:`app.core.metrics.record_llm_call`.

Blueprint generation is deterministic parsing, so the model runs at
``temperature=0.0`` (set on the LLM object, mirroring
:mod:`app.features.voice.adaptation`).
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.core.llm import get_llm_with_tracing, llm_invoke_config
from app.core.tracing import LangfuseTraceContext
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.shared.schemas.blueprint import Blueprint

logger = get_logger(__name__)

PLANNER_SYSTEM_PROMPT = """
You are an AI assessment architect. Given an admin's description and
the tools they want to enable, produce a structured JSON assessment blueprint.

Return ONLY valid JSON — no markdown fences, no explanation, no preamble.

Required JSON shape:
{
  "title": "string — concise assessment title",
  "description": "string — 1-2 sentence description",
  "tools": {
    "<tool>": {
      "enabled": bool,
      "question_count": int,
      "min_difficulty": "beginner|intermediate|advanced",
      "max_difficulty": "beginner|intermediate|advanced",
      "time_limit_seconds": null
    }
  },
  "skill_dimensions": ["thinking", "soft", "work", "digital_ai", "growth"],
  "total_questions": int,
  "session_time_limit_seconds": null
}

Include one "tools" entry per tool, keyed exactly: "mcq", "voice", "diagram",
"code". Use those exact keys — never "coding".

Rules:
- Only enable tools the admin explicitly requested.
- total_questions = sum of question_count for enabled tools only.
- min_difficulty must be <= max_difficulty (beginner < intermediate < advanced).
- skill_dimensions: non-empty subset of the five valid values.
- question_count per tool: 1-10.
- session_time_limit_seconds: optional whole-assessment sitting budget in seconds
  (e.g. 3600 for one hour). Use null when no global limit is needed.
- For each enabled tool set time_limit_seconds to the per-question learner budget
  in seconds (e.g. code 600, mcq 120, diagram 300, voice 180). Use null only when
  the tool should have no per-question timer.
- For voice: prefer 120-300 seconds per question when enabled.
""".strip()


def _parse_blueprint_content(raw_content: object) -> str:
    """Flatten an LLM response into a JSON string, stripping markdown fences.

    Kimi K2 returns a list of thinking blocks followed by the answer string;
    the ``reversed()`` walk finds the final answer.

    Args:
        raw_content: The ``response.content`` returned by the LLM (str or list).

    Returns:
        The candidate JSON string with any surrounding code fences removed.
    """
    answer = ""
    if isinstance(raw_content, list):
        for item in reversed(raw_content):
            if isinstance(item, str) and item.strip():
                answer = item.strip()
                break
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "").strip()
                if text:
                    answer = text
                    break
    else:
        answer = str(raw_content).strip()

    answer = answer.strip()
    if answer.startswith("```"):
        lines = answer.split("\n")
        answer = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()
    return answer


async def run_planner(
    admin_prompt: str,
    tools_enabled: list[str],
) -> Blueprint:
    """Generate a structured assessment blueprint from an admin's description.

    Args:
        admin_prompt: Free-text description of what the assessment should test.
        tools_enabled: Tool names to enable, e.g. ``["mcq", "voice"]``.

    Returns:
        A validated :class:`~app.shared.schemas.blueprint.Blueprint`.

    Raises:
        ValueError: If the LLM returns an unparseable or invalid blueprint.
    """
    settings = get_settings()
    model = settings.LITELLM_MODEL
    llm, callbacks = get_llm_with_tracing(model)
    # Deterministic parsing — set temperature on the object (ainvoke ignores it).
    if hasattr(llm, "temperature"):
        llm.temperature = 0.0

    user_message = (
        f"Admin description: {admin_prompt}\n"
        f"Enable these tools only: {', '.join(tools_enabled)}\n"
        f"Disable all other tools (set enabled: false, question_count: 0)."
    )

    start = time.perf_counter()
    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ],
            config=llm_invoke_config(
                callbacks,
                trace=LangfuseTraceContext(operation="planner"),
            ),
        )
        record_llm_call(model, "planner", "success", time.perf_counter() - start)
    except Exception:
        record_llm_call(model, "planner", "error", time.perf_counter() - start)
        raise

    answer = _parse_blueprint_content(response.content)

    try:
        data = json.loads(answer)
        blueprint = Blueprint.model_validate(data)
    except Exception as exc:
        logger.warning("planner_parse_failed", error=str(exc), raw=answer[:200])
        raise ValueError(
            f"Planner LLM returned unparseable blueprint: {exc}"
        ) from exc

    enabled_total = sum(
        cfg.question_count
        for cfg in blueprint.tools.values()
        if cfg.enabled and cfg.question_count > 0
    )
    if blueprint.total_questions != enabled_total:
        logger.warning(
            "planner_total_questions_adjusted",
            reported=blueprint.total_questions,
            computed=enabled_total,
        )
        blueprint = blueprint.model_copy(update={"total_questions": enabled_total})

    logger.info(
        "blueprint_generated",
        title=blueprint.title,
        tools=blueprint.enabled_tools(),
        total_questions=blueprint.total_questions,
    )
    return blueprint


__all__ = ["PLANNER_SYSTEM_PROMPT", "run_planner"]
