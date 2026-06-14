"""Deterministic challenge templates when the LLM is unavailable."""

from __future__ import annotations

from app.challenges.schemas import GeneratedCodeChallenge, GeneratedTestCase, PlatformChallengeConfig, UserProfile
from app.features.code.constants import SupportedLanguage


def _difficulty(profile: UserProfile) -> str:
    level = profile.experience_level.lower()
    return "beginner" if "begin" in level else "intermediate"


def _base_timing(config: PlatformChallengeConfig, profile: UserProfile) -> tuple[str, int, int]:
    difficulty = _difficulty(profile)
    e2b_cap = config.challenge.e2b_execution_timeout_seconds
    candidate_seconds = config.challenge.min_time_per_challenge_minutes * 60
    return difficulty, min(30, e2b_cap), candidate_seconds


def _python_starter(body: str) -> str:
    return body


def _js_starter(body: str) -> str:
    return f"{body}\nmodule.exports = {{ solution }};\n"


def _ts_starter(body: str) -> str:
    return (
        f"{body}\n"
        "// Keep Node-compatible exports for sandbox execution.\n"
        "module.exports = { solution };\n"
    )


def _starter_for_language(language: SupportedLanguage, python_body: str, js_body: str) -> str:
    if language == SupportedLanguage.TYPESCRIPT:
        return _ts_starter(js_body.replace("function solution", "export function solution"))
    if language == SupportedLanguage.JAVASCRIPT:
        return _js_starter(js_body)
    return _python_starter(python_body)


def _tests_for_language(
    language: SupportedLanguage,
    cases: list[tuple[str, str, bool]],
) -> list[GeneratedTestCase]:
    tests: list[GeneratedTestCase] = []
    for raw_input, expected, hidden in cases:
        if language in (SupportedLanguage.JAVASCRIPT, SupportedLanguage.TYPESCRIPT):
            input_expr = raw_input.replace("print(", "console.log(")
        else:
            input_expr = raw_input
        tests.append(
            GeneratedTestCase(input=input_expr, expected_output=expected, is_hidden=hidden)
        )
    return tests


_FALLBACK_SPECS: list[dict] = [
    {
        "title": "Reverse a String",
        "category": "strings",
        "description": "Return the input string reversed.",
        "python_starter": "def solution(s: str) -> str:\n    pass",
        "js_starter": "function solution(s) {\n  return '';\n}",
        "cases": [
            ("print(solution('hello'))", "olleh", False),
            ("print(solution(''))", "", True),
        ],
    },
    {
        "title": "Sum Two Numbers",
        "category": "math",
        "description": "Return the sum of two integers.",
        "python_starter": "def solution(a: int, b: int) -> int:\n    pass",
        "js_starter": "function solution(a, b) {\n  return 0;\n}",
        "cases": [
            ("print(solution(2, 3))", "5", False),
            ("print(solution(-1, 1))", "0", True),
        ],
    },
    {
        "title": "Count Vowels",
        "category": "strings",
        "description": "Count vowels (a, e, i, o, u) in a lowercase string.",
        "python_starter": "def solution(s: str) -> int:\n    pass",
        "js_starter": "function solution(s) {\n  return 0;\n}",
        "cases": [
            ("print(solution('hello'))", "2", False),
            ("print(solution('rhythm'))", "0", True),
        ],
    },
    {
        "title": "Maximum in List",
        "category": "arrays",
        "description": "Return the largest integer in a non-empty list.",
        "python_starter": "def solution(nums: list[int]) -> int:\n    pass",
        "js_starter": "function solution(nums) {\n  return 0;\n}",
        "cases": [
            ("print(solution([3, 9, 2]))", "9", False),
            ("print(solution([-5, -1]))", "-1", True),
        ],
    },
]


def fallback_challenge_at_index(
    index: int,
    language: SupportedLanguage,
    profile: UserProfile,
    config: PlatformChallengeConfig,
) -> GeneratedCodeChallenge:
    """Build a distinct fallback challenge for the given slot index."""
    spec = _FALLBACK_SPECS[index % len(_FALLBACK_SPECS)]
    difficulty, time_limit_seconds, candidate_time_seconds = _base_timing(config, profile)
    return GeneratedCodeChallenge(
        title=spec["title"],
        difficulty=difficulty,
        category=spec["category"],
        description=spec["description"],
        requirements=[f"Implement solution for: {spec['description']}"],
        evaluation_criteria=["correctness", "edge_cases"],
        max_score=100,
        estimated_duration=f"{max(1, candidate_time_seconds // 60)} minutes",
        candidate_time_seconds=candidate_time_seconds,
        starter_code=_starter_for_language(
            language,
            spec["python_starter"],
            spec["js_starter"],
        ),
        language=language,
        time_limit_seconds=time_limit_seconds,
        test_cases=_tests_for_language(language, spec["cases"]),
    )
