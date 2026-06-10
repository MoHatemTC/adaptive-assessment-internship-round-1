"""Central FastAPI dependency-injection surface for the kernel.

Every API route — in every feature — imports its dependencies from this module
rather than reaching into individual kernel files. That keeps the wiring layer
in one place and gives features a single, stable import surface
(``from app.core.deps import ...``).

The kernel's dependency graph is strictly one-directional: this module imports
*only* from other ``app.core`` modules and third-party packages. It never
imports from ``app.features``, ``app.agent``, ``app.admin``, ``app.sessions``,
``app.workers``, ``app.proctoring``, or ``app.reports``. Where a dependency needs
a model the feature teams have not built yet (the learner-session model), it is
referenced via ``Any`` with a ``TODO`` rather than importing feature code.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from fastapi import Depends
from fastapi.routing import APIRoute
from fastapi.security import OAuth2PasswordBearer
from langchain_core.callbacks import BaseCallbackHandler
from langchain_litellm import ChatLiteLLM
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.checkpointer import get_checkpointer
from app.core.database import get_db
from app.core.limiter import standard_limit
from app.core.llm import get_llm, get_llm_with_tracing
from app.core.logging import get_logger
from app.core.security import (
    credentials_exception,
    hash_token,
    session_not_found_exception,
    verify_access_token,
)

_logger = get_logger(__name__)

#: Extracts a bearer token from the ``Authorization`` header. ``tokenUrl`` is
#: OpenAPI-docs metadata only (the admin login route); it is not a runtime
#: dependency or a secret. The same scheme backs both the opaque learner session
#: token and the admin JWT.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


async def get_session_by_token(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Resolve a learner session token to its session record.

    The raw bearer token is hashed and looked up against the stored digest in
    the ``assessment_sessions`` table. A missing or expired session yields a
    standard 404.

    Note:
        The ``AssessmentSession`` model does not exist yet — it will be built by
        the feature team under ``app/sessions/``. The kernel must not import
        feature code, so the return type is annotated ``Any`` and the real query
        is left as a commented template. Until the model lands, this dependency
        deliberately raises :func:`session_not_found_exception`, so routes that
        depend on it fail closed rather than passing ``None`` through.

    Args:
        token: Opaque learner session token from the ``Authorization`` header.
        db: Active async database session.

    Returns:
        The matching session record once ``app/sessions/`` exists. Typed ``Any``
        for now (forward reference to ``AssessmentSession``).

    Raises:
        HTTPException: 404 if the token does not resolve to a live session.
    """
    hashed_token = hash_token(token)

    # TODO: replace with AssessmentSession lookup once app/sessions/ is built.
    #   from sqlmodel import select
    #   result = await db.exec(
    #       select(AssessmentSession).where(
    #           AssessmentSession.token_hash == hashed_token,
    #           AssessmentSession.expires_at > datetime.now(timezone.utc),
    #       )
    #   )
    #   session = result.first()
    #   if session is None:
    #       raise session_not_found_exception()
    #   return session
    _ = (hashed_token, db)  # keep references live until the lookup is wired up
    _logger.warning("session_lookup_not_implemented")
    raise session_not_found_exception()


async def get_current_admin(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    """Authenticate an admin from a bearer JWT and return its claims.

    Args:
        token: Admin access token (JWT) from the ``Authorization`` header.

    Returns:
        The decoded JWT claims payload.

    Raises:
        HTTPException: 401 if the token is missing, malformed, expired, or has an
            invalid signature.
    """
    payload = verify_access_token(token)
    if payload is None:
        raise credentials_exception()
    return payload


async def get_checkpointer_dep() -> AsyncGenerator[BaseCheckpointSaver, None]:
    """Yield a LangGraph checkpointer for a request.

    FastAPI-dependency wrapper around
    :func:`app.core.checkpointer.get_checkpointer`. The underlying connection is
    closed automatically when the request completes.

    Yields:
        A ready-to-use checkpointer.

    Raises:
        RuntimeError: If Postgres is unreachable outside development (raised by
            the wrapped context manager, with credentials masked).
    """
    async with get_checkpointer() as checkpointer:
        yield checkpointer


def get_llm_dep() -> ChatLiteLLM:
    """Return a configured LLM instance for a request.

    Returns:
        A :class:`ChatLiteLLM` built with the platform defaults.
    """
    return get_llm()


def get_llm_with_tracing_dep() -> tuple[ChatLiteLLM, list[BaseCallbackHandler]]:
    """Return an LLM plus its Langfuse tracing callbacks for a request.

    Returns:
        A ``(llm, callbacks)`` tuple suitable for traced invocation.
    """
    return get_llm_with_tracing()


@dataclass
class CommonQueryParams:
    """Shared pagination query parameters for list endpoints.

    Use as a dependency (``params: CommonQueryParams = Depends()``) to give every
    list endpoint a consistent ``skip``/``limit`` contract.

    Attributes:
        skip: Number of records to skip (offset). Defaults to ``0``.
        limit: Maximum number of records to return. Defaults to ``100``.
    """

    skip: int = 0
    limit: int = 100


class RateLimitedRoute(APIRoute):
    """An :class:`APIRoute` that applies the standard rate limit by default.

    Feature routers set ``route_class=RateLimitedRoute`` so every route on the
    router is rate limited without each endpoint repeating a decorator. Endpoints
    using this route class must declare a ``request: Request`` parameter (the
    slowapi contract for resolving the client key).

    Note:
        This wraps the endpoint with :data:`app.core.limiter.standard_limit` at
        route-construction time. ``# VERIFY`` the slowapi-over-APIRoute
        interaction in the Docker environment; if it proves brittle, the
        documented fallback is for feature routers to apply ``@limiter.limit(...)``
        decorators directly on individual routes instead.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Wrap the route's endpoint in the standard rate-limit decorator.

        Args:
            *args: Positional arguments forwarded to :class:`APIRoute`.
            **kwargs: Keyword arguments forwarded to :class:`APIRoute`. The
                ``endpoint`` entry, when present, is wrapped before delegation.
        """
        endpoint = kwargs.get("endpoint")
        if endpoint is not None:
            kwargs["endpoint"] = standard_limit(endpoint)
        super().__init__(*args, **kwargs)


__all__ = [
    "get_db",
    "oauth2_scheme",
    "get_session_by_token",
    "get_current_admin",
    "get_checkpointer_dep",
    "get_llm_dep",
    "get_llm_with_tracing_dep",
    "CommonQueryParams",
    "RateLimitedRoute",
]
