"""LLM-based MCQ generation.

This module generates the next MCQ using the platform LiteLLM gateway.
The generated question is stored in the MCQ tables before being returned.

Unified schema alignment:
- mcq_questions stores difficulty and dimension.
- topic/focus is generation context only and is not stored on mcq_questions.
- difficulty values are beginner / intermediate / advanced.
"""

import json
import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm import get_llm_with_tracing
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.features.mcq.service import create_question

_logger = get_logger(__name__)

_ALLOWED_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
_ALLOWED_DIMENSIONS = {"Thinking", "Soft", "Work", "Digital/AI", "Growth"}


def _build_mcq_generation_prompt(
    next_plan: Dict[str, Any],
    learner_profile: Dict[str, Any] | None = None,
    admin_config: Dict[str, Any] | None = None,
) -> str:
    """Build a strict prompt for generating one schema-aligned MCQ."""
    return f"""
Generate exactly ONE multiple-choice question for an adaptive assessment.

Next MCQ plan:
{json.dumps(next_plan, ensure_ascii=False)}

Learner profile:
{json.dumps(learner_profile or {}, ensure_ascii=False)}

Admin / blueprint configuration:
{json.dumps(admin_config or {}, ensure_ascii=False)}

Rules:
- The question must match next_dimension, next_focus, and next_difficulty.
- Difficulty must be one of: beginner, intermediate, advanced.
- Dimension must be one of: Thinking, Soft, Work, Digital/AI, Growth.
- The question must assess practical ability, not memorization only.
- Generate exactly 4 options.
- Each option must have a short label: A, B, C, D.
- Exactly one option must be correct.
- Do not include explanations.
- Do not include markdown.
- Return valid JSON only.

JSON format:
{{
  "question_text": "string",
  "difficulty": "beginner|intermediate|advanced",
  "dimension": "Thinking|Soft|Work|Digital/AI|Growth",
  "correct_option": "A|B|C|D",
  "options": [
    {{"label": "A", "text": "string"}},
    {{"label": "B", "text": "string"}},
    {{"label": "C", "text": "string"}},
    {{"label": "D", "text": "string"}}
  ]
}}
""".strip()


def _extract_json_from_llm_response(content: Any) -> Dict[str, Any]:
    """Parse JSON from an LLM response."""
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


def _validate_generated_mcq(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the generated MCQ payload."""
    required_fields = [
        "question_text",
        "difficulty",
        "dimension",
        "correct_option",
        "options",
    ]

    for field in required_fields:
        if field not in data:
            raise ValueError(f"Generated MCQ is missing required field: {field}")

    options = data["options"]

    if not isinstance(options, list) or len(options) != 4:
        raise ValueError("Generated MCQ must contain exactly 4 options")

    labels = [str(option.get("label", "")).strip().upper() for option in options]

    if labels != ["A", "B", "C", "D"]:
        raise ValueError("Generated MCQ option labels must be A, B, C, D")

    correct_option = str(data["correct_option"]).strip().upper()

    if correct_option not in labels:
        raise ValueError("Generated correct_option must match one option label")

    normalized_options: List[Dict[str, str]] = []

    for option in options:
        normalized_options.append(
            {
                "label": str(option["label"]).strip().upper(),
                "text": str(option["text"]).strip(),
            }
        )

    difficulty = str(data["difficulty"]).strip().lower()

    if difficulty not in _ALLOWED_DIFFICULTIES:
        difficulty = "beginner"

    dimension = str(data["dimension"]).strip()

    if dimension not in _ALLOWED_DIMENSIONS:
        dimension = "Thinking"

    return {
        "question_text": str(data["question_text"]).strip(),
        "difficulty": difficulty,
        "dimension": dimension,
        "correct_option": correct_option,
        "options": normalized_options,
    }


async def generate_and_store_next_mcq(
    db: AsyncSession,
    next_plan: Dict[str, Any],
    learner_profile: Dict[str, Any] | None = None,
    admin_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Generate the next MCQ using LiteLLM and store it in the database."""
    prompt = _build_mcq_generation_prompt(
        next_plan=next_plan,
        learner_profile=learner_profile,
        admin_config=admin_config,
    )

    llm, callbacks = get_llm_with_tracing()
    model_name = getattr(llm, "model", "unknown")

    messages = [
        SystemMessage(
            content=(
                "You are an examiner agent that generates safe, valid, "
                "single-answer multiple-choice questions for adaptive assessment."
            )
        ),
        HumanMessage(content=prompt),
    ]

    start_time = time.perf_counter()

    try:
        response = await llm.ainvoke(messages, config={"callbacks": callbacks})
        duration = time.perf_counter() - start_time

        record_llm_call(
            model=model_name,
            tool="mcq_generation",
            status="success",
            duration=duration,
        )
    except Exception:
        duration = time.perf_counter() - start_time

        record_llm_call(
            model=model_name,
            tool="mcq_generation",
            status="error",
            duration=duration,
        )

        raise

    generated_data = _extract_json_from_llm_response(response.content)
    validated_data = _validate_generated_mcq(generated_data)

    _logger.info(
        "mcq_generated_using_llm",
        difficulty=validated_data["difficulty"],
        dimension=validated_data["dimension"],
    )

    return await create_question(
        db=db,
        question_text=validated_data["question_text"],
        correct_option=validated_data["correct_option"],
        options=validated_data["options"],
        difficulty=validated_data["difficulty"],
        dimension=validated_data["dimension"],
    )
