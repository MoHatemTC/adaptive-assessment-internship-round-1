"""MCQ adaptation layer.

This module selects the next MCQ dimension, focus, and difficulty using the
current learner analysis, learner profile, and admin/blueprint configuration.

It follows the unified schema difficulty levels:
beginner / intermediate / advanced.
"""

from typing import Any, Dict, Optional


_DIFFICULTY_ORDER = ["beginner", "intermediate", "advanced"]


def _normalize_difficulty(difficulty: str | None) -> str:
    """Normalize unsupported or missing difficulty values."""
    if difficulty in _DIFFICULTY_ORDER:
        return difficulty

    return "beginner"


def _increase_difficulty(current_difficulty: str) -> str:
    """Move one level up, capped at advanced."""
    difficulty = _normalize_difficulty(current_difficulty)
    index = _DIFFICULTY_ORDER.index(difficulty)
    next_index = min(index + 1, len(_DIFFICULTY_ORDER) - 1)
    return _DIFFICULTY_ORDER[next_index]


def _decrease_difficulty(current_difficulty: str) -> str:
    """Move one level down, capped at beginner."""
    difficulty = _normalize_difficulty(current_difficulty)
    index = _DIFFICULTY_ORDER.index(difficulty)
    next_index = max(index - 1, 0)
    return _DIFFICULTY_ORDER[next_index]


def _difficulty_index(difficulty: str) -> int:
    """Return difficulty order index with safe fallback."""
    normalized = _normalize_difficulty(difficulty)
    return _DIFFICULTY_ORDER.index(normalized)


def _most_recent_or_common_difficulty(skill_stats: Dict[str, Any]) -> str:
    """Pick the most common difficulty seen for this dimension."""
    difficulties = skill_stats.get("difficulties", {})

    if not difficulties:
        return "beginner"

    return _normalize_difficulty(max(difficulties, key=difficulties.get))


def _pick_focus(admin_config: Optional[Dict[str, Any]]) -> str:
    """Pick the next focus/topic from the admin blueprint config."""
    if not admin_config:
        return "problem_solving"

    allowed_topics = admin_config.get("allowed_topics") or admin_config.get("focus_areas")

    if allowed_topics:
        return allowed_topics[0]

    return "problem_solving"


def select_next_mcq_plan(
    analysis: Dict[str, Any],
    learner_profile: Optional[Dict[str, Any]] = None,
    admin_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Select the next MCQ plan on the fly."""
    skill_mastery = analysis.get("skill_mastery", {})
    weakest_dimension = analysis.get("weakest_skill")

    allowed_dimensions = None
    max_difficulty = "advanced"

    if admin_config:
        allowed_dimensions = admin_config.get("allowed_skills")
        max_difficulty = _normalize_difficulty(
            admin_config.get("max_difficulty", "advanced")
        )

    if weakest_dimension:
        next_dimension = weakest_dimension
    elif allowed_dimensions:
        next_dimension = allowed_dimensions[0]
    else:
        next_dimension = "Thinking"

    if allowed_dimensions and next_dimension not in allowed_dimensions:
        next_dimension = allowed_dimensions[0]

    skill_stats = skill_mastery.get(next_dimension, {})
    mastery_level = skill_stats.get(
        "mastery_level",
        analysis.get("mastery_level", "low"),
    )
    current_difficulty = _most_recent_or_common_difficulty(skill_stats)

    if mastery_level == "high":
        next_difficulty = _increase_difficulty(current_difficulty)
    elif mastery_level == "medium":
        if current_difficulty != "beginner":
            next_difficulty = current_difficulty
        else:
            next_difficulty = "intermediate"
    else:
        next_difficulty = _decrease_difficulty(current_difficulty)

    if _difficulty_index(next_difficulty) > _difficulty_index(max_difficulty):
        next_difficulty = max_difficulty

    next_focus = _pick_focus(admin_config)

    return {
        "next_skill": next_dimension,
        "next_dimension": next_dimension,
        "next_focus": next_focus,
        "next_difficulty": next_difficulty,
        "mastery_level": mastery_level,
        "reason": (
            f"Selected {next_dimension} because it is the weakest/current target "
            f"dimension. Next difficulty is {next_difficulty} based on "
            f"{mastery_level} mastery."
        ),
        "learner_profile_used": learner_profile is not None,
        "admin_config_used": admin_config is not None,
    }
