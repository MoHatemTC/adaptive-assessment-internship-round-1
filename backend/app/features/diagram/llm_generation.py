"""LLM-based SVG diagram question generation."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import llm as llm_gateway
from app.core.llm import llm_invoke_config
from app.core.tracing import LangfuseTraceContext
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.features.diagram.service import create_question

_logger = get_logger(__name__)

_ALLOWED_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
_ALLOWED_DIMENSIONS = {"thinking", "soft", "work", "digital_ai", "growth"}


def _build_diagram_generation_prompt(
    next_plan: Dict[str, Any],
    learner_profile: Dict[str, Any] | None = None,
    admin_config: Dict[str, Any] | None = None,
) -> str:
    cv_context = (learner_profile or {}).get("cv_context", {})
    if cv_context:
        cv_hint = f"""
Candidate background from CV:
- Current role: {cv_context.get('current_role', 'unknown')}
- Experience: {cv_context.get('experience_years', 0)} years
- Key skills: {', '.join(cv_context.get('skills', [])[:5])}
- Technologies: {', '.join(cv_context.get('technologies', [])[:5])}
- Summary: {cv_context.get('cv_summary', '')}

Use this context to calibrate question difficulty and topic relevance.
"""
    else:
        cv_hint = ""

    return f"""
Generate exactly ONE SVG diagram question for an adaptive assessment.

Next diagram plan:
{json.dumps(next_plan, ensure_ascii=False)}

Learner profile:
{json.dumps(learner_profile or {}, ensure_ascii=False)}

Admin / blueprint configuration:
{json.dumps(admin_config or {}, ensure_ascii=False)}
{cv_hint}
Rules:
- The question must match the adaptive context.
- Difficulty must be one of: beginner, intermediate, advanced.
- Dimension must be one of: thinking, soft, work, digital_ai, growth.
- Generate a valid, self-contained SVG (no external imports, no <image> tags).
- The SVG must represent a real system architecture, data flow, or network diagram.
- All component boxes/nodes must have a human-readable label — except exactly one node which must be labeled with [?] (a literal question mark in brackets).
- Use <rect> elements for nodes, <line> or <path> elements for edges, and <text> elements for labels. Set width="600" height="400" on the root SVG.
- The [?] node must be visually distinct: use fill="#FFB300" and a dashed stroke-dasharray="6,3" border so learners immediately see which node is blank.
- The diagram must make sense without the missing label — surrounding nodes must give enough context for the learner to infer the answer.
- Return valid JSON only. Do not include markdown.

JSON format:
{{
  "svg_content": "<svg ...>...</svg>",
  "prompt": "What is the blank component labeled [?] in this diagram?",
  "correct_label": "Load Balancer",
  "rubric": "Accept: load balancer, LB, reverse proxy. Reject: router, firewall, CDN.",
  "difficulty": "beginner|intermediate|advanced",
  "dimension": "thinking|soft|work|digital_ai|growth"
}}
""".strip()


def _extract_json_from_llm_response(content: Any) -> Dict[str, Any]:
    """Parse a JSON object out of an LLM response.

    Handles Kimi K2's list-of-blocks content shape and stray code fences.

    Args:
        content: The ``response.content`` returned by the LLM.

    Returns:
        The parsed JSON object as a dict.

    Raises:
        ValueError: If no JSON object can be located in the response.
    """
    if isinstance(content, list):
        text_parts: List[str] = []

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")

                if block_type == "text" and block.get("text"):
                    text_parts.append(str(block["text"]))
                elif block_type not in {"thinking", "reasoning"}:
                    possible_text = block.get("text") or block.get("content") or ""
                    if possible_text:
                        text_parts.append(str(possible_text))
            else:
                text_parts.append(str(block))

        cleaned = "\n".join(text_parts).strip()
    else:
        cleaned = str(content).strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    start_index = cleaned.find("{")
    end_index = cleaned.rfind("}")

    if start_index == -1 or end_index == -1:
        raise ValueError("LLM response does not contain a valid JSON object")

    json_text = cleaned[start_index : end_index + 1]
    return json.loads(json_text)


def _strip_svg_fences(svg_content: str) -> str:
    cleaned = str(svg_content).strip()
    if cleaned.startswith("```svg"):
        cleaned = cleaned.removeprefix("```svg").strip()
    if cleaned.startswith("```xml"):
        cleaned = cleaned.removeprefix("```xml").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def _validate_generated_diagram(data: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = [
        "svg_content",
        "prompt",
        "correct_label",
        "rubric",
        "difficulty",
        "dimension",
    ]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Generated diagram is missing required field: {field}")

    svg_content = _strip_svg_fences(str(data["svg_content"]))
    if "[?]" not in svg_content:
        raise ValueError("Generated diagram SVG must contain [?] blank marker")
    if not svg_content.strip().lower().startswith("<svg"):
        raise ValueError("Generated diagram svg_content must start with <svg")

    difficulty = str(data["difficulty"]).strip().lower()
    if difficulty not in _ALLOWED_DIFFICULTIES:
        difficulty = "beginner"

    dimension = str(data["dimension"]).strip().lower()
    if dimension not in _ALLOWED_DIMENSIONS:
        dimension = "thinking"

    return {
        "svg_content": svg_content,
        "prompt": str(data["prompt"]).strip(),
        "correct_label": str(data["correct_label"]).strip(),
        "rubric": str(data["rubric"]).strip(),
        "difficulty": difficulty,
        "dimension": dimension,
    }


async def generate_and_store_next_diagram(
    db: AsyncSession,
    next_plan: Dict[str, Any],
    learner_profile: Dict[str, Any] | None = None,
    admin_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    prompt = _build_diagram_generation_prompt(
        next_plan=next_plan,
        learner_profile=learner_profile,
        admin_config=admin_config,
    )
    llm, callbacks = llm_gateway.get_llm_with_tracing()
    model_name = getattr(llm, "model", "unknown")
    messages = [
        SystemMessage(
            content=(
                "You are an examiner agent that generates safe, valid SVG diagram "
                "questions for adaptive assessment."
            )
        ),
        HumanMessage(content=prompt),
    ]

    start_time = time.perf_counter()
    try:
        response = await llm.ainvoke(
            messages,
            config=llm_invoke_config(
                callbacks,
                trace=LangfuseTraceContext(
                    session_id=next_plan.get("session_id"),
                    operation="diagram_generation",
                    tool="diagram",
                    question_index=next_plan.get("question_index"),
                ),
            ),
        )
        duration = time.perf_counter() - start_time
        record_llm_call(
            model=model_name,
            tool="diagram_generation",
            status="success",
            duration=duration,
        )
    except Exception:
        duration = time.perf_counter() - start_time
        record_llm_call(
            model=model_name,
            tool="diagram_generation",
            status="error",
            duration=duration,
        )
        raise

    generated_data = _extract_json_from_llm_response(response.content)
    validated = _validate_generated_diagram(generated_data)

    _logger.info(
        "diagram_generated_using_llm",
        difficulty=validated["difficulty"],
        dimension=validated["dimension"],
    )

    return await create_question(
        db=db,
        svg_content=validated["svg_content"],
        prompt=validated["prompt"],
        correct_label=validated["correct_label"],
        rubric=validated["rubric"],
        difficulty=validated["difficulty"],
        dimension=validated["dimension"],
    )
