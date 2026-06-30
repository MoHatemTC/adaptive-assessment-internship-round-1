"""Generator Agent — LLM-authored coding challenges from an adaptive contract."""

from __future__ import annotations

import json
import uuid

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.core.llm import get_llm_with_tracing, llm_invoke_config
from app.core.tracing import LangfuseTraceContext
from app.core.logging import get_logger
from app.features.code.llm_json import (
    extract_json as _extract_json,
    extract_llm_text as _extract_llm_text,
    prefers_raw_json_model,
)
from app.features.code.grading import LLMGradingUnavailable, _is_llm_unavailable
from app.features.code.languages import (
    SupportedLanguage,
    generator_retry_prompt,
    generator_starter_description,
    generator_system_prompt,
    generator_test_case_description,
    normalize_language,
)
from app.shared.schemas.memory import AdaptiveContract, DifficultyLevel, DimensionName

_logger = get_logger(__name__)

# Kimi emits long reasoning chains; 1536 tokens often never reaches the JSON answer.
_GENERATION_MAX_TOKENS = 4096
_RAW_GENERATION_ATTEMPTS = 3

_FOCUS_HINTS: dict[DimensionName, str] = {
    "thinking": "algorithmic reasoning, edge cases, and problem decomposition",
    "work": "practical data processing and clear maintainable logic",
    "digital_ai": "structured data transformation and automation-style tasks",
    "soft": "readable code and sensible naming",
    "growth": "iterative improvement and learning-oriented tasks",
}

_DIFFICULTY_HINTS: dict[DifficultyLevel, str] = {
    "beginner": "a single-function exercise solvable in under 15 lines",
    "intermediate": "moderate logic with one core insight (hash map, two pointers, etc.)",
    "advanced": "multi-step reasoning; still one self-contained function",
}


class GeneratedTestCase(BaseModel):
    input: str
    expected_output: str
    is_hidden: bool = False


class GeneratedChallengeSpec(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20)
    starter_code: str
    test_cases: list[GeneratedTestCase] = Field(min_length=3, max_length=6)

    @classmethod
    def model_json_schema_for_language(cls, language: str | None) -> dict:
        """Build a schema hint with language-specific field descriptions."""
        schema = cls.model_json_schema()
        props = schema.get("properties", {})
        if "starter_code" in props:
            props["starter_code"]["description"] = generator_starter_description(language)
        test_case_schema = props.get("test_cases", {}).get("items", {})
        if "input" in test_case_schema.get("properties", {}):
            test_case_schema["properties"]["input"]["description"] = (
                generator_test_case_description(language)
            )
        return schema


def _build_generator_prompt(
    *,
    contract: AdaptiveContract,
    assessment_id: str,
    language: SupportedLanguage,
    previous_titles: list[str],
) -> str:
    focus = contract.focus_dimension
    focus_hint = _FOCUS_HINTS.get(focus, "core programming skills") if focus else "core programming skills"
    avoid = ", ".join(previous_titles) if previous_titles else "(none yet)"
    nonce = uuid.uuid4().hex[:10]
    return (
        f"Assessment: {assessment_id}\n"
        f"Session: {contract.session_id}\n"
        f"Unique nonce: {nonce} — invent a fresh problem unrelated to prior sessions.\n"
        f"Language: {language}\n"
        f"Question index: {contract.question_index}\n"
        f"Difficulty: {contract.difficulty} — {_DIFFICULTY_HINTS[contract.difficulty]}\n"
        f"Focus dimension: {focus or 'general'} — emphasise {focus_hint}\n"
        f"Learner context: {contract.memory_summary}\n"
        f"Avoid repeating these titles: {avoid}\n\n"
        "Write the next challenge now."
    )


def _prefers_raw_json_generation(model: str) -> bool:
    return prefers_raw_json_model(model)


async def _generate_challenge_spec_raw(
    *,
    llm,
    callbacks,
    messages: list[tuple[str, str]],
    contract: AdaptiveContract,
    lang: str,
) -> GeneratedChallengeSpec:
    schema_hint = json.dumps(
        GeneratedChallengeSpec.model_json_schema_for_language(lang),
        separators=(",", ":"),
    )
    attempt_messages = [
        *messages,
        (
            "human",
            "Return ONLY valid JSON matching this schema. No markdown fences, "
            "no reasoning, no prose.\n"
            f"{schema_hint}",
        ),
    ]
    bound = llm.bind(max_tokens=_GENERATION_MAX_TOKENS)
    last_error: Exception | None = None

    for attempt in range(_RAW_GENERATION_ATTEMPTS):
        try:
            response = await bound.ainvoke(
                attempt_messages,
                config=llm_invoke_config(
                    callbacks,
                    trace=LangfuseTraceContext(
                        session_id=contract.session_id,
                        operation="code_generation",
                        tool="coding",
                        question_index=contract.question_index,
                    ),
                ),
            )
            content = _extract_llm_text(response.content)
            spec = GeneratedChallengeSpec.model_validate_json(_extract_json(content))
            _logger.info(
                "code_challenge_generated_raw",
                session_id=contract.session_id,
                question_index=contract.question_index,
                title=spec.title,
                difficulty=contract.difficulty,
                language=lang,
                attempt=attempt + 1,
            )
            return spec
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            _logger.warning(
                "code_challenge_generation_parse_failed",
                attempt=attempt + 1,
                language=lang,
                error=str(exc),
            )
            attempt_messages.append(("human", generator_retry_prompt(lang)))

    raise RuntimeError("LLM challenge generation failed after retries") from last_error


async def generate_challenge_spec(
    *,
    contract: AdaptiveContract,
    assessment_id: str,
    language: str | None = "python",
    previous_titles: list[str] | None = None,
) -> GeneratedChallengeSpec:
    """Ask the LLM for a challenge spec matching the adaptive contract."""
    lang = normalize_language(language)
    llm, callbacks = get_llm_with_tracing()
    model = get_settings().LITELLM_MODEL
    messages: list[tuple[str, str]] = [
        ("system", generator_system_prompt(lang)),
        (
            "human",
            _build_generator_prompt(
                contract=contract,
                assessment_id=assessment_id,
                language=lang,
                previous_titles=previous_titles or [],
            ),
        ),
    ]

    if _prefers_raw_json_generation(model):
        try:
            return await _generate_challenge_spec_raw(
                llm=llm,
                callbacks=callbacks,
                messages=messages,
                contract=contract,
                lang=lang,
            )
        except RuntimeError:
            raise
        except Exception as exc:
            if _is_llm_unavailable(exc):
                raise LLMGradingUnavailable(
                    "LLM challenge generation is unavailable. Verify LITELLM_API_KEY, "
                    "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
                ) from exc
            raise RuntimeError("LLM challenge generation failed after retries") from exc

    structured = llm.with_structured_output(GeneratedChallengeSpec)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            result = await structured.ainvoke(
                messages,
                config=llm_invoke_config(
                    callbacks,
                    trace=LangfuseTraceContext(
                        session_id=contract.session_id,
                        operation="code_generation",
                        tool="coding",
                        question_index=contract.question_index,
                    ),
                ),
            )
            spec = (
                result
                if isinstance(result, GeneratedChallengeSpec)
                else GeneratedChallengeSpec.model_validate(result)
            )
            _logger.info(
                "code_challenge_generated",
                session_id=contract.session_id,
                question_index=contract.question_index,
                title=spec.title,
                difficulty=contract.difficulty,
                language=lang,
            )
            return spec
        except (OutputParserException, ValidationError) as exc:
            last_error = exc
            _logger.warning(
                "code_challenge_generation_parse_failed",
                attempt=attempt + 1,
                language=lang,
                error=str(exc),
            )
            messages.append(("human", generator_retry_prompt(lang)))
        except Exception as exc:
            if _is_llm_unavailable(exc):
                raise LLMGradingUnavailable(
                    "LLM challenge generation is unavailable. Verify LITELLM_API_KEY, "
                    "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
                ) from exc
            raise

    try:
        return await _generate_challenge_spec_raw(
            llm=llm,
            callbacks=callbacks,
            messages=messages,
            contract=contract,
            lang=lang,
        )
    except (ValidationError, json.JSONDecodeError) as exc:
        raise RuntimeError("LLM challenge generation failed after retries") from (
            last_error or exc
        )
    except Exception as exc:
        if _is_llm_unavailable(exc):
            raise LLMGradingUnavailable(
                "LLM challenge generation is unavailable. Verify LITELLM_API_KEY, "
                "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
            ) from exc
        raise RuntimeError("LLM challenge generation failed after retries") from exc


__all__ = ["GeneratedChallengeSpec", "generate_challenge_spec"]
