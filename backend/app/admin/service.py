"""Load and persist global platform code configuration."""

from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import PlatformCodeConfigRow
from app.challenges.defaults import DEFAULT_CHALLENGE_CONFIG
from app.challenges.schemas import PlatformChallengeConfig

_CONFIG_ROW_ID = 1


async def get_platform_challenge_config(db: AsyncSession) -> PlatformChallengeConfig:
    """Return persisted admin config or defaults when no row exists."""
    result = await db.exec(
        select(PlatformCodeConfigRow).where(PlatformCodeConfigRow.id == _CONFIG_ROW_ID)
    )
    row = result.first()
    if row is None:
        return DEFAULT_CHALLENGE_CONFIG.model_copy(deep=True)
    return PlatformChallengeConfig.model_validate_json(row.config_json)


async def save_platform_challenge_config(
    db: AsyncSession,
    config: PlatformChallengeConfig,
) -> PlatformChallengeConfig:
    """Upsert the global platform code configuration."""
    payload = config.model_dump_json()
    result = await db.exec(
        select(PlatformCodeConfigRow).where(PlatformCodeConfigRow.id == _CONFIG_ROW_ID)
    )
    row = result.first()
    if row is None:
        db.add(PlatformCodeConfigRow(id=_CONFIG_ROW_ID, config_json=payload))
    else:
        row.config_json = payload
        db.add(row)
    await db.commit()
    return config
