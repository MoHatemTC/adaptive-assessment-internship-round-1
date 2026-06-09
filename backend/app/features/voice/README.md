# Voice Interview Feature — Sprint 1 — Owner: Karim

## Files
- models.py   — VoiceSession, VoiceTranscript
- schemas.py  — Pydantic schemas
- service.py  — Deepgram STT, session management
- tool.py     — LangGraph voice subgraph
- api.py      — WebSocket stream endpoint

## Run
docker compose -f docker-compose.yml -f docker-compose.dev.yml up backend

## Test
docker compose exec backend pytest tests/features/test_voice.py -v
