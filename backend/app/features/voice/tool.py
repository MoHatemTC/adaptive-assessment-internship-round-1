"""Voice interview examiner-agent tool, implemented as a :class:`BaseTool` subgraph.

The voice tool exposes a time-boxed interview to the examiner agent through the
kernel :class:`~app.core.base_tool.BaseTool` contract. ``build_graph`` returns a
compiled LangGraph ``StateGraph`` that starts the interview, repeatedly checks
the elapsed time against the session's limit, and ends the interview — assembling
the final transcript silently for the LLM judge.

Nodes that touch the database open their own session via
:data:`~app.core.database.async_session`, because the graph runs outside the
FastAPI request lifecycle (driven by the agent / WebSocket layer).
"""

from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.base_tool import BaseTool
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.voice.service import (
    end_voice_session,
    get_voice_session,
    start_voice_session,
)

_logger = get_logger(__name__)


class VoiceState(TypedDict, total=False):
    """State passed through the voice interview subgraph.

    Attributes:
        voice_session_id: Primary key of the owning voice session.
        time_limit: Maximum interview duration in seconds.
        elapsed_seconds: Seconds elapsed since the interview started.
        transcript_chunks: Ordered transcript text chunks gathered so far.
        is_complete: Set to ``True`` once the interview has ended.
        final_transcript: The assembled final transcript, or ``None`` until the
            interview ends.
    """

    voice_session_id: int
    time_limit: int
    elapsed_seconds: int
    transcript_chunks: list[str]
    is_complete: bool
    final_transcript: Optional[str]


class VoiceTool(BaseTool):
    """Examiner-agent tool that conducts a time-boxed, transcribed interview."""

    @property
    def tool_name(self) -> str:
        """Stable identifier used by the agent registry and observability.

        Returns:
            The tool name ``"voice_tool"``.
        """
        return "voice_tool"

    @property
    def tool_description(self) -> str:
        """Natural-language summary the agent uses to decide when to call this.

        Returns:
            A short description of the tool's behaviour.
        """
        return "Conducts a time-boxed voice interview with real-time transcription"

    @property
    def input_schema(self) -> type:
        """Pydantic model that defines the adaptive evaluation input contract.

        Returns:
            The :class:`~app.features.voice.schemas.VoiceAdaptiveInput` class.
        """
        from app.features.voice.schemas import VoiceAdaptiveInput

        return VoiceAdaptiveInput

    @property
    def output_schema(self) -> type:
        """Pydantic model that defines the adaptive evaluation output contract.

        Returns:
            The :class:`~app.features.voice.schemas.VoiceAdaptiveOutput` class.
        """
        from app.features.voice.schemas import VoiceAdaptiveOutput

        return VoiceAdaptiveOutput

    def build_graph(self) -> CompiledStateGraph:
        """Build and compile the voice interview subgraph.

        Wires three nodes — ``start_interview`` -> ``check_time`` ->
        ``end_interview`` — where ``check_time`` conditionally routes to
        ``end_interview`` once ``elapsed_seconds`` reaches ``time_limit`` and
        otherwise halts, leaving the session open for more audio.

        Returns:
            The compiled voice interview graph.
        """
        graph: StateGraph = StateGraph(VoiceState)
        graph.add_node("start_interview", self._start_interview_node)
        graph.add_node("check_time", self._check_time_node)
        graph.add_node("end_interview", self._end_interview_node)

        graph.set_entry_point("start_interview")
        graph.add_edge("start_interview", "check_time")
        graph.add_conditional_edges(
            "check_time",
            self._route_after_check_time,
            {"end_interview": "end_interview", END: END},
        )
        graph.add_edge("end_interview", END)

        return graph.compile()

    async def _start_interview_node(self, state: VoiceState) -> dict[str, Any]:
        """Mark the voice session active and initialise interview state.

        Opens its own database session because the graph runs outside the
        FastAPI request lifecycle.

        Args:
            state: Incoming graph state carrying ``voice_session_id``.

        Returns:
            A state update initialising ``is_complete`` and the chunk buffer.
        """
        voice_session_id = state["voice_session_id"]
        async with async_session() as db:
            await start_voice_session(db, voice_session_id)
            await db.commit()

        _logger.info("voice_interview_started", voice_session_id=voice_session_id)

        return {
            "is_complete": False,
            "transcript_chunks": state.get("transcript_chunks", []),
        }

    async def _check_time_node(self, state: VoiceState) -> dict[str, Any]:
        """Compute elapsed interview time from the session's ``started_at``.

        Derives ``elapsed_seconds`` authoritatively from the database timestamp
        rather than trusting an injected value, so the conditional edge
        :meth:`_route_after_check_time` routes to ``end_interview`` based on real
        wall-clock progress against ``time_limit``. Opens its own database
        session because the graph runs outside the FastAPI request lifecycle.

        Args:
            state: Incoming graph state carrying ``voice_session_id``.

        Returns:
            A state update with the freshly computed ``elapsed_seconds``.
        """
        voice_session_id = state["voice_session_id"]
        async with async_session() as db:
            session = await get_voice_session(db, voice_session_id)
            if session.started_at is not None:
                elapsed = int(
                    (datetime.now(timezone.utc) - session.started_at).total_seconds()
                )
            else:
                elapsed = 0

        _logger.info(
            "voice_interview_time_checked",
            voice_session_id=voice_session_id,
            elapsed_seconds=elapsed,
            time_limit=state["time_limit"],
        )
        return {"elapsed_seconds": elapsed}

    def _route_after_check_time(self, state: VoiceState) -> str:
        """Route to ``end_interview`` when the time limit is reached, else stop.

        Args:
            state: Current graph state.

        Returns:
            ``"end_interview"`` if ``elapsed_seconds >= time_limit``, otherwise
            :data:`langgraph.graph.END`.
        """
        if state.get("elapsed_seconds", 0) >= state["time_limit"]:
            return "end_interview"
        return END

    async def _end_interview_node(self, state: VoiceState) -> dict[str, Any]:
        """End the session and attach the assembled final transcript.

        Opens its own database session because the graph runs outside the
        FastAPI request lifecycle.

        Args:
            state: Incoming graph state carrying ``voice_session_id``.

        Returns:
            A state update with ``is_complete`` set and the final transcript.
        """
        voice_session_id = state["voice_session_id"]
        async with async_session() as db:
            final_transcript = await end_voice_session(db, voice_session_id)
            await db.commit()

        _logger.info(
            "voice_interview_ended", voice_session_id=voice_session_id
        )

        return {"is_complete": True, "final_transcript": final_transcript}
