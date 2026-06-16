"""Contract extractor agent feature package.

Exposes the agent tool and its handoff schemas. The extractor normalises the
adaptive loop's output into a single typed
:class:`~app.shared.schemas.memory.AdaptiveContract` for the next tool.
"""

from app.features.contract_extractor.schemas import (
    AdaptiveContract,
    ToolHandoffContext,
)
from app.features.contract_extractor.tool import (
    ContractExtractorState,
    ContractExtractorTool,
    run_contract_extractor,
)

__all__ = [
    "AdaptiveContract",
    "ToolHandoffContext",
    "ContractExtractorState",
    "ContractExtractorTool",
    "run_contract_extractor",
]
