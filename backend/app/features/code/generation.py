"""Generator Agent — LLM-authored coding challenges from an adaptive contract."""

from __future__ import annotations

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field, ValidationError

from app.core.llm import get_llm_with_tracing
from app.core.logging import get_logger
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
    return (
        f"Assessment: {assessment_id}\n"
        f"Language: {language}\n"
        f"Question index: {contract.question_index}\n"
        f"Difficulty: {contract.difficulty} — {_DIFFICULTY_HINTS[contract.difficulty]}\n"
        f"Focus dimension: {focus or 'general'} — emphasise {focus_hint}\n"
        f"Learner context: {contract.memory_summary}\n"
        f"Avoid repeating these titles: {avoid}\n\n"
        "Write the next challenge now."
    )


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
    structured = llm.bind(streaming=False).with_structured_output(GeneratedChallengeSpec)
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

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            result = await structured.ainvoke(messages, config={"callbacks": callbacks})
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

    raise RuntimeError("LLM challenge generation failed after retries") from last_error


__all__ = ["GeneratedChallengeSpec", "generate_challenge_spec"]
