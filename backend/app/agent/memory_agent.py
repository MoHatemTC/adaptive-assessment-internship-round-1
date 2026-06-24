"""Memory Agent — Layer 6 of the adaptive assessment loop.

Runs after every graded learner response. Extracts one structured evidence
card via an LLM, persists it to ``memory_cards``, and produces a narrative
memory summary that the Adaptive Contract Layer (Layer 8) uses to select the
next question.

The agent is a four-node LangGraph pipeline:

1. ``load_prior_cards``   — load all existing cards for the session
2. ``extract_card``       — call the LLM to extract the new evidence card
3. ``save_card``          — persist the card to the database
4. ``summarize_memory``   — call the LLM to produce a progress summary

If any node sets ``error`` in the state, downstream nodes skip their LLM
calls and DB writes so the pipeline degrades gracefully.
"""

import asyncio
import json
import operator
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from typing_extensions import Annotated, TypedDict

from app.core.database import async_session
from app.core.llm import get_llm_with_tracing
from app.core.logging import get_logger
from app.sessions.models import MemoryCard as MemoryCardModel
from app.shared.schemas.memory import (
    DifficultyLevel,
    DimensionSignals,
    MemoryCardCreate,
    MemoryCardRead,
    ToolType,
)

logger = get_logger(__name__)


def _extract_answer_from_response(response: Any) -> str:
    """Extract the final answer string from an LLM response.

    Kimi K2 returns a list of thinking blocks + final answer string.
    Use reversed() to find the last plain string (the actual answer).

    Args:
        response: The LangChain message returned by ``llm.ainvoke``.

    Returns:
        The final answer text, stripped. Empty string if none is found.
    """
    raw_content = response.content
    if isinstance(raw_content, list):
        for item in reversed(raw_content):
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "").strip()
                if text:
                    return text
        return ""
    return str(raw_content).strip()


class MemoryAgentState(TypedDict):
    """LangGraph state for the memory agent pipeline.

    All fields are written once by a single node; ``prior_cards`` is
    accumulated with ``operator.add`` so partial updates compose correctly.
    """

    session_id: str
    tool_type: str
    question_index: int
    question_text: str
    learner_response: str
    rubric_scores_json: str
    passed: bool
    difficulty: str
    prior_cards: Annotated[list[dict], operator.add]
    card_create: Optional[dict]
    new_card: Optional[dict]
    saved_card: Optional[MemoryCardRead]
    memory_summary: str
    error: Optional[str]


# ---------------------------------------------------------------------------
# Node 1 — load prior cards
# ---------------------------------------------------------------------------

async def load_prior_cards_node(state: MemoryAgentState) -> dict[str, Any]:
    """Load all existing memory cards for the session, ordered by question index.

    Args:
        state: Current pipeline state.

    Returns:
        Dict with ``prior_cards`` key containing serialized MemoryCardRead dicts,
        or ``error`` key on failure.
    """
    try:
        async with async_session() as db:
            result = await db.execute(
                select(MemoryCardModel)
                .where(MemoryCardModel.session_id == state["session_id"])
                .order_by(MemoryCardModel.question_index)
            )
            rows = result.scalars().all()

        cards = []
        for row in rows:
            read_obj = MemoryCardRead.model_validate(
                {
                    "id": row.id,
                    "session_id": row.session_id,
                    "tool_type": row.tool_type,
                    "question_index": row.question_index,
                    "difficulty": row.difficulty,
                    "evidence_summary": row.evidence_summary,
                    "dimension_signals": json.loads(row.dimension_signals),
                    "passed": row.passed,
                    "created_at": row.created_at,
                }
            )
            cards.append(read_obj.model_dump(mode="json"))

        return {"prior_cards": cards}

    except Exception as e:
        logger.error("memory_load_failed", error=str(e))
        return {"prior_cards": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Node 2 — extract evidence card via LLM
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """
You are a learning assessment analyst. Your job is to extract a
structured evidence card from a learner's assessment response.
You must return ONLY valid JSON with no markdown, no code fences,
no explanation. Any deviation from pure JSON will break the system.
""".strip()

_EXTRACT_HUMAN_TEMPLATE = """
Tool: {tool_type}
Difficulty: {difficulty}
Question: {question_text}
Learner response: {learner_response}
Passed: {passed}
Rubric scores: {rubric_scores_json}

Extract a memory evidence card. Return this exact JSON structure:
{{
  "evidence_summary": "One concise sentence describing what this \
response reveals about the learner. Be specific and factual.",
  "dimension_signals": {{
    "thinking": true or false — logical reasoning and problem-solving,
    "soft": true or false — communication and interpersonal ability,
    "work": true or false — execution, delivery, task completion,
    "digital_ai": true or false — use of technology and AI tools,
    "growth": true or false — feedback receptiveness and learning
  }}
}}
""".strip()


async def extract_card_node(state: MemoryAgentState) -> dict[str, Any]:
    """Call the LLM to extract a structured evidence card from the learner response.

    Args:
        state: Current pipeline state.

    Returns:
        Dict with ``card_create`` key (serialized MemoryCardCreate dict),
        empty dict if skipped, or ``error`` key on failure.
    """
    if state.get("error"):
        return {}

    human_content = _EXTRACT_HUMAN_TEMPLATE.format(
        tool_type=state["tool_type"],
        difficulty=state["difficulty"],
        question_text=state["question_text"],
        learner_response=state["learner_response"],
        passed=state["passed"],
        rubric_scores_json=state["rubric_scores_json"],
    )

    try:
        llm, callbacks = get_llm_with_tracing()
        response = await llm.ainvoke(
            [
                SystemMessage(content=_EXTRACT_SYSTEM),
                HumanMessage(content=human_content),
            ],
            config={"callbacks": callbacks},
        )

        # Kimi K2 returns a list of thinking blocks + final answer string.
        # Use reversed() to find the last plain string (the actual answer).
        content = _extract_answer_from_response(response)
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)
        card_create = MemoryCardCreate(
            session_id=state["session_id"],
            tool_type=state["tool_type"],
            question_index=state["question_index"],
            difficulty=state["difficulty"],
            evidence_summary=parsed["evidence_summary"],
            dimension_signals=DimensionSignals(**parsed["dimension_signals"]),
            passed=state["passed"],
        )
        return {"card_create": card_create.model_dump(mode="json")}

    except Exception as e:
        logger.error("memory_extract_failed", error=str(e))
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Node 3 — persist the new card
# ---------------------------------------------------------------------------

async def save_card_node(state: MemoryAgentState) -> dict[str, Any]:
    """Persist the extracted memory card to the database.

    Args:
        state: Current pipeline state.

    Returns:
        Dict with ``new_card`` key (serialized MemoryCardRead dict),
        empty dict if skipped, or ``error`` key on failure.
    """
    if state.get("error") or not state.get("card_create"):
        return {}

    try:
        card_create = MemoryCardCreate(**state["card_create"])

        db_card = MemoryCardModel(
            session_id=card_create.session_id,
            tool_type=card_create.tool_type,
            question_index=card_create.question_index,
            difficulty=card_create.difficulty,
            evidence_summary=card_create.evidence_summary,
            dimension_signals=card_create.dimension_signals.model_dump_json(),
            passed=card_create.passed,
        )

        async with async_session() as db:
            db.add(db_card)
            await db.commit()
            await db.refresh(db_card)

        read_card = MemoryCardRead.model_validate(
            {
                "id": db_card.id,
                "session_id": card_create.session_id,
                "tool_type": card_create.tool_type,
                "question_index": card_create.question_index,
                "difficulty": card_create.difficulty,
                "evidence_summary": card_create.evidence_summary,
                "dimension_signals": card_create.dimension_signals,
                "passed": card_create.passed,
                "created_at": db_card.created_at,
            }
        )

        # ``new_card`` stays a JSON-serializable dict for the public return value;
        # ``saved_card`` carries the typed object the embed_and_store node needs.
        return {
            "new_card": read_card.model_dump(mode="json"),
            "saved_card": read_card,
        }

    except Exception as e:
        logger.error("memory_save_failed", error=str(e))
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Node 3.5 — embed the saved card and store it in Qdrant (non-critical)
# ---------------------------------------------------------------------------

async def embed_and_store_node(state: MemoryAgentState) -> dict[str, Any]:
    """Embed the saved card's evidence summary and upsert it to Qdrant.

    Non-critical path: any failure — Qdrant being unreachable, the embedding
    model failing to load, or a malformed vector — is logged and swallowed so
    the pipeline continues to ``summarize_memory``. This node never sets
    ``state["error"]``.

    Args:
        state: Current pipeline state.

    Returns:
        An empty dict. This node has side effects only; it must not return
        reducer-managed fields such as ``prior_cards`` (which would duplicate
        them via the ``operator.add`` reducer).
    """
    if state.get("error"):
        return {}

    card = state.get("saved_card")
    if card is None:
        return {}

    try:
        import uuid

        from qdrant_client.models import PointStruct

        from app.config import get_settings
        from app.shared.embedder import embed_text
        from app.shared.qdrant import get_qdrant_client

        settings = get_settings()
        evidence = card.evidence_summary
        if not evidence or not evidence.strip():
            return {}

        # SentenceTransformer.encode is CPU-bound; run off the event loop.
        vector = await asyncio.to_thread(embed_text, evidence)

        client = get_qdrant_client()
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "session_id": card.session_id,
                "tool_type": card.tool_type,
                "question_index": card.question_index,
                "difficulty": card.difficulty,
                "passed": card.passed,
                "evidence_summary": evidence,
            },
        )
        await client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[point],
        )
        logger.info(
            "qdrant_memory_stored",
            session_id=card.session_id,
            tool_type=card.tool_type,
            question_index=card.question_index,
        )
    except Exception as exc:  # noqa: BLE001 - Qdrant is a non-critical path
        logger.warning("qdrant_memory_store_failed", reason=str(exc))
        # Do NOT set state["error"] — Qdrant is non-critical.

    return {}


# ---------------------------------------------------------------------------
# Node 4 — summarize all cards for the adaptive layer
# ---------------------------------------------------------------------------

_SUMMARIZE_SYSTEM = """
You are summarizing a learner's assessment progress to guide
adaptive question selection. Be concise and specific. Return
plain text only — no bullet points, no headers, no markdown.
""".strip()

_SUMMARIZE_HUMAN_TEMPLATE = """
Evidence cards collected so far:
{cards_text}

Write a 2–3 sentence memory summary that:
- Identifies demonstrated strengths
- Notes consistent weaknesses or gaps
- Recommends what the next question should focus on
""".strip()


async def summarize_memory_node(state: MemoryAgentState) -> dict[str, Any]:
    """Call the LLM to produce a narrative memory summary over all cards.

    Args:
        state: Current pipeline state.

    Returns:
        Dict with ``memory_summary`` key (always set, even on failure).
    """
    if state.get("error"):
        return {"memory_summary": ""}

    all_cards: list[dict] = list(state["prior_cards"])
    if state.get("new_card"):
        all_cards.append(state["new_card"])

    if not all_cards:
        return {"memory_summary": "No prior evidence."}

    all_cards_sorted = sorted(all_cards, key=operator.itemgetter("question_index"))

    card_lines = []
    for c in all_cards_sorted:
        card_lines.append(
            f"Q{c['question_index']} ({c['tool_type']}, {c['difficulty']}): "
            f"{c['evidence_summary']}\nPassed: {c['passed']}"
        )
    cards_text = "\n".join(card_lines)

    try:
        llm, callbacks = get_llm_with_tracing()
        response = await llm.ainvoke(
            [
                SystemMessage(content=_SUMMARIZE_SYSTEM),
                HumanMessage(
                    content=_SUMMARIZE_HUMAN_TEMPLATE.format(cards_text=cards_text)
                ),
            ],
            config={"callbacks": callbacks},
        )
        # Kimi K2 returns a list of thinking blocks + final answer string.
        # Use reversed() to find the last plain string (the actual answer).
        return {"memory_summary": _extract_answer_from_response(response)}

    except Exception as e:
        logger.error("memory_summarize_failed", error=str(e))
        return {"memory_summary": "Summary unavailable."}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_memory_graph() -> CompiledStateGraph:
    """Build and compile the memory agent LangGraph pipeline.

    Returns:
        A compiled :class:`CompiledStateGraph` ready for ``ainvoke``.
    """
    graph = StateGraph(MemoryAgentState)

    graph.add_node("load_prior_cards", load_prior_cards_node)
    graph.add_node("extract_card", extract_card_node)
    graph.add_node("save_card", save_card_node)
    graph.add_node("embed_and_store", embed_and_store_node)
    graph.add_node("summarize_memory", summarize_memory_node)

    graph.add_edge(START, "load_prior_cards")
    graph.add_edge("load_prior_cards", "extract_card")
    graph.add_edge("extract_card", "save_card")
    graph.add_edge("save_card", "embed_and_store")
    graph.add_edge("embed_and_store", "summarize_memory")
    graph.add_edge("summarize_memory", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_memory_agent(
    session_id: str,
    tool_type: ToolType,
    question_index: int,
    question_text: str,
    learner_response: str,
    rubric_scores_json: str,
    passed: bool,
    difficulty: DifficultyLevel,
) -> tuple[Optional[MemoryCardRead], str]:
    """Run the full memory agent pipeline for one learner response.

    Called by the examiner agent after every graded answer.
    Returns (new_card, memory_summary).
    new_card is None if the pipeline failed — caller must handle this.
    memory_summary is always a string (may be empty on failure).

    Args:
        session_id: Platform assessment session UUID.
        tool_type: Which tool produced the response.
        question_index: Zero-based position in the assessment blueprint.
        question_text: The question that was asked.
        learner_response: The learner's answer text.
        rubric_scores_json: Serialized RubricScores from the grading layer.
        passed: Whether the response cleared the pass threshold.
        difficulty: Difficulty tier of the question.

    Returns:
        A ``(MemoryCardRead | None, summary_str)`` tuple.
    """
    graph = build_memory_graph()
    initial_state: MemoryAgentState = {
        "session_id": session_id,
        "tool_type": tool_type,
        "question_index": question_index,
        "question_text": question_text,
        "learner_response": learner_response,
        "rubric_scores_json": rubric_scores_json,
        "passed": passed,
        "difficulty": difficulty,
        "prior_cards": [],
        "card_create": None,
        "new_card": None,
        "saved_card": None,
        "memory_summary": "",
        "error": None,
    }
    result = await graph.ainvoke(initial_state)
    new_card = (
        MemoryCardRead(**result["new_card"]) if result.get("new_card") else None
    )
    return new_card, result.get("memory_summary", "")
