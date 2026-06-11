# Voice Interview Feature

Owner: Karim — Sprint 1

The voice feature provides an end-to-end vertical slice for a **time-boxed voice
interview**: create a session, stream microphone audio over a WebSocket for
real-time Deepgram transcription, persist each transcript chunk, and finalize
the session into a single assembled transcript for the silent LLM judge.

## Files

| File | Responsibility |
|------|----------------|
| `models.py` | `VoiceSession` and `VoiceTranscript` SQLAlchemy 2.0 models. |
| `schemas.py` | Pydantic v2 request/response schemas. |
| `service.py` | Session lifecycle, per-chunk persistence, Deepgram STT call. |
| `tool.py` | `VoiceTool` LangGraph subgraph (`BaseTool` contract). |
| `api.py` | REST endpoints + the audio-streaming WebSocket. |
| `../../../migrations/versions/0001_voice.py` | Alembic migration for both tables. |
| `../../../tests/features/test_voice.py` | Feature test suite. |
| `frontend/src/features/voice/VoiceRecorder.tsx` | Recorder UI (idle/recording/completed). |
| `frontend/src/hooks/useVoiceRecorder.ts` | Capture + WebSocket + countdown hook. |

## API Endpoints

- `POST /voice/sessions` — create a new voice session
- `WS /voice/sessions/{voice_session_id}/stream` — stream binary audio, receive transcript deltas
- `GET /voice/sessions/{voice_session_id}/transcript` — list stored transcript chunks
- `POST /voice/sessions/{voice_session_id}/end` — end the session and assemble the final transcript

### `POST /voice/sessions`

Request:

```json
{
  "session_id": "session-abc123",
  "time_limit_seconds": 90
}
```

Response (`200 OK`):

```json
{
  "id": 1,
  "session_id": "session-abc123",
  "status": "pending",
  "time_limit_seconds": 90,
  "started_at": null,
  "ended_at": null,
  "created_at": "2026-06-11T12:00:00Z"
}
```

### `GET /voice/sessions/1/transcript`

Response (`200 OK`):

```json
[
  {
    "voice_session_id": 1,
    "chunk_index": 0,
    "transcript_text": "hello world",
    "is_final": true
  }
]
```

### `POST /voice/sessions/1/end`

Response (`200 OK`):

```json
{
  "session_id": "session-abc123",
  "final_transcript": "hello world this is my answer",
  "duration_seconds": 42
}
```

A missing `voice_session_id` returns `404 Not Found`.

## WebSocket Protocol

Endpoint: `WS /voice/sessions/{voice_session_id}/stream`

- **Client → server:** raw binary audio frames (e.g. `MediaRecorder` chunks).
  No text frames are expected.
- **Server → client:** JSON messages.

On connect the session is marked `active`. Each audio frame is transcribed and
persisted, and a delta is echoed back:

```json
{ "type": "transcript_delta", "text": "hello world", "is_final": true }
```

When the client disconnects **or** the time limit elapses, the server finalizes
the session and (if the socket is still open) sends a final message before
closing:

```json
{ "type": "session_complete", "final_transcript": "hello world this is my answer" }
```

If the session id does not exist, the socket is closed with policy-violation
code `1008`.

## Running Locally

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up backend
```

Apply migrations (creates `voice_sessions` and `voice_transcripts`):

```bash
docker compose exec backend alembic upgrade head
```

The feature router is auto-discovered by `app.main:create_app` (no manual
registration). It requires `DEEPGRAM_API_KEY` to be set in the environment for
live transcription.

## Running Tests

```bash
docker compose exec backend pytest tests/features/test_voice.py -v
```

The Deepgram call (`_transcribe_chunk`) is mocked in tests, so no network or API
key is required to run the suite.

## Design Decisions

- **Time-boxing:** every session carries `time_limit_seconds`. The WebSocket
  loop wraps each receive in a deadline, so the interview auto-stops when the
  limit is reached; the `VoiceTool` subgraph mirrors this with a `check_time`
  conditional edge that routes to `end_interview`.
- **Real-time STT:** audio is streamed in chunks and transcribed per chunk via
  the Deepgram SDK v7 `AsyncDeepgramClient`
  (`listen.v1.media.transcribe_file`). The actual SDK call is isolated in
  `service._transcribe_chunk` so it is a single seam to mock and to harden.
  Each chunk is persisted to `voice_transcripts` with its order index.
- **Silent scoring:** the assembled transcript is persisted in full for the LLM
  judge and admin reporting; no score or correctness signal is ever returned to
  the learner through the API or the WebSocket.
- **Own session for streaming:** `stream_audio_chunk` and the tool's graph nodes
  run outside the FastAPI request lifecycle, so they open their own
  `async_session` and commit explicitly, following the MCQ tool pattern.
- **`session_id` without a hard FK:** `voice_sessions.session_id` is an indexed
  string linking to the assessment session; the foreign key to
  `assessment_sessions.id` will be added once the sessions feature merges.
- **Tool follows the kernel contract:** `VoiceTool` subclasses
  `app.core.base_tool.BaseTool` and exposes its flow as a compiled LangGraph
  subgraph (`start_interview → check_time → end_interview`).
```
