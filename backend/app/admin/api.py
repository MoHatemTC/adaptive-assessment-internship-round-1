"""Admin REST routes for global code assessment configuration."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin import service
from app.challenges.schemas import PlatformChallengeConfig
from app.config import get_settings
from app.core.deps import RateLimitedRoute, get_db

router = APIRouter(prefix="/admin", tags=["admin"], route_class=RateLimitedRoute)


def _verify_admin_key(x_admin_key: str | None) -> None:
    settings = get_settings()
    expected = getattr(settings, "ADMIN_API_KEY", None)
    if expected is None:
        expected = settings.SECRET_KEY.get_secret_value()
    if not expected:
        return
    if x_admin_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Key",
        )


@router.get("/code-config", response_model=PlatformChallengeConfig)
async def get_code_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PlatformChallengeConfig:
    """Read global code challenge and timing configuration."""
    return await service.get_platform_challenge_config(db)


@router.put("/code-config", response_model=PlatformChallengeConfig)
async def put_code_config(
    request: Request,
    payload: PlatformChallengeConfig,
    db: AsyncSession = Depends(get_db),
    x_admin_key: str | None = Header(default=None),
) -> PlatformChallengeConfig:
    """Update global code challenge and timing configuration."""
    _verify_admin_key(x_admin_key)
    return await service.save_platform_challenge_config(db, payload)
