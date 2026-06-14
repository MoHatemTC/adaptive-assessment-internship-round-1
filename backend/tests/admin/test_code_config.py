"""Tests for global code assessment admin configuration."""

from __future__ import annotations

import pytest

from app.admin.service import get_platform_challenge_config, save_platform_challenge_config
from app.challenges.defaults import DEFAULT_CHALLENGE_CONFIG
from app.challenges.schemas import PlatformChallengeConfig
from app.features.code.constants import SupportedLanguage


class TestAdminCodeConfig:
    @pytest.mark.asyncio
    async def test_get_defaults_when_no_row(self, db_session):
        config = await get_platform_challenge_config(db_session)
        assert config.challenge.challenges_per_candidate == (
            DEFAULT_CHALLENGE_CONFIG.challenge.challenges_per_candidate
        )

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, db_session):
        updated = DEFAULT_CHALLENGE_CONFIG.model_copy(deep=True)
        updated.challenge.total_time_minutes = 90
        updated.challenge.challenges_per_candidate = 2
        await save_platform_challenge_config(db_session, updated)
        loaded = await get_platform_challenge_config(db_session)
        assert loaded.challenge.total_time_minutes == 90
        assert loaded.challenge.challenges_per_candidate == 2

    @pytest.mark.asyncio
    async def test_save_allowed_languages(self, db_session):
        updated = DEFAULT_CHALLENGE_CONFIG.model_copy(deep=True)
        updated.challenge.allowed_languages = [
            SupportedLanguage.PYTHON,
            SupportedLanguage.JAVASCRIPT,
        ]
        updated.challenge.default_language = SupportedLanguage.JAVASCRIPT
        await save_platform_challenge_config(db_session, updated)
        loaded = await get_platform_challenge_config(db_session)
        assert loaded.challenge.allowed_languages == [
            SupportedLanguage.PYTHON,
            SupportedLanguage.JAVASCRIPT,
        ]
        assert loaded.challenge.default_language == SupportedLanguage.JAVASCRIPT


class TestAdminAPI:
    @pytest.mark.asyncio
    async def test_get_code_config(self, client):
        from unittest.mock import AsyncMock, patch

        from app.challenges.defaults import DEFAULT_CHALLENGE_CONFIG

        with patch(
            "app.admin.api.service.get_platform_challenge_config",
            new_callable=AsyncMock,
            return_value=DEFAULT_CHALLENGE_CONFIG,
        ):
            response = await client.get("/api/v1/admin/code-config")
        assert response.status_code == 200
        data = response.json()
        assert "challenge" in data
        assert data["challenge"]["total_time_minutes"] >= 10
