"""Lightweight E2B availability probe for health endpoints."""

from __future__ import annotations

import os


def test_e2b_connection() -> bool:
    """Return True when E2B is configured and the SDK is importable."""
    if not os.environ.get("E2B_API_KEY"):
        return False
    try:
        import e2b_code_interpreter  # noqa: F401
    except ImportError:
        return False
    return True
