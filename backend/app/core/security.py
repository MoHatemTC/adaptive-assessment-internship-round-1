"""Cryptographic primitives for learner sessions and admin authentication.

This module is intentionally *pure crypto*: it generates and verifies tokens and
builds standard error responses, but it never touches the database. The DB
lookups that pair with these helpers (resolving a hashed token to a session row,
loading an admin) live in :mod:`app.core.deps`.

Two distinct auth mechanisms live here:

* **Learner session tokens** — opaque, high-entropy random strings produced by
  :func:`generate_session_token`. They are *not* JWTs; they carry no claims and
  are meaningless until looked up in the database. Only their SHA-256 digest
  (:func:`hash_token`) is stored, so a database leak never exposes a usable
  token.
* **Admin access tokens** — signed JWTs (HS256) produced by
  :func:`create_access_token` and validated by :func:`verify_access_token`,
  carrying short-lived claims for privileged admin endpoints.

Logging note: only token *events* are logged (generation, verification
failure) — never token values, raw or hashed.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import get_settings
from app.core.logging import get_logger

_logger = get_logger(__name__)

#: JWT signing algorithm for admin access tokens.
ALGORITHM = "HS256"

#: Fallback admin access-token lifetime when settings are unavailable (minutes).
_DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 30

#: Number of random bytes backing an opaque learner session token. 32 bytes of
#: entropy is well beyond brute-force reach; ``token_urlsafe`` encodes them as a
#: ~43-character URL-safe string.
SESSION_TOKEN_NBYTES = 32


def generate_session_token() -> str:
    """Generate a new opaque, URL-safe learner session token.

    The returned value is the *raw* token handed to the learner's client. Only
    its hash (see :func:`hash_token`) should ever be persisted.

    Returns:
        A cryptographically random, URL-safe token string.
    """
    token = secrets.token_urlsafe(SESSION_TOKEN_NBYTES)
    _logger.info("session_token_generated")
    return token


def hash_token(token: str) -> str:
    """Hash a raw token for storage or lookup.

    Tokens are stored as their SHA-256 digest so the database never holds a
    value that could be replayed if leaked. The same function is used both when
    persisting a freshly issued token and when looking one up on a later
    request.

    Args:
        token: The raw token string.

    Returns:
        The lowercase hex-encoded SHA-256 digest of ``token``.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed admin access token (JWT).

    A copy of ``data`` is used as the token's claims, with an ``exp`` expiry
    claim added. The token is signed with the application ``SECRET_KEY`` using
    HS256.

    Args:
        data: Claims to embed in the token (for example ``{"sub": admin_id}``).
            The mapping is copied, not mutated.
        expires_delta: Optional custom lifetime. Defaults to
            ``ACCESS_TOKEN_EXPIRE_MINUTES`` from settings.

    Returns:
        The encoded, signed JWT string.
    """
    to_encode = data.copy()
    settings = get_settings()
    expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=expire_minutes)
    )
    to_encode["exp"] = expire
    secret_key = get_settings().SECRET_KEY.get_secret_value()
    encoded = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    _logger.info("access_token_created")
    return encoded


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate an admin access token.

    Verifies the signature and expiry. Any failure — bad signature, expired
    token, malformed input — is reported as ``None`` rather than an exception,
    so callers can branch cleanly.

    Args:
        token: The encoded JWT to validate.

    Returns:
        The decoded claims payload if the token is valid, otherwise ``None``.
    """
    secret_key = get_settings().SECRET_KEY.get_secret_value()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, secret_key, algorithms=[ALGORITHM]
        )
    except JWTError as exc:
        _logger.warning("token_verification_failed", error=str(exc))
        return None
    return payload


def credentials_exception() -> HTTPException:
    """Build the standard ``401 Unauthorized`` response for auth failures.

    Centralising this keeps admin-auth error responses identical across every
    route that depends on it.

    Returns:
        A pre-configured :class:`~fastapi.HTTPException` with status 401 and a
        ``WWW-Authenticate: Bearer`` header.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def session_not_found_exception() -> HTTPException:
    """Build the standard ``404 Not Found`` response for missing sessions.

    Returned when a learner session token does not resolve to a live,
    unexpired session.

    Returns:
        A pre-configured :class:`~fastapi.HTTPException` with status 404.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Assessment session not found or expired.",
    )


__all__ = [
    "generate_session_token",
    "hash_token",
    "create_access_token",
    "verify_access_token",
    "credentials_exception",
    "session_not_found_exception",
]
