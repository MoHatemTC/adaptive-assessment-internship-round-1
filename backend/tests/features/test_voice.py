import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.base_tool import BaseTool
from app.core.database import Base, async_session, engine
from app.core.deps import get_db
from app.features.voice import service as voice_service
from app.features.voice.api import router as voice_router
from app.features.voice.models import VoiceSession, VoiceTranscript
from app.features.voice.service import (
    create_voice_session,
    end_voice_session,
    get_voice_session,
    start_voice_session,
    stream_audio_chunk,
)
from app.features.voice.tool import VoiceTool


async def reset_voice_tables() -> None:
    """
    Create voice tables if needed and clean voice data before each DB test.

    Tables are registered on the SQLAlchemy 2.0 ``Base`` metadata. Transcripts
    are deleted before sessions to respect the foreign key. The shared test
    engine is configured in ``tests/conftest.py`` (session-scoped loop + NullPool).
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        await db.exec(delete(VoiceTranscript))
        await db.exec(delete(VoiceSession))
        await db.commit()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    await reset_voice_tables()

    async with async_session() as db:
        try:
            yield db
        finally:
            await db.rollback()
            await db.close()


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Test replacement for ``get_db`` that commits like the real dependency."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.mark.asyncio
async def test_create_voice_session(db_session):
    voice_session = await create_voice_session(
        db=db_session,
        session_id="session-1",
        time_limit=120,
    )
    await db_session.commit()

    saved = (await db_session.exec(select(VoiceSession))).all()

    assert len(saved) == 1
    assert saved[0].id == voice_session.id
    assert saved[0].session_id == "session-1"
    assert saved[0].status == "pending"
    assert saved[0].time_limit_seconds == 120


@pytest.mark.asyncio
async def test_start_voice_session(db_session):
    voice_session = await create_voice_session(
        db=db_session,
        session_id="session-1",
        time_limit=60,
    )
    await db_session.commit()

    started = await start_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )
    await db_session.commit()

    assert started.status == "active"
    assert started.started_at is not None


@pytest.mark.asyncio
async def test_end_voice_session(db_session):
    voice_session = await create_voice_session(
        db=db_session,
        session_id="session-1",
        time_limit=60,
    )
    await db_session.commit()
    await start_voice_session(db=db_session, voice_session_id=voice_session.id)
    await db_session.commit()

    final_transcript = await end_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )
    await db_session.commit()

    ended = await get_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )

    assert ended.status == "completed"
    assert ended.ended_at is not None
    assert isinstance(final_transcript, str)


@pytest.mark.asyncio
async def test_transcript_stored_per_chunk(db_session, monkeypatch):
    voice_session = await create_voice_session(
        db=db_session,
        session_id="session-1",
        time_limit=60,
    )
    await db_session.commit()

    async def fake_transcribe(audio_chunk: bytes, settings, logger) -> tuple[str, float]:
        return "hello world", 0.95

    # Isolate the LiteLLM transcription call — no network during tests.
    monkeypatch.setattr(voice_service, "_transcribe_chunk", fake_transcribe)

    chunk = await stream_audio_chunk(voice_session.id, b"fake-audio-bytes")

    assert chunk.voice_session_id == voice_session.id
    assert chunk.chunk_index == 0
    assert chunk.transcript_text == "hello world"
    assert chunk.is_final is True

    saved = (
        await db_session.exec(
            select(VoiceTranscript).where(
                VoiceTranscript.voice_session_id == voice_session.id
            )
        )
    ).all()

    assert len(saved) == 1
    assert saved[0].chunk_index == 0
    assert saved[0].transcript_text == "hello world"
    assert saved[0].speaker_confidence == 0.95
    assert saved[0].is_final is True


def test_voice_tool_conforms_to_base_tool():
    tool = VoiceTool()

    assert isinstance(tool, BaseTool)
    assert tool.tool_name == "voice_tool"
    assert tool.tool_description is not None
    assert tool.build_graph() is not None


@pytest.mark.asyncio
async def test_server_side_time_limit_enforcement(db_session):
    """A session past its time limit is ended cleanly by the server."""
    voice_session = await create_voice_session(
        db=db_session,
        session_id="session-1",
        time_limit=1,
    )
    await db_session.commit()

    session = await start_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )
    # Backdate the start so the 1-second limit is already exceeded.
    session.started_at = datetime.now(timezone.utc) - timedelta(seconds=2)
    await db_session.flush()

    await end_voice_session(db=db_session, voice_session_id=voice_session.id)
    await db_session.commit()

    ended = await get_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )

    assert ended.status == "completed"
    assert ended.ended_at is not None


@pytest.mark.asyncio
async def test_empty_transcript_handling(db_session):
    """Ending a session with no transcript chunks returns "" without crashing."""
    voice_session = await create_voice_session(
        db=db_session,
        session_id="session-1",
        time_limit=60,
    )
    await db_session.commit()
    await start_voice_session(db=db_session, voice_session_id=voice_session.id)
    await db_session.commit()

    final_transcript = await end_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )
    await db_session.commit()

    ended = await get_voice_session(
        db=db_session,
        voice_session_id=voice_session.id,
    )

    assert final_transcript == ""
    assert ended.status == "completed"


# Kept last: this test drives the app through TestClient via ``asyncio.run``,
# which opens and closes its own event loop on the module-global engine. Any
# async DB test running after it would inherit stale pooled connections, so the
# new async tests above must precede it (mirrors the MCQ reference ordering).
def test_submit_voice_session_round_trip():
    """Create a voice session over HTTP and assert the response shape."""
    asyncio.run(reset_voice_tables())

    app = FastAPI()
    app.include_router(voice_router)
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        create_response = client.post(
            "/voice/sessions",
            json={
                "session_id": "session-1",
                "time_limit_seconds": 90,
            },
        )

    assert create_response.status_code == 200

    body = create_response.json()
    assert body["session_id"] == "session-1"
    assert body["status"] == "pending"
    assert body["time_limit_seconds"] == 90
    assert "id" in body
