# Code Execution Feature (E2B)

Sprint 1 vertical slice — isolated sandbox execution with weighted test-case grading.

## Architecture

```
api.py → service.py → tool.py → E2B Sandbox
         ↓
      models.py (PostgreSQL)
```

| Layer | Responsibility |
|-------|----------------|
| `api.py` | REST validation, DI, rate limiting |
| `service.py` | Challenge CRUD, submission orchestration, scoring |
| `tool.py` | E2B sandbox execution only |
| `models.py` | SQLModel entities |

## Data Model

```
CodeChallenge 1──* TestCase
CodeChallenge 1──* CodeSubmission
```

## API

Base path: `/api/v1/code`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/challenges` | Create challenge with test cases |
| GET | `/challenges` | List challenges |
| GET | `/challenges/{id}` | Get challenge (hidden expected outputs omitted) |
| POST | `/submissions` | Submit and grade code |
| GET | `/submissions/{id}` | Get submission result |

### Example: create challenge

```bash
curl -X POST http://localhost:8000/api/v1/code/challenges \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Reverse String",
    "description": "Return the reversed string.",
    "starter_code": "def solution(s: str) -> str:\n    pass",
    "test_cases": [
      {"input": "print(solution(\"hello\"))", "expected_output": "olleh", "is_hidden": false}
    ]
  }'
```

### Example: submit code

```bash
curl -X POST http://localhost:8000/api/v1/code/submissions \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_id": 1,
    "session_id": "demo-session",
    "submitted_code": "def solution(s: str) -> str:\n    return s[::-1]"
  }'
```

## E2B Flow

1. Write `solution.py` and `runner.py` into sandbox
2. Runner imports learner code and executes each test case
3. Parse JSON results, compute weighted score (pass threshold 0.6)
4. Hidden test details filtered in API response

Requires `E2B_API_KEY` in environment.

## Development

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
docker compose exec backend alembic -c migrations/alembic.ini upgrade head
```

## Testing

```bash
docker compose exec backend pytest tests/features/test_code.py -v
```

Unit tests mock E2B. Integration tests run when `E2B_API_KEY` is set.
