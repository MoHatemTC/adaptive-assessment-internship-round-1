"""ASGI middleware for request-scoped context injection and metrics.

:class:`RequestContextMiddleware` assigns every request a unique ``request_id``,
binds it into the structlog contextvars context so *every* log line emitted
while handling the request carries it automatically, times the request, logs a
single ``http_request_completed`` event, and records HTTP metrics.

``setup_middleware`` registers the middleware on the FastAPI app and is called
once from ``main.py``.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.core.metrics import record_request

_logger = get_logger(__name__)

#: Response header carrying the generated request id back to the client.
_REQUEST_ID_HEADER = "X-Request-ID"


def _resolve_endpoint(request: Request) -> str:
    """Return a low-cardinality endpoint label for metrics.

    Prefers the matched route's path *template* (for example
    ``"/sessions/{session_id}"``) over the concrete URL path, so per-request
    path parameters do not explode Prometheus label cardinality.

    Args:
        request: The incoming request.

    Returns:
        The route path template if available, otherwise the raw URL path.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id, log completion, and record HTTP metrics.

    For each request this middleware generates a UUID ``request_id``, binds it to
    the structlog context, measures wall-clock duration, logs a single
    ``http_request_completed`` event, records the request in Prometheus, and
    clears the structlog context afterwards so ids never bleed between requests.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process one request within a bound logging context.

        Args:
            request: The incoming request.
            call_next: Callable that invokes the rest of the middleware stack and
                the route handler.

        Returns:
            The response produced downstream, with an ``X-Request-ID`` header.
        """
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            endpoint = _resolve_endpoint(request)
            _logger.info(
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=round(duration * 1000, 2),
            )
            record_request(request.method, endpoint, status_code, duration)
            structlog.contextvars.clear_contextvars()


def setup_middleware(app: FastAPI) -> None:
    """Register the request-context middleware on the application.

    Called once during application setup in ``main.py``.

    Args:
        app: The FastAPI application instance.

    Returns:
        None.
    """
    app.add_middleware(RequestContextMiddleware)


__all__ = ["RequestContextMiddleware", "setup_middleware"]
