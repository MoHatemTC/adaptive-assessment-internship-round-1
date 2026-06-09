"""The single LiteLLM/LangChain gateway for every LLM call in the system.

Nothing in the codebase instantiates an LLM client directly — agent nodes,
graders, the judge, and the blueprint generator all go through the factories
here. Centralising this guarantees three platform-wide invariants:

* **Consistent configuration** — one place sets temperature, streaming, retry,
  and API-key wiring, so behaviour can't drift between callers.
* **Automatic observability** — :func:`get_llm_with_tracing` pairs every model
  with a Langfuse callback, satisfying the NFR that *every* LLM call is traced
  with execution time and token cost.
* **Resilience** — retries with backoff are configured once, so transient rate
  limits don't bubble up as user-visible failures.

Langfuse v4 (the OTel-based rewrite) is configured by initialising a singleton
client from settings; the LangChain ``CallbackHandler`` then reads from that
client and takes no key arguments of its own.
"""

from functools import lru_cache

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_litellm import ChatLiteLLM
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler  # VERIFY: v4 LangChain handler path

from app.config import get_settings

#: Low temperature for deterministic grading/assessment behaviour. Kept fixed so
#: scoring stays reproducible across calls and sessions.
_ASSESSMENT_TEMPERATURE = 0.1

#: Retry budget for transient LLM/API errors. LiteLLM applies exponential
#: backoff between attempts.
_MAX_RETRIES = 3


def get_llm(model: str | None = None) -> ChatLiteLLM:
    """Construct a configured :class:`ChatLiteLLM` instance.

    The returned model is tuned for grading/assessment work: low temperature,
    streaming enabled, and bounded retries with exponential backoff.

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
        # VERIFY: api_key kwarg name on langchain-litellm 0.6.6's ChatLiteLLM.
        api_key=settings.LITELLM_API_KEY.get_secret_value(),
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

    Ensures the singleton Langfuse client is initialised, then returns a fresh
    handler bound to it. Attach the result to any LLM/chain invocation to emit
    a trace with execution time and token cost.

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
    configured model and the Langfuse callback wired for automatic tracing.
    Pass the callbacks through to ``.ainvoke(..., config={"callbacks": cbs})``
    or the runnable config.

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


async def test_llm_connection() -> bool:
    """Probe LLM reachability by sending a minimal prompt.

    Used by the application's health-check endpoint. Never raises — any error
    (auth, network, provider outage) is reported as ``False``.

    Returns:
        ``True`` if the model responds, ``False`` otherwise.
    """
    try:
        llm = get_llm()
        await llm.ainvoke([HumanMessage(content="ping")])
    except Exception:  # noqa: BLE001 - health probe must swallow all failures
        return False
    return True


__all__ = [
    "get_llm",
    "get_langfuse_callback",
    "get_llm_with_tracing",
    "test_llm_connection",
]
