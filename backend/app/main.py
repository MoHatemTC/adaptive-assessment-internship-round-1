"""FastAPI application factory with auto-discovered feature routers.

Wires the kernel together into a runnable app: structured logging, request
middleware, rate-limit error handling, a health check, the agent checkpointer
lifespan, and automatic registration of every feature router.

Router discovery is intentionally tolerant: each candidate module is imported in
isolation and a failure (missing module, import error, or no ``router``
attribute) is logged and skipped rather than crashing startup. That lets the
team build features incrementally — a half-finished or absent feature never
takes down the whole API.

Run with ``uvicorn app.main:app``.
"""

import pkgutil
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.checkpointer import setup_checkpointer
from app.core.database import check_db_connection
from app.core.limiter import limiter
from app.core.logging import configure_logging, get_logger
from app.core.middleware import setup_middleware
from app.shared.qdrant import bootstrap_qdrant, check_qdrant_connection, is_qdrant_configured

_logger = get_logger(__name__)

#: Package scanned for feature subpackages, each expected to expose ``api.py``.
_FEATURES_PACKAGE = "app.features"

#: Standalone modules outside ``app.features`` that may expose a ``router``.
_STANDALONE_ROUTER_MODULES = (
    "app.admin.api",
    "app.sessions.api",
    "app.proctoring.api",
    "app.reports.api",
)


def _include_router(app: FastAPI, module_path: str) -> None:
    """Import ``module_path`` and register its ``router`` if present.

    Any failure is logged and swallowed so one broken or unfinished feature
    cannot prevent the application from starting.

    Args:
        app: The FastAPI application to register the router on.
        module_path: Dotted path of the module to import (for example
            ``"app.features.mcq.api"``).

    Returns:
        None.
    """
    try:
        module = import_module(module_path)
    except Exception as exc:  # noqa: BLE001 - discovery must tolerate any error
        _logger.warning("router_import_failed", module=module_path, error=str(exc))
        return

    router = getattr(module, "router", None)
    if router is None:
        _logger.info("router_not_found", module=module_path)
        return

    try:
        app.include_router(router)
    except Exception as exc:  # noqa: BLE001 - a bad router must not crash startup
        _logger.warning("router_register_failed", module=module_path, error=str(exc))
        return

    _logger.info("router_registered", module=module_path)


def _discover_routers(app: FastAPI) -> None:
    """Auto-discover and register all feature, admin, and session routers.

    Scans every subpackage of :data:`_FEATURES_PACKAGE` for an ``api`` module,
    plus the standalone modules in :data:`_STANDALONE_ROUTER_MODULES`, and
    registers any ``router`` each exposes.

    Args:
        app: The FastAPI application to register routers on.

    Returns:
        None.
    """
    try:
        features_pkg = import_module(_FEATURES_PACKAGE)
    except Exception as exc:  # noqa: BLE001 - missing features pkg is non-fatal
        _logger.warning("features_package_import_failed", error=str(exc))
    else:
        for submodule in pkgutil.iter_modules(features_pkg.__path__):
            if submodule.ispkg:
                _include_router(app, f"{_FEATURES_PACKAGE}.{submodule.name}.api")

    for module_path in _STANDALONE_ROUTER_MODULES:
        _include_router(app, module_path)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: provision the agent checkpointer on startup.

    Args:
        app: The FastAPI application (required by the lifespan protocol).

    Yields:
        Control back to the running application after startup tasks complete.
    """
    _logger.info("app_startup_started")
    await setup_checkpointer()
    app.state.qdrant_ok = await bootstrap_qdrant()
    try:
        from app.shared.embedder import get_embedding_model

        await asyncio.to_thread(get_embedding_model)
    except Exception as exc:  # noqa: BLE001 - optional cold-start preload
        _logger.warning("embedding_model_preload_skipped", reason=str(exc))
    _logger.info("app_startup_complete")
    yield
    _logger.info("app_shutdown_complete")


def create_app() -> FastAPI:
    """Build and configure the Masaar FastAPI application.

    Configures logging, installs the request-context middleware, wires the
    slowapi rate limiter and its exception handler, registers the health check,
    and auto-discovers feature routers.

    Returns:
        The fully configured :class:`~fastapi.FastAPI` application.
    """
    configure_logging()

    app = FastAPI(title="Masaar API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    setup_middleware(app)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/health")
    async def health() -> dict[str, str | bool | None]:
        """Report service health, including database and Qdrant connectivity.

        Returns:
            A mapping with ``status``, ``db``, and ``qdrant``. ``qdrant`` is
            ``null`` when ``QDRANT_URL`` is unset (memory features disabled),
            otherwise a boolean reachability flag.
        """
        db_ok = await check_db_connection()
        if not is_qdrant_configured():
            qdrant_ok: bool | None = None
        else:
            qdrant_ok = await check_qdrant_connection()
        return {"status": "ok", "db": db_ok, "qdrant": qdrant_ok}

    _discover_routers(app)

    return app


app = create_app()
