"""Rate limiting for API routes, built on slowapi.

Defines the single shared :data:`limiter` instance plus a few named, pre-built
limit decorators for the common cases. Feature routes apply them directly::

    from app.core.limiter import llm_limit

    @router.post("/grade")
    @llm_limit
    async def grade(request: Request, ...): ...

The decorated endpoint **must** declare a ``request: Request`` parameter — this
is slowapi's contract for resolving the client key. Application wiring (binding
``limiter`` to ``app.state.limiter`` and registering slowapi's exception
handler/middleware) is done in ``main.py``, not here.

Keying is by client IP via :func:`slowapi.util.get_remote_address`. Behind a
reverse proxy (the deployment runs nginx), ensure ``X-Forwarded-For`` is honored
so limits apply per real client rather than per proxy.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

#: Limit for general-purpose routes (profile intake, status polling, etc.).
STANDARD_LIMIT = "60/minute"

#: Tighter limit for LLM-heavy endpoints (blueprint generation, grading) where
#: each request fans out into expensive model calls.
LLM_LIMIT = "10/minute"

#: Limit for session-creation endpoints that spin up a new WebSocket-driven
#: assessment. Applies to the creation request, not the live WS connection.
WEBSOCKET_LIMIT = "5/minute"

#: Shared limiter instance. Routes never construct their own — they import the
#: decorators below (or ``limiter`` itself for custom limits).
limiter = Limiter(key_func=get_remote_address)

#: Pre-built decorator applying :data:`STANDARD_LIMIT`.
standard_limit = limiter.limit(STANDARD_LIMIT)

#: Pre-built decorator applying :data:`LLM_LIMIT`.
llm_limit = limiter.limit(LLM_LIMIT)

#: Pre-built decorator applying :data:`WEBSOCKET_LIMIT`.
websocket_limit = limiter.limit(WEBSOCKET_LIMIT)


__all__ = ["limiter", "standard_limit", "llm_limit", "websocket_limit"]
