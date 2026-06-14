"""Explicit registration surface for the code execution feature."""

from app.features.code.agent_tool import get_langchain_tools
from app.features.code import tool
from app.features.code.api import router
from app.features.registry import FeatureDescriptor, IntegrationDescriptor, ToolDescriptor

tool_descriptor = ToolDescriptor(
    name="code_execution",
    description=(
        "Execute learner Python in an E2B sandbox. Supports visible-only practice runs "
        "(keep_sandbox) and full graded submissions with weighted test cases."
    ),
    entrypoint=tool.execute_submission,
)

feature = FeatureDescriptor(
    name="code",
    api_prefix="code",
    tags=["code"],
    router=router,
    tool=tool_descriptor,
    integration=IntegrationDescriptor(
        question_types=("code",),
        frontend_blocks=("CodeTool", "QuestionRenderer"),
        description=(
            "E2B multi-language execution, multi-challenge timed sessions, "
            "LLM challenge generation and grading."
        ),
    ),
)

__all__ = ["feature", "router", "tool_descriptor", "get_langchain_tools"]
