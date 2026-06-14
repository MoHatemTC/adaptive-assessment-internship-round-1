"""Feature discovery and router mounting (feature-owned, not kernel)."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI
from langchain_core.tools import StructuredTool

from app.core.deps import RateLimitedRoute

FEATURE_MODULES: list[str] = [
    "app.features.code.register",
]


@dataclass(frozen=True)
class IntegrationDescriptor:
    """Hints for chat UI blocks and agent graph tool routing."""

    question_types: tuple[str, ...] = ()
    frontend_blocks: tuple[str, ...] = ()
    proctoring: bool = False
    description: str = ""


@dataclass(frozen=True)
class ToolDescriptor:
    """Metadata for agent/LangGraph tool registration."""

    name: str
    description: str
    entrypoint: Callable[..., Any]


@dataclass(frozen=True)
class FeatureDescriptor:
    """Registration bundle for a vertical-slice feature."""

    name: str
    api_prefix: str
    tags: list[str]
    router: APIRouter
    tool: ToolDescriptor | None = None
    integration: IntegrationDescriptor | None = None


def discover_features() -> list[FeatureDescriptor]:
    """Load and validate feature registration modules."""
    features: list[FeatureDescriptor] = []
    for module_path in FEATURE_MODULES:
        module = importlib.import_module(module_path)
        feature = getattr(module, "feature", None)
        if not isinstance(feature, FeatureDescriptor):
            raise RuntimeError(
                f"{module_path} must export a FeatureDescriptor named 'feature'"
            )
        features.append(feature)
    return features


def discover_tool_descriptors() -> list[ToolDescriptor]:
    """Return LangGraph-ready tool descriptors from all registered features."""
    return [feat.tool for feat in discover_features() if feat.tool is not None]


_LANGCHAIN_TOOL_BUILDERS: dict[str, str] = {
    "code": "app.features.code.agent_tool",
}


def discover_langchain_tools() -> list[StructuredTool]:
    """Instantiate LangChain StructuredTools from registered features."""
    tools: list[StructuredTool] = []
    for feat in discover_features():
        module_path = _LANGCHAIN_TOOL_BUILDERS.get(feat.name)
        if not module_path:
            continue
        module = importlib.import_module(module_path)
        builder = getattr(module, "get_langchain_tools", None)
        if callable(builder):
            tools.extend(builder())
    return tools


def mount_feature_routers(app: FastAPI, *, prefix: str = "/api/v1") -> None:
    """Mount all registered feature routers on the FastAPI app."""
    for feat in discover_features():
        router = APIRouter(route_class=RateLimitedRoute)
        router.include_router(feat.router, tags=feat.tags)
        app.include_router(router, prefix=f"{prefix}/{feat.api_prefix}")
