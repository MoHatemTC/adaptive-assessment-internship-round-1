"""LLM Challenge Generator — personalized challenges via kernel LiteLLM."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.challenges.defaults import DEFAULT_CHALLENGE_CONFIG
from app.challenges.fallback_templates import fallback_challenge_at_index
from app.challenges.language_profile import (
    assign_challenge_languages,
    language_labels,
    resolve_profile_languages,
)
from app.challenges.prompts import (
    build_adaptive_user_prompt,
    build_generator_system_prompt,
    build_generator_user_prompt,
)
from app.challenges.time_budget import allocate_fallback_times, normalize_challenge_times
from app.challenges.schemas import (
    ChallengeGenerationResult,
    GeneratedCodeChallenge,
    PlatformChallengeConfig,
    UserProfile,
)
from app.config import get_settings
from app.structured_llm import extract_llm_text, get_structured_llm_with_tracing
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.features.code.constants import SupportedLanguage, validate_language

from app.features.code.adaptive_schemas import AdaptationDecision

_logger = get_logger(__name__)
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_response(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def _fallback_challenges(
    profile: UserProfile,
    config: PlatformChallengeConfig,
) -> ChallengeGenerationResult:
    """Deterministic starter challenges when the LLM is unavailable."""
    count = max(1, config.challenge.challenges_per_candidate)
    profile_languages = resolve_profile_languages(profile, config)
    assignments = assign_challenge_languages(profile_languages, count)
    challenges = [
        fallback_challenge_at_index(index, language, profile, config)
        for index, language in enumerate(assignments)
    ]
    challenges = allocate_fallback_times(challenges, config)
    return ChallengeGenerationResult(
        challenges=challenges,
        generation_notes=(
            f"Fallback template (LLM unavailable). Languages: {language_labels(assignments)}."
        ),
    )


def _apply_language_plan(
    result: ChallengeGenerationResult,
    profile: UserProfile,
    config: PlatformChallengeConfig,
) -> ChallengeGenerationResult:
    """Coerce each generated challenge to the profile-driven language plan."""
    profile_languages = resolve_profile_languages(profile, config)
    assignments = assign_challenge_languages(profile_languages, len(result.challenges))
    coerced = [
        challenge.model_copy(update={"language": language})
        for challenge, language in zip(result.challenges, assignments, strict=False)
    ]
    notes = result.generation_notes.strip()
    suffix = f"Assigned languages: {language_labels(assignments)}."
    generation_notes = f"{notes} {suffix}".strip() if notes else suffix
    return result.model_copy(update={"challenges": coerced, "generation_notes": generation_notes})


def _finalize_generation(
    result: ChallengeGenerationResult,
    profile: UserProfile,
    config: PlatformChallengeConfig,
) -> ChallengeGenerationResult:
    count = config.challenge.challenges_per_candidate
    trimmed = result.model_copy(update={"challenges": result.challenges[:count]})
    with_languages = _apply_language_plan(trimmed, profile, config)
    return normalize_challenge_times(with_languages, config)


async def generate_code_challenges(
    profile: UserProfile,
    *,
    config: PlatformChallengeConfig | None = None,
    prior_performance_summary: str | None = None,
) -> ChallengeGenerationResult:
    """Generate personalized programming challenges from a user profile.

    Applies admin challenge settings and uses LiteLLM via the kernel gateway.
    Falls back to a template challenge when the LLM is unavailable.
    """
    gen_config = config or DEFAULT_CHALLENGE_CONFIG
    count = gen_config.challenge.challenges_per_request
    profile_languages = resolve_profile_languages(profile, gen_config)
    assigned_languages = assign_challenge_languages(profile_languages, count)
    settings = get_settings()

    if not settings.LITELLM_API_KEY.get_secret_value():
        return _finalize_generation(_fallback_challenges(profile, gen_config), profile, gen_config)

    llm, callbacks = get_structured_llm_with_tracing()
    model = settings.LITELLM_MODEL
    start = time.perf_counter()

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content=build_generator_system_prompt(
                        gen_config,
                        profile_languages=profile_languages,
                    )
                ),
                HumanMessage(
                    content=build_generator_user_prompt(
                        profile,
                        count=count,
                        profile_languages=profile_languages,
                        assigned_languages=assigned_languages,
                        prior_performance_summary=prior_performance_summary,
                    )
                ),
            ],
            config={"callbacks": callbacks},
        )
        record_llm_call(model, "challenge_generator", "success", time.perf_counter() - start)
    except Exception as exc:  # noqa: BLE001
        record_llm_call(model, "challenge_generator", "error", time.perf_counter() - start)
        _logger.warning("challenge_generation_failed", error=str(exc))
        return _finalize_generation(_fallback_challenges(profile, gen_config), profile, gen_config)

    raw = extract_llm_text(response.content)
    parsed = _parse_json_response(raw)
    if not parsed or "challenges" not in parsed:
        _logger.warning("challenge_generation_unparseable", raw=raw[:300])
        return _finalize_generation(_fallback_challenges(profile, gen_config), profile, gen_config)

    try:
        result = ChallengeGenerationResult.model_validate(parsed)
        return _finalize_generation(result, profile, gen_config)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("challenge_generation_invalid_shape", error=str(exc))
        return _finalize_generation(_fallback_challenges(profile, gen_config), profile, gen_config)


def _single_challenge_fallback(
    profile: UserProfile,
    config: PlatformChallengeConfig,
    decision: AdaptationDecision,
) -> GeneratedCodeChallenge:
    language = validate_language(decision.next_language)
    challenge = fallback_challenge_at_index(0, language, profile, config)
    return challenge.model_copy(
        update={
            "difficulty": decision.next_difficulty,
            "category": decision.next_category,
            "language": language,
        }
    )


async def generate_single_adaptive_challenge(
    profile: UserProfile,
    config: PlatformChallengeConfig,
    decision: AdaptationDecision,
) -> GeneratedCodeChallenge:
    """Generate one adapted challenge for the next loop turn."""
    profile_languages = resolve_profile_languages(profile, config)
    settings = get_settings()
    gen_config = config.model_copy(
        update={
            "challenge": config.challenge.model_copy(update={"challenges_per_candidate": 1}),
        }
    )

    if not settings.LITELLM_API_KEY.get_secret_value():
        challenge = _single_challenge_fallback(profile, gen_config, decision)
        normalized = normalize_challenge_times(
            ChallengeGenerationResult(challenges=[challenge], generation_notes="Fallback adaptive."),
            gen_config,
        )
        return normalized.challenges[0]

    llm, callbacks = get_structured_llm_with_tracing()
    model = settings.LITELLM_MODEL
    start = time.perf_counter()
    language = validate_language(decision.next_language)

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content=build_generator_system_prompt(
                        gen_config,
                        profile_languages=profile_languages,
                    )
                ),
                HumanMessage(
                    content=build_adaptive_user_prompt(
                        profile,
                        decision=decision,
                        profile_languages=profile_languages,
                    )
                ),
            ],
            config={"callbacks": callbacks},
        )
        record_llm_call(model, "adaptive_challenge_generator", "success", time.perf_counter() - start)
    except Exception as exc:  # noqa: BLE001
        record_llm_call(model, "adaptive_challenge_generator", "error", time.perf_counter() - start)
        _logger.warning("adaptive_challenge_generation_failed", error=str(exc))
        return _single_challenge_fallback(profile, gen_config, decision)

    raw = extract_llm_text(response.content)
    parsed = _parse_json_response(raw)
    if not parsed or "challenges" not in parsed:
        return _single_challenge_fallback(profile, gen_config, decision)

    try:
        result = ChallengeGenerationResult.model_validate(parsed)
        if not result.challenges:
            return _single_challenge_fallback(profile, gen_config, decision)
        challenge = result.challenges[0].model_copy(
            update={
                "difficulty": decision.next_difficulty,
                "category": decision.next_category,
                "language": language,
            }
        )
        normalized = normalize_challenge_times(
            ChallengeGenerationResult(challenges=[challenge], generation_notes=result.generation_notes),
            gen_config,
        )
        return normalized.challenges[0]
    except Exception as exc:  # noqa: BLE001
        _logger.warning("adaptive_challenge_invalid_shape", error=str(exc))
        return _single_challenge_fallback(profile, gen_config, decision)

