"""Adaptive loop orchestrator for the voice tool.

Wires together Layers 5–8 for a single completed voice recording:
evaluate (grade + memory card) → analyse (dimension estimates) →
adapt (generate next question + build contract). Returns the full
:class:`~app.features.voice.schemas.VoiceAdaptiveOutput` with the adaptive
contract populated, ready for the caller to relay to the Generator Agent.
"""

from app.config import get_settings
from app.core.logging import get_logger
from app.shared.memory_retrieval import enrich_memory_summary_for_adaptation
from app.features.voice.adaptation import (
    build_voice_adaptive_contract,
    generate_next_voice_question,
)
from app.features.voice.analysis import analyze_voice_session
from app.features.voice.evaluation import evaluate_voice_response
from app.features.voice.schemas import VoiceAdaptiveInput, VoiceAdaptiveOutput

logger = get_logger(__name__)


async def run_voice_adaptive_loop(
    input_data: VoiceAdaptiveInput,
) -> VoiceAdaptiveOutput:
    """Orchestrate one full adaptive loop cycle for a completed voice recording.

    Runs Layers 5+6 (evaluate), Layer 7 (analyse), and Layer 8 (adapt) in
    sequence and embeds the resulting :class:`AdaptiveContract` into the
    evaluation output before returning.

    Args:
        input_data: The evaluation request describing the just-completed voice
            session, the learner profile, and the admin config.

    Returns:
        A :class:`~app.features.voice.schemas.VoiceAdaptiveOutput` with
        ``adaptive_contract`` populated. Never raises — failures in individual
        layers are handled internally and reported through the output fields.
    """
    logger.info(
        "adaptive_loop_started",
        session_id=input_data.session_id,
        question_index=input_data.question_index,
    )

    # Layers 5+6 — grade the transcript and extract a memory card.
    eval_output = await evaluate_voice_response(input_data)

    # Layer 7 — aggregate memory cards into dimension ability estimates.
    analysis = await analyze_voice_session(
        input_data.session_id, input_data.question_index
    )

    # Layer 8 — select next difficulty and generate the next question.
    prior_questions = analysis.get("prior_questions", [])

    adaptation_query = (
        f"Adaptive next question for {analysis.get('weakest_dimension', 'thinking')} "
        f"after {input_data.target_difficulty} difficulty response."
    )
    memory_summary = await enrich_memory_summary_for_adaptation(
        input_data.session_id,
        eval_output.memory_summary,
        adaptation_query,
    )

    next_question_text, next_difficulty, follow_up_depth = (
        await generate_next_voice_question(
            analysis=analysis,
            learner_profile=input_data.learner_profile,
            admin_config=input_data.admin_config,
            current_difficulty=input_data.target_difficulty,
            current_question_index=input_data.question_index,
            memory_summary=memory_summary,
            prior_questions=prior_questions,
            session_id=input_data.session_id,
        )
    )

    contract = await build_voice_adaptive_contract(
        session_id=input_data.session_id,
        current_question_index=input_data.question_index,
        analysis=analysis,
        next_question_text=next_question_text,
        next_difficulty=next_difficulty,
        follow_up_depth=follow_up_depth,
        memory_summary=memory_summary,
        admin_config=input_data.admin_config,
    )

    # Embed the contract plus the generated question into the output.
    contract_dict = contract.model_dump()
    contract_dict["next_question_text"] = next_question_text
    contract_dict["follow_up_depth"] = follow_up_depth
    eval_output.adaptive_contract = contract_dict

    logger.info(
        "adaptive_loop_completed",
        session_id=input_data.session_id,
        question_index=input_data.question_index,
        next_difficulty=next_difficulty,
        flagged=eval_output.flagged,
        stop=contract.stop,
    )
    return eval_output
