# Diagram Feature — Sprint 1

**Owner:** Mohamed Abutaleb  
**Branch:** `viz-tool`

---

## Overview

Delivers image-based assessment items to learners, accepts text answers, and grades them silently using an LLM vision model. The grading result feeds a four-layer adaptive loop that tracks per-learner skill estimates and selects the next question's difficulty.

---

## Structure

```
backend/app/features/diagram/
├── __init__.py            # exports router
├── api.py                 # GET /diagram/{id}, POST /diagram/{id}/answer
├── models.py               # DiagramQuestion + DiagramAnswer ORM models
├── schemas.py               # Pydantic request/response shapes
├── service.py               # image validation, vision grading logic
├── tool.py                 # LangChain tool wrapper for the agent
├── grading.py               # rubric grader + LLM judge validation
├── evaluation_memory.py      # writes trusted grades to VisualMemoryCard / Qdrant
├── analysis.py               # aggregates memory cards into per-dimension estimates
└── adaptation.py             # selects next difficulty/topic from analysis + profile + blueprint
backend/migrations/versions/
└── 0001_diagram.py
backend/tests/features/
├── test_diagram.py            # image validation, API round-trip, vision format
├── test_diagram_grading.py            # grader/judge scoring and trust gating
├── test_diagram_memory.py   # memory card construction and persistence
├── test_diagram_analysis.py            # dimension aggregation, recency weighting, confidence
└── test_diagram_adaptation.py          # difficulty selection, clamping, quota handling
```

---

## Database

Two tables added via migration `0001_diagram`:

**`diagram_questions`** — the assessment item
`id` · `image_url` · `prompt` · `rubric` · `difficulty` · `dimension` · `created_at`

**`diagram_responses`** — the learner's response per session (replaces legacy `diagram_answers`)
`id` · `session_id` · `question_id` · `answer_text` · `score` · `grading_feedback` · `graded_at` · `submitted_at`

Run the migration:

```bash
alembic upgrade head
```

---

## API

### `GET /diagram/{question_id}`

Returns the item delivered to the learner. Rubric is **excluded** — it stays server-side for grading only.

```json
{
  "id": "...",
  "image_url": "https://cdn.example.com/q1.jpg",
  "prompt": "Label the parts of this network diagram.",
  "difficulty": "medium",
  "dimension": "digital_ai"
}
```

### `POST /diagram/{question_id}/answer`

Accepts the learner's text answer, persists it, grades it silently, and returns a structured result to the agent. Score is never shown to the learner mid-session.

**Request:**

```json
{
  "session_id": "...",
  "answer_text": "The router is in the centre connected to three switches."
}
```

**Response:**

```json
{
  "answer_id": "...",
  "session_id": "...",
  "question_id": "...",
  "score": 0.8,
  "dimension": "digital_ai",
  "grading_feedback": "Correct router identified; missed one switch label.",
  "graded_at": "2024-01-01T00:00:00"
}
```

---

## Image Validation

Before the image is passed to the vision model, `service.py` enforces:

- **Allowed types:** `image/jpeg`, `image/png`, `image/webp`, `image/gif`
- **Max size:** 5 MB

Requests that fail either check raise a `ValueError` and return `422`.

> **Note:** The image is always passed to the model as a `base64` vision content block — never described as text. Describing the image as text and sending that to the model (the "image as text stub" anti-pattern) is explicitly out of scope.

---

## LangChain Tool

`tool.py` wraps the feature as a `BaseTool` so the examiner agent can invoke it when the blueprint calls for a diagram question. The agent receives the structured grading result and uses `score` + `dimension` to select the next question difficulty.

---

## Adaptive Loop

After `POST /diagram/{question_id}/answer` grades a response, four layers run in sequence to decide what the learner sees next. `grading.py` runs an LLM rubric grader to score the answer per dimension, then a second LLM judge call checks that grade for hallucination or inconsistency before it's trusted. `evaluation_memory.py` persists a trusted grade as a `VisualMemoryCard` in Qdrant — an untrusted grade (failed judge) is never written. `analysis.py` reads a session's accumulated memory cards and computes a recency-weighted score plus a confidence value for each skill dimension. `adaptation.py` combines those dimension estimates with the learner profile and the admin's blueprint config to pick the next question's difficulty and topic, clamped to the configured range, or to signal that the quota for this question type is exhausted.

Each layer takes the previous layer's typed output directly, so no untyped dicts cross a boundary. The only I/O in the chain is the grading LLM calls and the Qdrant read/write; analysis and the core selection logic in adaptation are pure functions.

---

## Tests

```bash
# test diagram feature
docker compose exec backend pytest tests/features/test_diagram.py -v

# test diagram grading layer
docker compose exec backend pytest backend/tests/features/test_diagram_grading.py -v

# test diagram evaluation_memory layer
docker compose exec backend pytest backend/tests/features/test_diagram_memory.py -v

# test diagram analysis layer
docker compose exec backend pytest backend/tests/features/test_diagram_analysis.py -v

# test diagram adaptation layer
docker compose exec backend pytest backend/tests/features/test_diagram_adaptation.py -v
```

`test_diagram.py` covers:

| Test                                          | Covers                                      |
| --------------------------------------------- | ------------------------------------------- |
| `test_rejects_bad_mime`                       | Rejects non-image MIME types                |
| `test_rejects_oversized`                      | Rejects images over 5 MB                    |
| `test_accepts_valid_jpeg`                     | Accepts valid JPEG, returns base64          |
| `test_get_question_shape`                     | GET returns correct fields, rubric excluded |
| `test_get_question_404`                       | GET returns 404 for missing question        |
| `test_submit_answer_returns_grading`          | POST persists answer, returns score         |
| `test_vision_message_has_image_content_block` | Image sent as vision block, not text        |
| `test_vision_image_is_data_uri`               | Vision block uses `data:` URI format        |
