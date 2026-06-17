"""Generator Agent — LLM-authored coding challenges from an adaptive contract."""

from __future__ import annotations

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field, ValidationError

from app.core.llm import get_llm_with_tracing
from app.core.logging import get_logger
from app.features.code.grading import LLMGradingUnavailable, _is_llm_unavailable
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
    input: str = Field(
        description="Executable Python that calls solution(...), e.g. print(solution('hi'))"
    )
    expected_output: str
    is_hidden: bool = False


class GeneratedChallengeSpec(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20)
    starter_code: str = Field(
        description="Python starter with def solution(...) and a TODO body"
    )
    test_cases: list[GeneratedTestCase] = Field(min_length=3, max_length=6)


_GENERATOR_SYSTEM_PROMPT = (
    "You are an expert coding-assessment author. Produce ONE original Python "
    "challenge for a learner.\n\n"
    "Rules:\n"
    "- Define exactly one entry point: def solution(...)\n"
    "- starter_code must include that function with a TODO/pass body\n"
    "- Every test case input MUST be valid Python that calls solution, "
    "typically print(solution(...))\n"
    "- expected_output is the stdout the sandbox expects (no trailing newline)\n"
    "- Include at least 2 visible tests (is_hidden=false) and at least 1 hidden test\n"
    "- Do not reuse titles from the avoid list\n"
    "- Keep problems fair and self-contained — no imports beyond the standard library\n"
    "- Return JSON matching the schema exactly"
)

_RETRY_PROMPT = (
    "Invalid challenge spec. Ensure test inputs are executable Python like "
    "print(solution('abc')), include hidden and visible tests, and use def solution(...)."
)


def _build_generator_prompt(
    *,
    contract: AdaptiveContract,
    assessment_id: str,
    previous_titles: list[str],
) -> str:
    focus = contract.focus_dimension
    focus_hint = _FOCUS_HINTS.get(focus, "core programming skills") if focus else "core programming skills"
    avoid = ", ".join(previous_titles) if previous_titles else "(none yet)"
    return (
        f"Assessment: {assessment_id}\n"
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
    previous_titles: list[str] | None = None,
) -> GeneratedChallengeSpec:
    """Ask the LLM for a challenge spec matching the adaptive contract."""
    llm, callbacks = get_llm_with_tracing()
    structured = llm.bind(streaming=False).with_structured_output(GeneratedChallengeSpec)
    messages: list[tuple[str, str]] = [
        ("system", _GENERATOR_SYSTEM_PROMPT),
        (
            "human",
            _build_generator_prompt(
                contract=contract,
                assessment_id=assessment_id,
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
            )
            return spec
        except (OutputParserException, ValidationError) as exc:
            last_error = exc
            _logger.warning(
                "code_challenge_generation_parse_failed",
                attempt=attempt + 1,
                error=str(exc),
            )
            messages.append(("human", _RETRY_PROMPT))
        except Exception as exc:
            if _is_llm_unavailable(exc):
                raise LLMGradingUnavailable(
                    "LLM challenge generation is unavailable. Verify LITELLM_API_KEY, "
                    "LITELLM_BASE_URL, and LITELLM_MODEL in the backend environment."
                ) from exc
            raise

    raise RuntimeError("LLM challenge generation failed after retries") from last_error


__all__ = ["GeneratedChallengeSpec", "generate_challenge_spec"]
