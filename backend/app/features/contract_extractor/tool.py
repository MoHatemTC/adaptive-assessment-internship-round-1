"""Contract extractor agent, implemented as a :class:`BaseTool` subgraph.

The contract extractor normalises the adaptive loop's output into a single
typed handoff contract (:class:`~app.shared.schemas.memory.AdaptiveContract`)
that the examiner agent passes to the next tool / Generator Agent. It owns no
business logic of its own: the single graph node delegates to
``compute_adaptive_contract`` (the code feature's Layer-8 adaptation step) and
simply surfaces the result in graph state.

The adaptation function is resolved lazily through
:func:`_load_compute_adaptive_contract` so this module imports cleanly before
the Sprint 2 adaptation layer exists, and so tests can substitute a fake.
"""

from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.base_tool import BaseTool
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.contract_extractor.schemas import AdaptiveContract

_logger = get_logger(__name__)

#: Signature of the adaptation step the extract node delegates to.
ComputeAdaptiveContract = Callable[
    [AsyncSession, str, str], Awaitable[AdaptiveContract]
]


def _load_compute_adaptive_contract() -> ComputeAdaptiveContract:
    """Resolve the code feature's ``compute_adaptive_contract`` function.

    Imported lazily so this module loads even before the Sprint 2 adaptation
    layer (``app.features.code.adaptation``) is implemented, and so tests can
    monkeypatch this loader with a stand-in.

    Returns:
        The ``compute_adaptive_contract`` coroutine function.

    Raises:
        RuntimeError: If the adaptation layer is not yet available.
    """
    try:
        from app.features.code.adaptation import compute_adaptive_contract
    except ImportError as exc:  # pragma: no cover - exercised once Layer 4 lands
        raise RuntimeError(
            "The adaptation layer (app.features.code.adaptation."
            "compute_adaptive_contract) is not available yet. Implement the "
            "Sprint 2 adaptation step before running the contract extractor."
        ) from exc
    return compute_adaptive_contract


class ContractExtractorState(TypedDict, total=False):
    """State passed through the contract extractor subgraph.

    Attributes:
        session_id: Owning assessment session UUID.
        assessment_id: Parent assessment identifier.
        last_tool_type: Tool type that produced the most recent response.
        contract: The normalised adaptive contract, set by the extract node.
    """

    session_id: str
    assessment_id: str
    last_tool_type: str
    contract: Optional[AdaptiveContract]


class ContractExtractorTool(BaseTool):
    """Examiner-agent tool that normalises loop output into a handoff contract."""

    @property
    def tool_name(self) -> str:
        """Stable identifier used by the agent registry and observability.

        Returns:
            The tool name ``"contract_extractor"``.
        """
        return "contract_extractor"

    @property
    def tool_description(self) -> str:
        """Natural-language summary the agent uses to decide when to call this.

        Returns:
            A short description of the tool's behaviour.
        """
        return (
            "Normalises adaptive loop output into a typed handoff contract "
            "for the next tool"
        )

    def build_graph(self) -> CompiledStateGraph:
        """Build and compile the single-node contract extraction subgraph.

        Returns:
            A compiled graph whose ``extract`` node produces an
            :class:`AdaptiveContract` in ``state["contract"]``.
        """
        graph: StateGraph = StateGraph(ContractExtractorState)
        graph.add_node("extract", self._extract_node)
        graph.set_entry_point("extract")
        graph.add_edge("extract", END)
        return graph.compile()

    async def _extract_node(self, state: ContractExtractorState) -> dict[str, Any]:
        """Delegate to the adaptation layer and surface the contract.

        Opens its own database session because the tool runs outside the
        FastAPI request lifecycle. No business logic lives here — the adaptive
        contract is computed by ``compute_adaptive_contract``.

        Args:
            state: Incoming graph state with ``session_id`` and ``assessment_id``.

        Returns:
            A state update carrying the computed :class:`AdaptiveContract`.
        """
        compute_adaptive_contract = _load_compute_adaptive_contract()
        session_id = state["session_id"]
        assessment_id = state["assessment_id"]

        _logger.info(
            "contract_extract_started",
            session_id=session_id,
            assessment_id=assessment_id,
            last_tool_type=state.get("last_tool_type"),
        )

        async with async_session() as db:
            contract = await compute_adaptive_contract(db, session_id, assessment_id)

        _logger.info(
            "contract_extract_completed",
            session_id=session_id,
            next_tool_type=contract.tool_type,
            next_difficulty=contract.difficulty,
            stop=contract.stop,
        )
        return {"contract": contract}


async def run_contract_extractor(
    session_id: str,
    assessment_id: str,
    last_tool_type: str,
) -> AdaptiveContract:
    """Run the contract extractor subgraph and return the handoff contract.

    Args:
        session_id: Owning assessment session UUID.
        assessment_id: Parent assessment identifier.
        last_tool_type: Tool type that produced the most recent response.

    Returns:
        The normalised :class:`AdaptiveContract` for the next question.

    Raises:
        RuntimeError: If the graph did not produce a contract.
    """
    tool = ContractExtractorTool()
    graph = tool.build_graph()
    result = await graph.ainvoke(
        {
            "session_id": session_id,
            "assessment_id": assessment_id,
            "last_tool_type": last_tool_type,
        }
    )
    contract = result.get("contract")
    if contract is None:
        raise RuntimeError("Contract extractor did not produce a contract")
    return contract


__all__ = [
    "ContractExtractorState",
    "ContractExtractorTool",
    "run_contract_extractor",
]
