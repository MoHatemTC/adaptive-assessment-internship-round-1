"""Structlog configuration — the single logging-setup site for the backend.

This is the *only* module in the codebase that configures logging. Every other
module obtains a logger via :func:`get_logger` and never imports ``structlog``
or the standard ``logging`` module directly.

Logs are structured: in production they render as JSON (one object per line,
ready for log shippers); in development they render as colourised console lines
with ``rich``-formatted tracebacks. Request-scoped context (``request_id``,
``session_id``, ...) is bound once by the request middleware via
``structlog.contextvars`` and then merged into every log line automatically — so
individual log calls never have to pass it.

Logging conventions (enforced by review):

* **Event strings are ``lowercase_with_underscores``** and name *what happened*,
  not a sentence. Examples: ``"db_connection_established"``,
  ``"llm_call_started"``, ``"token_verification_failed"``.
* **No f-strings in event strings.** Dynamic values are passed as keyword
  arguments, never interpolated into the message. This keeps events groupable
  and machine-parseable.

      Wrong:  ``logger.info(f"user {user_id} logged in")``
      Right:  ``logger.info("user_logged_in", user_id=user_id)``
"""

import structlog

from app.config import get_settings


def configure_logging() -> None:
    """Configure structlog process-wide. Call once at application startup.

    Selects a JSON renderer in production and a colourised console renderer (with
    ``rich`` tracebacks) in development, based on
    :attr:`app.config.Settings.is_development`. Installs the shared processor
    chain that adds the log level, an ISO-8601 UTC timestamp, any contextvars
    bound by the request middleware, and standard-library ``extra`` fields.

    This function is idempotent in effect: calling it again simply re-installs
    the same configuration.

    Returns:
        None.
    """
    settings = get_settings()

    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer(colors=True)
        if settings.is_development
        else structlog.processors.JSONRenderer()
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ExtraAdder(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        renderer,
    ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound structlog logger for ``name``.

    This is the canonical way every module obtains a logger; import this instead
    of calling ``structlog.get_logger`` (or the standard ``logging`` module)
    directly, so the whole backend shares one configuration and one set of
    conventions.

    Args:
        name: Logger name, conventionally the calling module's ``__name__``.

    Returns:
        A :class:`structlog.BoundLogger` bound to ``name``.
    """
    return structlog.get_logger(name)


__all__ = ["configure_logging", "get_logger"]
