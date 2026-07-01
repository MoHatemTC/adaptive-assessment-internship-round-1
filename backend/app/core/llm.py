"""The single LiteLLM/LangChain gateway for every LLM call in the system.

Nothing in the codebase instantiates an LLM client directly — agent nodes,
graders, the judge, and the blueprint generator all go through the factories
here. Centralising this guarantees consistent configuration (temperature,
streaming, retries), automatic Langfuse tracing, and a single place to evolve
provider behaviour.

Tracing and metrics responsibilities:

* :func:`get_llm_with_tracing` is the canonical entry point for agent nodes. It
  returns ``(llm, callbacks)`` where ``callbacks`` carries the Langfuse handler.
  Pass :func:`app.core.tracing.llm_invoke_config` as the invoke ``config`` so
  traces include ``session_id``, tool, and operation tags via Langfuse metadata.
  It is intentionally *pure* — it builds the objects and makes no model call.
* Because the kernel does not intercept node invocations, **agent nodes are
  responsible for calling** :func:`app.core.metrics.record_llm_call` after their
  own ``invoke``/``ainvoke``, timing the call and passing the model, tool name,
  status, and duration. The kernel itself only records metrics for
  :func:`test_llm_connection` (the one call it actually makes).

Resilience: LLM calls are wrapped with a tenacity retry policy
(``stop_after_attempt(3)`` + exponential backoff). Retries are logged as
``llm_call_retrying`` with the attempt number via structlog.
"""

import time
from functools import lru_cache

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_litellm import ChatLiteLLM
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler  # VERIFY: v4 LangChain handler path
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.core.tracing import LangfuseTraceContext, llm_invoke_config

_logger = get_logger(__name__)

#: Low temperature for deterministic grading/assessment behaviour. Kept fixed so
#: scoring stays reproducible across calls and sessions.
_ASSESSMENT_TEMPERATURE = 0.1

#: Retry budget for transient LLM/API errors.
_MAX_RETRIES = 3


def _log_retry(retry_state: RetryCallState) -> None:
    """Log an LLM retry attempt via structlog.

    Used as the tenacity ``before_sleep`` callback so retries are observable
    without routing through the standard-library logging module.

    Args:
        retry_state: Tenacity's state for the current retry attempt.

    Returns:
        None.
    """
    _logger.warning("llm_call_retrying", attempt_number=retry_state.attempt_number)


def get_llm(model: str | None = None) -> ChatLiteLLM:
    """Construct a configured :class:`ChatLiteLLM` instance.

    The returned model is tuned for grading/assessment work: low temperature,
    streaming enabled, and bounded internal retries.

    Args:
        model: Optional model identifier. When ``None``, the default
            ``LITELLM_MODEL`` from settings is used.

    Returns:
        A ready-to-use :class:`ChatLiteLLM` instance.
    """
    settings = get_settings()
    return ChatLiteLLM(
        model=model or settings.LITELLM_MODEL,
        temperature=_ASSESSMENT_TEMPERATURE,
        streaming=True,
        max_retries=_MAX_RETRIES,
        # VERIFY: api_key / api_base kwarg names on langchain-litellm 0.6.6.
        api_key=settings.LITELLM_API_KEY.get_secret_value(),
        api_base=settings.LITELLM_BASE_URL or None,
    )


@lru_cache
def _init_langfuse() -> Langfuse:
    """Initialise and cache the process-wide Langfuse v4 client.

    Langfuse v4 routes traces through a singleton client configured once per
    process; the LangChain callback then attaches to it. Caching ensures the
    client (and its OTel exporter) is created exactly once.

    Returns:
        The cached, configured :class:`Langfuse` client.
    """
    settings = get_settings()
    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY.get_secret_value(),
        secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
        host=settings.LANGFUSE_HOST,
    )


def get_langfuse_callback() -> CallbackHandler:
    """Return a Langfuse LangChain callback handler for tracing.

    Ensures the singleton Langfuse client is initialised, then returns a handler
    bound to it. Attach the result to any LLM/chain invocation to emit a trace
    with execution time and token cost.

    Returns:
        A :class:`~langfuse.langchain.CallbackHandler` ready to pass in a
        ``callbacks`` list.
    """
    _init_langfuse()
    # VERIFY: v4 CallbackHandler() takes no key args — it reads the singleton
    # client configured above (unlike the v2/v3 constructor).
    return CallbackHandler()


def get_llm_with_tracing(
    model: str | None = None,
) -> tuple[ChatLiteLLM, list[BaseCallbackHandler]]:
    """Return an LLM plus the callbacks list that traces it.

    This is the function agent nodes should call: one import yields both a
    configured model and the Langfuse callback wired for automatic tracing. The
    callbacks are passed through to the invocation, for example
    ``llm.ainvoke(messages, config={"callbacks": callbacks})``.

    This function makes no model call itself; nodes that invoke the model are
    responsible for recording metrics via
    :func:`app.core.metrics.record_llm_call`.

    Args:
        model: Optional model identifier. When ``None``, the default
            ``LITELLM_MODEL`` from settings is used.

    Returns:
        A ``(llm, callbacks)`` tuple, where ``callbacks`` contains the Langfuse
        tracing handler.
    """
    llm = get_llm(model)
    callbacks: list[BaseCallbackHandler] = [get_langfuse_callback()]
    return llm, callbacks


@retry(
    stop=stop_after_attempt(_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=_log_retry,
    reraise=True,
)
async def _ping_llm(llm: ChatLiteLLM) -> None:
    """Send a minimal prompt to the model, retrying on transient failure.

    Args:
        llm: The model instance to probe.

    Returns:
        None.

    Raises:
        Exception: Propagates the final error if all retry attempts fail.
    """
    await llm.ainvoke([HumanMessage(content="ping")])


async def test_llm_connection() -> bool:
    """Probe LLM reachability by sending a minimal prompt.

    Used by the application's health-check endpoint. Applies the tenacity retry
    policy, records the call in Prometheus, and never raises — any error after
    retries is reported as ``False``.

    Returns:
        ``True`` if the model responds, ``False`` otherwise.
    """
    settings = get_settings()
    model = settings.LITELLM_MODEL
    start = time.perf_counter()
    try:
        llm = get_llm(model)
        await _ping_llm(llm)
    except Exception as exc:  # noqa: BLE001 - health probe must swallow failures
        record_llm_call(model, "health", "error", time.perf_counter() - start)
        _logger.error("llm_connection_failed", error=str(exc))
        return False
    record_llm_call(model, "health", "success", time.perf_counter() - start)
    _logger.info("llm_connection_ok")
    return True


def get_langfuse_client() -> Langfuse:
    """Return the process-wide Langfuse client (for non-LangChain observations)."""
    return _init_langfuse()


__all__ = [
    "LangfuseTraceContext",
    "get_langfuse_client",
    "get_llm",
    "get_langfuse_callback",
    "get_llm_with_tracing",
    "llm_invoke_config",
    "test_llm_connection",
]
