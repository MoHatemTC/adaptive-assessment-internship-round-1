"""Abstract base class for the five examiner-agent tool subgraphs.

Every Masaar tool — MCQ, diagram/image reasoning, voice interview, camera
interview, and E2B code execution — is implemented as its own LangGraph
``StateGraph`` and exposed to the examiner agent through a subclass of
:class:`BaseTool`. The base class fixes a small, uniform contract so the agent
layer can discover, describe, and invoke any tool the same way:

* ``tool_name`` / ``tool_description`` — identity and a natural-language summary
  the agent uses when deciding whether (and how) to call the tool.
* ``build_graph`` — returns the compiled subgraph that implements the tool.
* ``invoke`` — a concrete streaming entry point shared by all tools.

Subclasses implement the three abstract members; they never override
``invoke`` unless they have a genuine reason to change the streaming contract.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

# VERIFY: confirmed correct on langgraph==1.2.4 — the compiled state graph type
# is exported from langgraph.graph.state as CompiledStateGraph.
from langgraph.graph.state import CompiledStateGraph

from app.core.logging import get_logger

_logger = get_logger(__name__)


class BaseTool(ABC):
    """Abstract base class all five tool subgraphs inherit from.

    Defines the contract the examiner agent relies on. Concrete tools implement
    :attr:`tool_name`, :attr:`tool_description`, and :meth:`build_graph`, and use
    the inherited :meth:`invoke` to run their compiled subgraph with streaming.
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Stable, machine-friendly identifier for the tool.

        Returns:
            The tool's name (for example ``"mcq"`` or ``"voice_interview"``),
            used as the registry key and in observability labels.
        """

    @property
    @abstractmethod
    def tool_description(self) -> str:
        """Natural-language description of what the tool does.

        Returns:
            A short human-readable summary the agent uses to decide when to
            invoke the tool.
        """

    @abstractmethod
    def build_graph(self) -> CompiledStateGraph:
        """Build and compile this tool's LangGraph state graph.

        Implementations construct a ``StateGraph``, wire its nodes and edges, and
        return the compiled result (typically via ``graph.compile(...)``).

        Returns:
            The compiled graph that implements the tool's workflow.
        """

    async def invoke(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the tool's compiled graph and stream state updates back.

        Builds the graph via :meth:`build_graph` and streams each update emitted
        by the graph as it executes, so callers can react incrementally (for
        example, forwarding partial results over the session WebSocket).

        Args:
            state: Initial input state passed to the graph.
            config: Optional LangGraph run configuration (for example
                ``{"configurable": {"thread_id": ...}, "callbacks": [...]}``).

        Yields:
            Each state update produced by the graph during execution.
        """
        _logger.info("tool_invoke_started", tool=self.tool_name)
        graph = self.build_graph()
        async for chunk in graph.astream(state, config=config):
            yield chunk
        _logger.info("tool_invoke_completed", tool=self.tool_name)


__all__ = ["BaseTool"]
