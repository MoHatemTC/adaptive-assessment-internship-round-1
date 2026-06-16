# MCQ Feature

Owner: Malak

The MCQ feature provides an end-to-end vertical slice for multiple-choice
assessment questions: create a question, present it to the learner, and grade
the submitted answer objectively and silently against the stored option key.

## API Endpoints

- `POST /mcq/questions` — create a question (returns it without the answer)
- `GET /mcq/questions/{question_id}` — retrieve a question (no answer exposed)
- `POST /mcq/submit` — submit an answer (grading is silent)

## Request/Response Examples

### `POST /mcq/questions`

Request:

```json
{
  "question_text": "What is the output of print(2 + 3)?",
  "difficulty": "easy",
  "correct_option": "5",
  "options": [
    { "label": "2", "text": "2" },
    { "label": "3", "text": "3" },
    { "label": "5", "text": "5" },
    { "label": "23", "text": "23" }
  ]
}
```

Response (`200 OK`) — note the correct answer is never returned:

```json
{
  "id": 1,
  "question_text": "What is the output of print(2 + 3)?",
  "options": [
    { "label": "2", "text": "2" },
    { "label": "3", "text": "3" },
    { "label": "5", "text": "5" },
    { "label": "23", "text": "23" }
  ],
  "difficulty": "easy"
}
```

### `GET /mcq/questions/1`

Response (`200 OK`):

```json
{
  "id": 1,
  "question_text": "What is the output of print(2 + 3)?",
  "options": [
    { "label": "2", "text": "2" },
    { "label": "3", "text": "3" },
    { "label": "5", "text": "5" },
    { "label": "23", "text": "23" }
  ],
  "difficulty": "easy"
}
```

A missing id returns `404 Not Found`.

### `POST /mcq/submit`

Request:

```json
{
  "question_id": 1,
  "session_id": "session-abc123",
  "selected_option": "5",
  "learner_id": "learner-1"
}
```

Response (`200 OK`) — silent acknowledgement only:

```json
{
  "received": true,
  "question_id": 1
}
```

## Running Tests

```bash
docker compose exec backend pytest tests/features/test_mcq.py -v
```

## Design Decisions

- **Grading is silent:** `is_correct` and `score` are persisted on
  `mcq_responses` for the LLM judge and admin reporting, but never returned to
  the learner through the API.
- **Option IDs compared normalized:** the submitted option id and the stored
  correct option are compared lowercased and stripped, so case/whitespace
  differences never cause a false mismatch.
- **No silent fallback:** submitting against a non-existent question raises a
  `404`, instead of grading against a hardcoded default answer.
- **`session_id` on every response:** each response stores its owning
  `session_id` (indexed) so responses are queryable per session. The hard
  foreign key to `assessment_sessions.id` will be added by an Alembic migration
  once the sessions feature is merged.
- **Tool follows the kernel contract:** `MCQTool` subclasses
  `app.core.base_tool.BaseTool` and exposes its grading flow as a compiled
  LangGraph subgraph.
