# Voice Interview Tool — Sprint 2

Owner: Karim · Branch: `voice-agent`

## Overview

The voice tool runs a **time-boxed, adaptive voice interview** end to end. A
learner is asked a question, records a spoken answer that is streamed over a
WebSocket and transcribed in real time (Azure Whisper via the Sprints LiteLLM
proxy), and on completion the backend silently grades the transcript, extracts
an evidence memory card, aggregates the learner's skill-dimension estimates, and
generates the **next** question at a difficulty matched to demonstrated mastery.
The learner only ever sees the next question — no scores, no correctness, no
feedback. Grading is silent by law.

## Architecture — Four-Layer Adaptive Loop

After each recording ends, `run_voice_adaptive_loop` (the orchestrator) runs the
layers in sequence:

- **Layer 5+6 — Evaluation** (`evaluation.py`): assembles the transcript
  (chunks ordered by `chunk_index`), detects flags
  (`timed_out` / `failed` / `empty_transcript` / `low_confidence`), grades clean
  transcripts with the kernel LLM gateway, writes a `grade_results` row, and —
  only for clean responses — calls `run_memory_agent` to write a `MemoryCard`.
- **Layer 7 — Analysis** (`analysis.py`): loads every voice `MemoryCard` for the
  session, tallies the boolean dimension signals into per-dimension engagement
  rates, derives an overall mastery level (`low` / `medium` / `high`), and writes
  a `skill_dimension_scores` row.
- **Layer 8 — Adaptation** (`adaptation.py`): selects the next difficulty from
  mastery level within the admin-configured `max_difficulty` ceiling, generates
  the next question (targeting the weakest dimension) with the LLM, and builds
  the `AdaptiveContract` (never persisted).
- **Orchestrator** (`loop.py`): wires Layers 5+6 → 7 → 8 and returns the
  internal `VoiceAdaptiveOutput` with the contract embedded.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/voice/sessions` | Create a Sprint 1 voice session (`pending`). |
| `WS` | `/voice/sessions/{voice_session_id}/stream` | Stream binary audio, receive `transcript_delta` messages. |
| `GET` | `/voice/sessions/{voice_session_id}/transcript` | List stored transcript chunks in order. |
| `POST` | `/voice/sessions/{voice_session_id}/end` | End the session, return the assembled transcript. |
| `POST` | `/voice/adaptive/sessions` | Create an adaptive session, returns a `voice_session_id`. |
| `POST` | `/voice/adaptive/sessions/{voice_session_id}/process` | Run the full adaptive loop; returns the next question (sanitized). |
| `GET` | `/voice/adaptive/sessions/{session_id}/analysis` | Session state — mastery level and focus dimension only, no raw scores. |

## Data Flow

From the moment a recording ends to the next question appearing:

1. The WebSocket stream closes (client disconnect or time limit) and the session
   is finalized; chunks are persisted to `voice_transcripts`.
2. The frontend calls `POST /voice/adaptive/sessions/{id}/process`.
3. **Evaluation** loads the `VoiceSession` and concatenates its transcript
   chunks, averaging `speaker_confidence`.
4. Flags are detected in priority order (`timed_out` → `failed` →
   `empty_transcript` → `low_confidence`).
5. A clean transcript is graded by the LLM into `RubricScores`; a flagged one
   gets a zero rubric and skips the LLM entirely.
6. A `grade_results` row is written for every response, flagged or not.
7. For clean responses only, communication signals are computed and
   `run_memory_agent` writes a `MemoryCard`; flagged responses skip memory
   extraction.
8. **Analysis** aggregates all voice memory cards into dimension rates, derives
   mastery, and writes a `skill_dimension_scores` row.
9. **Adaptation** selects the next difficulty (bounded by admin `max_difficulty`)
   and generates the next question targeting the weakest dimension.
10. The orchestrator embeds the `AdaptiveContract`; the API strips it down to
    navigation data and returns `VoiceAdaptivePublicResponse` to the frontend,
    which renders the next question.

## Silent Grading Guarantee

The learner **never** sees scores, pass/fail, confidence values, rubric
feedback, memory card contents, or dimension scores.

`VoiceAdaptiveOutput` is the **internal** object that carries all of those
signals between layers. It never crosses the API boundary. The boundary is
`VoiceAdaptivePublicResponse`, returned by `POST /…/process`, which exposes only:

- `session_id`, `voice_session_id`, `question_index`
- `flagged` (a boolean with no reason attached)
- `adaptive_contract` reduced to navigation fields only:
  `next_question_text`, `difficulty`, `follow_up_depth`, `stop`,
  `question_index`

Notably, `memory_summary`, `focus_dimension`, and `cumulative_scores` — which are
present in the internal contract — are stripped before the response is returned.
Transcript text, average confidence, rubric scores, `grade_result_id`,
`memory_card_id`, and `flag_reason` are never serialized to the learner.

## STT Integration — Cost and Accuracy Trade-offs

### Why Azure Whisper via LiteLLM proxy

- **Consolidated billing:** All LLM and STT calls route through
  the same Sprints proxy endpoint, one API key, one cost center.
- **No separate SDK:** Deepgram SDK 7.x required its own client,
  auth flow, and connection management. LiteLLM's atranscription()
  provides a uniform interface.
- **Vendor flexibility:** Swapping the STT model requires one
  .env change (TRANSCRIPTION_MODEL=...) with no code changes.

### Accuracy comparison

| Factor | Azure Whisper (via proxy) | Deepgram Nova-2 |
|---|---|---|
| WER on clear speech | ~3-5% | ~2-3% |
| WER on accented speech | ~8-15% | ~5-10% |
| Real-time streaming | No (batch per chunk) | Yes (live tokens) |
| Confidence scores | Per-segment no_speech_prob | Per-word confidence |
| Cold start latency | ~300-600ms per chunk | ~50-100ms streaming |

### Cost implications

Whisper via proxy charges per audio minute. At 120s per voice
question with up to 10 questions per session, maximum cost is
~20 audio minutes per full assessment. At current proxy rates
this is negligible for an MVP but should be monitored at scale.

### Current status and degradation

Audio transcriptions route returns 404 on the Sprints proxy
for azure/whisper — proxy config pending from infrastructure team.
When STT is unavailable:
- Each chunk returns ("", 0.0) from _transcribe_chunk
- _detect_flag returns "empty_transcript"
- run_memory_agent is skipped (no memory card written)
- Adaptive loop continues with LLM-only question generation
- Dimension scores reflect question difficulty only

### Upgrade path

If latency or accuracy becomes a production concern, replace
_transcribe_chunk to use Deepgram Nova-2 streaming by:
1. Re-add deepgram-sdk>=7.2.0 to requirements.txt
2. Add DEEPGRAM_API_KEY to config.py and .env
3. Replace litellm.atranscription() with AsyncDeepgramClient
The rest of the evaluation layer (flagging, grading, memory)
is STT-agnostic and requires no changes.

## Running Tests

```bash
docker compose exec backend pytest tests/features/test_voice.py -v
docker compose exec backend pytest tests/features/test_voice_evaluation.py -v
docker compose exec backend pytest tests/features/test_voice_analysis.py -v
docker compose exec backend pytest tests/features/test_voice_loop.py -v
```

All LLM and database calls are mocked, so no network, API key, or live database
is required to run the suites.

## Known Limitations

- **STT not operational:** the `azure/whisper` transcriptions route is pending
  proxy configuration; live transcription returns `404` until then.
- **Internal vs. public memory summary:** `memory_summary` is present in the
  internal `VoiceAdaptiveOutput` (and the raw `AdaptiveContract`) but is stripped
  from the API response via `VoiceAdaptivePublicResponse`.
- **Fallback grading:** when a transcript is empty or flagged, dimension scores
  are based on fallback grading (difficulty progression), not response quality,
  and no memory card is written.
