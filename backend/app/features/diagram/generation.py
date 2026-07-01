"""Diagram question generator.

Produces the next adapted diagram question via the kernel LLM gateway. Mirrors
:mod:`app.features.code.generation`: it goes through
:func:`app.core.llm.get_llm_with_tracing`, sets ``temperature`` on the LLM object
(generation runs at 0.7), parses Kimi K2's list content with the ``reversed()``
pattern, and records the call via :func:`app.core.metrics.record_llm_call`.

The generator reads ``contract.difficulty`` and ``contract.focus_dimension`` from
the shared :class:`~app.shared.schemas.memory.AdaptiveContract`.
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
from app.shared.schemas.memory import AdaptiveContract

logger = get_logger(__name__)

_ALLOWED_DIAGRAM_TYPES = {"flowchart", "sequence", "er_diagram", "class_diagram"}
_ALLOWED_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
_ALLOWED_DIMENSIONS = {"thinking", "soft", "work", "digital_ai", "growth"}

_SYSTEM_PROMPT = (
    "You are an expert assessment designer for diagramming skills. "
    "Generate exactly ONE diagram question for an adaptive assessment. "
    "Return ONLY valid JSON — no markdown fences, no preamble, no explanation."
)


def _build_prompt(
    contract: AdaptiveContract,
    admin_context: str,
    prior_questions: list[str],
) -> str:
    """Build the diagram generation prompt.

    Args:
        contract: Adaptive contract carrying difficulty and focus dimension.
        admin_context: Assessment title + description for topic relevance.
        prior_questions: Previously asked question texts to avoid repeating.

    Returns:
        The fully rendered prompt string.
    """
    focus = contract.focus_dimension or "thinking"
    avoid = (
        "\n".join(f"- {q}" for q in prior_questions)
        if prior_questions
        else "(none yet)"
    )
    return (
        f"Assessment context: {admin_context}\n"
        f"Difficulty: {contract.difficulty}\n"
        f"Target skill dimension: {focus}\n"
        f"Avoid repeating or paraphrasing these prior questions:\n{avoid}\n\n"
        "The question asks the learner to draw or describe a diagram. Choose a "
        "diagram_type from: flowchart, sequence, er_diagram, class_diagram.\n\n"
        "Return JSON only, exactly this shape:\n"
        "{\n"
        '  "question_text": "string — what the learner must diagram",\n'
        '  "diagram_type": "flowchart|sequence|er_diagram|class_diagram",\n'
        '  "difficulty": "beginner|intermediate|advanced",\n'
        '  "dimension": "thinking|soft|work|digital_ai|growth"\n'
        "}"
    )


def _parse_response(raw_content: object) -> str:
    """Flatten an LLM response to a JSON string, stripping fences.

    Args:
        raw_content: The ``response.content`` (str or Kimi K2 list of blocks).

    Returns:
        The candidate JSON string with surrounding code fences removed.
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
    start = answer.find("{")
    end = answer.rfind("}")
    if start != -1 and end != -1 and end > start:
        return answer[start : end + 1]
    return answer


async def generate_diagram_question(
    contract: AdaptiveContract,
    admin_context: str,
    prior_questions: list[str] | None = None,
) -> dict:
    """Generate one diagram question at the contract's difficulty.

    Args:
        contract: Adaptive contract with difficulty and ``focus_dimension``.
        admin_context: Assessment title + description for topic relevance.
        prior_questions: Prior question texts for deduplication.

    Returns:
        A dict with keys ``question_text``, ``diagram_type`` (one of flowchart /
        sequence / er_diagram / class_diagram), ``difficulty``, ``dimension``.

    Raises:
        ValueError: If the LLM returns an unparseable response.
    """
    settings = get_settings()
    model = settings.LITELLM_MODEL
    llm, callbacks = get_llm_with_tracing(model)
    # Generation runs at 0.7 — set on the object (ainvoke ignores temperature).
    if hasattr(llm, "temperature"):
        llm.temperature = 0.7

    prompt = _build_prompt(contract, admin_context, prior_questions or [])

    start = time.perf_counter()
    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ],
            config=llm_invoke_config(
                callbacks,
                trace=LangfuseTraceContext(
                    session_id=getattr(contract, "session_id", None),
                    operation="diagram_generation",
                    tool="diagram",
                    question_index=getattr(contract, "question_index", None),
                ),
            ),
        )
        record_llm_call(
            model, "diagram_generation", "success", time.perf_counter() - start
        )
    except Exception:
        record_llm_call(
            model, "diagram_generation", "error", time.perf_counter() - start
        )
        raise

    json_text = _parse_response(response.content)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "diagram_generation_parse_failed", error=str(exc), raw=json_text[:200]
        )
        raise ValueError(
            f"Diagram generator returned unparseable JSON: {exc}"
        ) from exc

    diagram_type = str(data.get("diagram_type", "")).strip().lower()
    if diagram_type not in _ALLOWED_DIAGRAM_TYPES:
        diagram_type = "flowchart"

    difficulty = str(data.get("difficulty", "")).strip().lower()
    if difficulty not in _ALLOWED_DIFFICULTIES:
        difficulty = contract.difficulty

    dimension = str(data.get("dimension", "")).strip().lower()
    if dimension not in _ALLOWED_DIMENSIONS:
        dimension = contract.focus_dimension or "thinking"

    question_text = str(data.get("question_text", "")).strip()
    if not question_text:
        raise ValueError("Diagram generator returned an empty question_text")

    logger.info(
        "diagram_question_generated",
        difficulty=difficulty,
        dimension=dimension,
        diagram_type=diagram_type,
    )
    return {
        "question_text": question_text,
        "diagram_type": diagram_type,
        "difficulty": difficulty,
        "dimension": dimension,
    }


__all__ = ["generate_diagram_question"]
