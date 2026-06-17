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

## STT — Trade-off Notes

- **Azure Whisper over a third-party SDK:** STT is called exclusively through
  `litellm.atranscription()` against the Sprints LiteLLM proxy
  (`STT_MODEL=azure/whisper`). This consolidates STT and the grading/generation
  LLM behind a single vendor and proxy, with one set of credentials and no
  separate transcription SDK to install, version, or secure.
- **Current status:** the audio transcriptions route is **not yet configured**
  on the Sprints LiteLLM proxy — `azure/whisper` currently returns `404`. The
  feature is wired and tested, but live transcription is blocked awaiting proxy
  configuration from the infrastructure team.
- **Graceful degradation:** empty or low-confidence transcripts are flagged.
  Flagged responses skip memory extraction entirely, and the adaptive loop
  continues with LLM-only question generation, so a session never hard-fails on
  missing audio.
- **Accuracy implication:** without real transcripts, dimension scores reflect
  question difficulty progression only, not the quality of the learner's spoken
  response. No memory cards are generated for flagged sessions, so those
  responses contribute no evidence to the skill-dimension aggregation.

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
