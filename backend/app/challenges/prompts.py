"""Prompt templates for LLM challenge generation."""

from app.challenges.language_profile import language_labels
from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from app.features.code.constants import SupportedLanguage
from app.features.code.languages.registry import get_language_runtime


def _language_rules_block(languages: list[SupportedLanguage]) -> str:
    sections: list[str] = []
    for language in languages:
        runtime = get_language_runtime(language)
        sections.append(
            f"""For {language.value} challenges:
- Set "language" to "{language.value}".
- Starter stub: {runtime.solution_module_export_hint}
- Each test case "input" must invoke solution and capture stdout, e.g. {runtime.legacy_test_example}
- expected_output is the stripped stdout string (booleans as True/False)."""
        )
    return "\n\n".join(sections)


def build_generator_system_prompt(
    config: PlatformChallengeConfig,
    *,
    profile_languages: list[SupportedLanguage],
) -> str:
    settings = config.challenge
    categories = ", ".join(settings.categories)
    difficulties = ", ".join(settings.difficulty_levels)
    total_seconds = settings.total_time_minutes * 60
    min_secs = settings.min_time_per_challenge_minutes * 60
    max_secs = settings.max_time_per_challenge_minutes * 60
    language_rules = _language_rules_block(profile_languages)

    return f"""You are the Challenge Generator for an adaptive assessment platform.
Users never create their own challenges — you generate them from their profile.

Domain: {settings.domain}
Allowed categories: {categories}
Allowed difficulty levels: {difficulties}
Complexity range: {settings.min_complexity}–{settings.max_complexity} (1=easiest)
Generate exactly {settings.challenges_per_candidate} challenge(s).

Profile languages (use these — one per challenge when multiple are listed): {language_labels(profile_languages)}

Time budget (admin):
- Total candidate working time across all challenges: {total_seconds} seconds ({settings.total_time_minutes} minutes)
- Per-challenge candidate_time_seconds: between {min_secs} and {max_secs} seconds
- Harder difficulty → more candidate_time_seconds; easier → less
- Sum of all candidate_time_seconds MUST NOT exceed {total_seconds}
- time_limit_seconds: E2B execution cap only (5–{settings.e2b_execution_timeout_seconds} seconds per run)

Programming challenge rules:
- Define a function named `solution` that learners implement (export appropriately per language).
- Include at least 2 visible and 1 hidden test case per challenge.

{language_rules}

Return ONLY valid JSON:
{{
  "challenges": [
    {{
      "title": "...",
      "difficulty": "...",
      "category": "...",
      "description": "...",
      "requirements": ["..."],
      "evaluation_criteria": ["correctness", "..."],
      "max_score": 100,
      "estimated_duration": "25 minutes",
      "candidate_time_seconds": 1500,
      "starter_code": "...",
      "language": "{profile_languages[0].value}",
      "time_limit_seconds": 30,
      "test_cases": [
        {{"input": "...", "expected_output": "...", "is_hidden": false, "weight": 1.0}}
      ]
    }}
  ],
  "generation_notes": "brief rationale for difficulty/category/time/language allocation"
}}"""


def build_generator_user_prompt(
    profile: UserProfile,
    *,
    count: int,
    profile_languages: list[SupportedLanguage],
    assigned_languages: list[SupportedLanguage],
    prior_performance_summary: str | None = None,
) -> str:
    plan = ", ".join(
        f"#{index + 1}={language.value}" for index, language in enumerate(assigned_languages)
    )
    lines = [
        f"Generate {count} personalized challenge(s).",
        f"Language plan (must match): {plan}",
        f"Profile languages: {language_labels(profile_languages)}",
        f"Name: {profile.name}",
        f"Experience level: {profile.experience_level}",
        f"Skills: {', '.join(profile.skills)}",
        f"Interests: {', '.join(profile.interests) or 'general'}",
        f"Career goals: {', '.join(profile.career_goals) or 'not specified'}",
        f"Preferred domains: {', '.join(profile.preferred_domains)}",
        f"Previous experience: {profile.previous_experience or 'none'}",
        f"Learning objectives: {', '.join(profile.learning_objectives) or 'not specified'}",
    ]
    if prior_performance_summary:
        lines.append(f"Prior performance (adapt difficulty): {prior_performance_summary}")
    return "\n".join(lines)


def build_adaptive_user_prompt(
    profile: UserProfile,
    *,
    decision: object,
    profile_languages: list[SupportedLanguage],
) -> str:
    """User prompt for generating a single adapted challenge."""
    from app.features.code.adaptive_schemas import AdaptationDecision

    typed = decision if isinstance(decision, AdaptationDecision) else AdaptationDecision.model_validate(decision)
    return "\n".join(
        [
            "Generate exactly 1 personalized challenge.",
            f"Target difficulty: {typed.next_difficulty}",
            f"Target category: {typed.next_category}",
            f"Target language: {typed.next_language}",
            f"Profile languages: {language_labels(profile_languages)}",
            f"Name: {profile.name}",
            f"Experience level: {profile.experience_level}",
            f"Skills: {', '.join(profile.skills)}",
            f"Preferred domains: {', '.join(profile.preferred_domains)}",
            f"Learning objectives: {', '.join(profile.learning_objectives) or 'not specified'}",
            f"Adaptation rationale (internal): {typed.rationale}",
        ]
    )
