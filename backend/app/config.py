"""Application configuration — the single typed source of truth for env config.

Every environment variable consumed anywhere in the Masaar backend is declared,
typed, and validated here. No other module reads ``os.environ`` directly; they
all call :func:`get_settings` instead. Secrets are wrapped in
:class:`pydantic.SecretStr` so they never leak into logs, tracebacks, or
``repr`` output.

This module follows the reference template's ``config.py`` pattern: a
Pydantic v2 ``BaseSettings`` class loaded from ``.env``, exposed through a
cached singleton, with ``is_development`` / ``is_production`` helpers that other
kernel modules branch on (logging renderer, checkpointer fallback, etc.).
"""

from functools import lru_cache
from typing import Final

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Recognised deployment environments.
_ALLOWED_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {"development", "staging", "production"}
)

#: Required SQLAlchemy async URL scheme for the primary database.
_REQUIRED_DB_PREFIX: Final[str] = "postgresql+asyncpg://"


class Settings(BaseSettings):
    """Strongly typed, validated application settings.

    Settings are loaded from the process environment and, as a fallback, from a
    ``.env`` file in the working directory. Field names are matched
    case-insensitively. Unknown environment variables (for example ``SMTP_*``
    and ``E2B_API_KEY``, which are owned by feature modules rather than the
    kernel) are ignored rather than rejected.

    Attributes:
        DATABASE_URL: Async SQLAlchemy connection URL. Must use the
            ``postgresql+asyncpg://`` scheme.
        REDIS_URL: Redis connection URL used by the Celery broker/result
            backend and other transient state.
        LITELLM_API_KEY: API key forwarded to LiteLLM for LLM calls.
        LITELLM_BASE_URL: Optional base URL for a LiteLLM proxy/gateway. Empty
            string means use the provider's default endpoint.
        LITELLM_MODEL: Default model identifier used when a caller does not
            specify one explicitly.
        LITELLM_VISION_MODEL: Optional vision/VLM model for diagram grading.
            When empty, ``LITELLM_MODEL`` is used (e.g. Kimi K2.6 multimodal).
        DEEPGRAM_API_KEY: API key for the Deepgram speech-to-text service.
        TRANSCRIPTION_MODEL: LiteLLM model identifier used for speech-to-text
            transcription (e.g. ``"azure/whisper"``).
        QDRANT_URL: Base URL of the Qdrant vector database.
        QDRANT_API_KEY: API key for Qdrant (may be empty for local instances).
        QDRANT_COLLECTION: Name of the Qdrant collection that stores platform
            memory-card vectors.
        EMBEDDING_MODEL: SentenceTransformers model id used to embed memory-card
            evidence summaries before upserting them to Qdrant.
        LANGFUSE_PUBLIC_KEY: Langfuse public key for observability tracing.
        LANGFUSE_SECRET_KEY: Langfuse secret key for observability tracing.
        LANGFUSE_HOST: Base URL of the Langfuse server.
        SECRET_KEY: Symmetric key used to sign and verify admin JWT tokens.
        ENVIRONMENT: Deployment environment; one of ``development``,
            ``staging``, or ``production``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database / cache ──────────────────────────────────────────────────────
    DATABASE_URL: str
    REDIS_URL: str

    # ── LLM gateway ───────────────────────────────────────────────────────────
    LITELLM_API_KEY: SecretStr
    LITELLM_BASE_URL: str = ""
    LITELLM_MODEL: str = "gpt-4o"
    LITELLM_VISION_MODEL: str = ""

    # ── Speech-to-text ────────────────────────────────────────────────────────
    # The correct env var name confirmed by the infrastructure team
    TRANSCRIPTION_MODEL: str = "azure/whisper"

    # ── Vector database ───────────────────────────────────────────────────────
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "platform_memory"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # ── Observability ─────────────────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: SecretStr
    LANGFUSE_SECRET_KEY: SecretStr
    LANGFUSE_HOST: str

    # ── Security / runtime ────────────────────────────────────────────────────
    SECRET_KEY: SecretStr
    ENVIRONMENT: str = "development"

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """Ensure the database URL targets the async ``asyncpg`` driver.

        Args:
            value: The raw ``DATABASE_URL`` value.

        Returns:
            The validated, unmodified database URL.

        Raises:
            ValueError: If the URL does not start with
                ``postgresql+asyncpg://``.
        """
        if not value.startswith(_REQUIRED_DB_PREFIX):
            raise ValueError(
                f"DATABASE_URL must start with {_REQUIRED_DB_PREFIX!r} "
                "so SQLAlchemy uses the asyncpg async driver."
            )
        return value

    @field_validator("ENVIRONMENT")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        """Ensure ``ENVIRONMENT`` is one of the recognised deployment targets.

        Args:
            value: The raw ``ENVIRONMENT`` value.

        Returns:
            The validated, unmodified environment name.

        Raises:
            ValueError: If the value is not one of ``development``, ``staging``,
                or ``production``.
        """
        if value not in _ALLOWED_ENVIRONMENTS:
            allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
            raise ValueError(f"ENVIRONMENT must be one of: {allowed}.")
        return value

    @property
    def is_development(self) -> bool:
        """Whether the app is running in the development environment.

        Returns:
            ``True`` if ``ENVIRONMENT`` is ``development``, otherwise ``False``.
        """
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Whether the app is running in the production environment.

        Returns:
            ``True`` if ``ENVIRONMENT`` is ``production``, otherwise ``False``.
        """
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    The result is cached so the environment is read and validated exactly once
    per process. Import-time and request-time callers share the same instance.

    Returns:
        The cached, validated application settings.
    """
    return Settings()


__all__ = ["Settings", "get_settings"]
