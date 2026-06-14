# Diagram Feature — Sprint 1

**Owner:** Mohamed Abutaleb  
**Branch:** `viz-tool`

---

## Overview

Delivers image-based assessment items to learners, accepts text answers, and grades them silently using an LLM vision model.

---

## Structure

```
backend/app/features/diagram/
├── __init__.py       # exports router
├── api.py            # GET /diagram/{id}, POST /diagram/{id}/answer
├── models.py         # DiagramQuestion + DiagramAnswer ORM models
├── schemas.py        # Pydantic request/response shapes
├── service.py        # image validation, vision grading logic
└── tool.py           # LangChain tool wrapper for the agent

backend/migrations/versions/
└── 0001_diagram.py   # migration (chains from 0001_mcq)

backend/tests/features/
└── test_diagram.py   # image validation, API round-trip, vision format
```

---

## Database

Two tables added via migration `0001_diagram`:

**`diagram_questions`** — the assessment item  
`id` · `image_url` · `prompt` · `rubric` · `difficulty` · `dimension` · `created_at`

**`diagram_answers`** — the learner's response per session  
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

## Tests

```bash
docker compose exec backend pytest tests/features/test_diagram.py -v
```

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
