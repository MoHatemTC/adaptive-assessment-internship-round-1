"""Adaptive contract layer for the voice tool (Layer 8 of the adaptive loop).

Turns the analysis output (Layer 7) into the next move: it selects the next
difficulty within admin blueprint bounds, generates the next interview question
via the kernel LLM gateway (falling back to a preset on failure), and assembles
the :class:`~app.shared.schemas.memory.AdaptiveContract` handed to the next loop
iteration.
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.shared.schemas.memory import AdaptiveContract, DifficultyLevel

logger = get_logger(__name__)

#: Difficulty tiers in ascending order; index arithmetic drives selection.
_DIFFICULTY_ORDER: list[DifficultyLevel] = ["beginner", "intermediate", "advanced"]

#: Default voice question budget; the contract stops once it is exhausted.
_MAX_VOICE_QUESTIONS = 10

#: Preset questions used when LLM generation fails, keyed by difficulty.
_FALLBACKS = {
    "beginner": [
        "Tell me about a recent project you worked on and your role in it.",
        "How do you approach learning a new technology or tool?",
        "Describe a time you had to ask for help. How did you handle it?",
    ],
    "intermediate": [
        "Describe a technical challenge you faced and how you solved it.",
        "Tell me about a time you disagreed with a teammate. What happened?",
        "How do you prioritize tasks when multiple deadlines compete?",
    ],
    "advanced": [
        "How would you design a system to handle 10 million concurrent users?",
        "Describe a time you had to make a high-stakes technical decision quickly.",
        "How do you approach improving a legacy codebase with no documentation?",
    ],
}


def _normalize_difficulty(d: str | None) -> str:
    """Coerce an arbitrary difficulty value into a known tier.

    Args:
        d: A difficulty string, possibly ``None`` or unrecognized.

    Returns:
        ``d`` if it is a known tier, otherwise ``"beginner"``.
    """
    return d if d in _DIFFICULTY_ORDER else "beginner"


def _select_next_difficulty(
    current: str,
    mastery_level: str,
    admin_config: dict,
) -> str:
    """Select the next difficulty within the admin blueprint bounds.

    High mastery steps difficulty up, medium holds, low steps down — all clamped
    between ``"beginner"`` and the admin-configured ``max_difficulty``.

    Args:
        current: The current question's difficulty tier.
        mastery_level: Overall mastery (``"low"``/``"medium"``/``"high"``).
        admin_config: Admin constraints; ``max_difficulty`` caps the result.

    Returns:
        The selected next difficulty tier.
    """
    max_allowed = _normalize_difficulty(admin_config.get("max_difficulty", "advanced"))
    current = _normalize_difficulty(current)
    idx = _DIFFICULTY_ORDER.index(current)
    max_idx = _DIFFICULTY_ORDER.index(max_allowed)
    if mastery_level == "high":
        next_idx = min(idx + 1, max_idx)
    elif mastery_level == "medium":
        next_idx = min(idx, max_idx)
    else:
        next_idx = max(idx - 1, 0)
    return _DIFFICULTY_ORDER[next_idx]


async def generate_next_voice_question(
    analysis: dict[str, Any],
    learner_profile: dict[str, Any],
    admin_config: dict[str, Any],
    current_difficulty: str,
    current_question_index: int,
    memory_summary: str,
    prior_questions: list[str] | None = None,
) -> tuple[str, str, str]:
    """Generate the next voice interview question with the LLM.

    Args:
        analysis: Output of :func:`~app.features.voice.analysis.analyze_voice_session`.
        learner_profile: Opaque learner context (role, level, ...).
        admin_config: Opaque admin constraints (max difficulty, topics, ...).
        current_difficulty: The difficulty of the question just answered.
        current_question_index: Zero-based index of the question just answered.
        memory_summary: Narrative progress summary from the memory agent.
        prior_questions: Previously asked question texts for this session;
            injected into the prompt so the LLM does not generate duplicates.

    Returns:
        A ``(question_text, next_difficulty, follow_up_depth)`` tuple. On LLM
        failure ``question_text`` is a preset fallback for the chosen difficulty.
    """
    next_diff = _select_next_difficulty(
        current_difficulty,
        analysis.get("mastery_level", "low"),
        admin_config,
    )
    follow_up_depth = analysis.get("recommended_follow_up_depth", "simple")
    weakest_dim = analysis.get("weakest_dimension") or "thinking"
    learner_role = learner_profile.get("role", "software developer")
    learner_level = learner_profile.get("level", "mid")
    allowed_topics = admin_config.get("allowed_topics", ["technical skills"])

    depth_instruction = (
        "Ask a deep follow-up probing implementation details, edge cases, "
        "or asking the learner to critique or improve their earlier answer."
        if follow_up_depth == "deep"
        else "Ask a clear, direct question. Do not repeat what was already asked."
    )

    system = (
        "You are an expert adaptive technical interviewer. "
        "Generate exactly one interview question. "
        "Return ONLY the question — no preamble, no numbering, no explanation."
    )
    human = (
        f"Learner role: {learner_role}\n"
        f"Learner level: {learner_level}\n"
        f"Next question number: {current_question_index + 2}\n"
        f"Target difficulty: {next_diff}\n"
        f"Dimension to probe: {weakest_dim}\n"
        f"Allowed topics: {allowed_topics}\n"
        f"Memory summary: {memory_summary or 'No prior answers yet.'}\n"
        f"Instruction: {depth_instruction}\n\n"
        "Generate the next interview question:"
    )

    if prior_questions:
        questions_list = "\n".join(
            f"{i + 1}. {q}" for i, q in enumerate(prior_questions)
        )
        human += (
            f"\n\nCRITICAL — Previously asked questions in this session. "
            f"You MUST NOT repeat or closely paraphrase any of these:\n"
            f"{questions_list}\n\n"
            f"Generate a completely different question that tests the same "
            f"dimension from a fresh angle."
        )

    try:
        llm = get_llm()
        response = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        raw_content = response.content
        if isinstance(raw_content, list):
            # Kimi K2 reasoning model: returns thinking blocks followed
            # by the actual answer as a plain string at the end of the list
            question_text = ""
            for item in reversed(raw_content):
                if isinstance(item, str) and item.strip():
                    question_text = item.strip()
                    break
                elif isinstance(item, dict) and item.get("type") == "text":
                    candidate = item.get("text", "").strip()
                    if candidate:
                        question_text = candidate
                        break
        else:
            question_text = str(raw_content).strip()
        if not question_text:
            raise ValueError("LLM returned empty question")
        logger.info(
            "question_generated",
            difficulty=next_diff,
            follow_up_depth=follow_up_depth,
            dimension=weakest_dim,
        )
        return question_text, next_diff, follow_up_depth
    except Exception as e:  # noqa: BLE001 - generation must degrade, never raise
        logger.error("question_generation_failed", error=str(e))
        fallback_list = _FALLBACKS.get(next_diff, _FALLBACKS["intermediate"])
        idx = len(prior_questions or []) % len(fallback_list)
        return fallback_list[idx], next_diff, follow_up_depth


async def build_voice_adaptive_contract(
    session_id: str,
    current_question_index: int,
    analysis: dict[str, Any],
    next_question_text: str,
    next_difficulty: str,
    follow_up_depth: str,
    memory_summary: str,
) -> AdaptiveContract:
    """Assemble the adaptive contract for the next loop iteration.

    Args:
        session_id: Owning assessment session identifier.
        current_question_index: Zero-based index of the question just answered.
        analysis: Output of the analysis layer; supplies the focus dimension.
        next_question_text: The generated next question (carried by the caller).
        next_difficulty: The selected next difficulty tier.
        follow_up_depth: Recommended probing depth for the next question.
        memory_summary: Narrative progress summary from the memory agent.

    Returns:
        The :class:`~app.shared.schemas.memory.AdaptiveContract` for the next
        question, with ``stop`` set once the question budget is exhausted.
    """
    stop = current_question_index >= _MAX_VOICE_QUESTIONS - 1
    return AdaptiveContract(
        session_id=session_id,
        question_index=current_question_index + 1,
        tool_type="voice",
        difficulty=next_difficulty,
        focus_dimension=analysis.get("weakest_dimension"),
        stop=stop,
        memory_summary=memory_summary,
    )
