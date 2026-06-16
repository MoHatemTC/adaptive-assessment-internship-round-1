"""Schemas for the contract extractor agent.

The contract extractor does not own any database tables. Its output shape,
:class:`~app.shared.schemas.memory.AdaptiveContract`, is the canonical
cross-tool handoff type defined once in ``app.shared.schemas.memory`` and
re-exported here for convenient feature-local imports. Only the input
context, :class:`ToolHandoffContext`, is introduced by this feature.
"""

from pydantic import BaseModel

from app.shared.schemas.memory import AdaptiveContract, ToolType


class ToolHandoffContext(BaseModel):
    """Input context describing the tool handoff to normalise into a contract.

    Attributes:
        session_id: Owning assessment session UUID.
        assessment_id: Parent assessment identifier.
        last_tool_type: Tool type that produced the most recent response.
    """

    session_id: str
    assessment_id: str
    last_tool_type: ToolType


__all__ = ["AdaptiveContract", "ToolHandoffContext"]
