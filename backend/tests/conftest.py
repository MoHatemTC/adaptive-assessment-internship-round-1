"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import PlatformCodeConfigRow
from app.core.database import get_db
from app.features.code.models import (
    CodeAssessmentSession,
    CodeChallenge,
    CodeChallengeAttempt,
    CodeMemoryCard,
    CodeRun,
    CodeSubmission,
    SessionAuditEvent,
    TestCase,
)
from app.main import app

_CODE_TABLES = [
    PlatformCodeConfigRow.__table__,
    CodeChallenge.__table__,
    TestCase.__table__,
    CodeSubmission.__table__,
    CodeAssessmentSession.__table__,
    CodeChallengeAttempt.__table__,
    CodeRun.__table__,
    CodeMemoryCard.__table__,
    SessionAuditEvent.__table__,
]


@pytest.fixture
def mock_db_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.exec = AsyncMock()
    return session


@pytest.fixture
async def client(mock_db_session: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[MagicMock, None]:
        yield mock_db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run database integration tests")
    return url


@pytest_asyncio.fixture
async def db_engine(database_url: str):
    engine = create_async_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all, tables=_CODE_TABLES)
            await conn.run_sync(SQLModel.metadata.create_all, tables=_CODE_TABLES)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Database unavailable for integration tests: {exc}")
    yield engine
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE code_runs, code_memory_cards, code_challenge_attempts, "
                "session_audit_events, code_assessment_sessions, code_submissions, code_test_cases, "
                "code_challenges, platform_code_config RESTART IDENTITY CASCADE"
            )
        )
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def sample_profile():
    from app.challenges.schemas import UserProfile

    return UserProfile(
        name="Test Learner",
        skills=["Python"],
        experience_level="intermediate",
        preferred_domains=["Programming"],
        learning_objectives=["Practice arrays"],
    )
