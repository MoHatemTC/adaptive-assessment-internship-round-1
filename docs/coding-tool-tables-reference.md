# Coding-Tool — Database Tables Reference

Required PostgreSQL tables for the **code execution feature** (`backend/app/features/code/`). Lists every column, PostgreSQL data type, allowed values, and what data is stored.

**Migrations:** `0001_code` → `0007_code_memory_cards` (+ `0004` audit/constraints).  
**Models:** `backend/app/features/code/models.py`, `backend/app/admin/models.py`.

For orchestration with the platform agent (separate tables), see [database-schema-coding-tool.md](./database-schema-coding-tool.md).

---

## 1. Required tables (summary)

| # | Table | Rows (typical) | Purpose |
|---|-------|----------------|---------|
| 1 | `platform_code_config` | **1** | Global admin settings for generation and timing |
| 2 | `code_challenges` | Many | LLM-generated or bootstrap coding problems |
| 3 | `code_test_cases` | Many | Visible + hidden tests per challenge |
| 4 | `code_assessment_sessions` | Per learner session | Timed assessment (`assess-*` id) |
| 5 | `code_challenge_attempts` | N per session | One slot per challenge (timers, sandbox) |
| 6 | `code_runs` | Many | Practice runs (visible tests only) |
| 7 | `code_submissions` | ≤ N per session | Final graded submissions |
| 8 | `session_audit_events` | Few per session | Lifecycle audit log |
| 9 | `code_memory_cards` | One per adaptive submit | Silent evaluation snapshots for analysis |

**Apply:**

```bash
docker compose exec backend alembic -c migrations/alembic.ini upgrade 0005_multilanguage
```

---

## 2. Enumerations & domain types

### `SessionStatus` (column: `code_assessment_sessions.status`)

| Value | Meaning |
|-------|---------|
| `active` | Learner can run/submit challenges |
| `completed` | Formally finished (may include unsubmitted with confirm) |
| `expired` | Session or challenge timer elapsed |

**Storage:** `VARCHAR(32)` (SQLAlchemy string enum, not native PG ENUM).

### `SubmissionStatus` (column: `code_submissions.status`)

| Value | Meaning |
|-------|---------|
| `pending` | Created, not yet executed |
| `running` | E2B execution in progress |
| `completed` | Graded successfully |
| `failed` | Sandbox or grading failure |

### `SupportedLanguage` (column: `code_challenges.language`)

| Value | E2B executable |
|-------|----------------|
| `python` | Yes |
| `javascript` | Yes |
| `typescript` | Yes |
| `java`, `go`, `csharp`, `ruby`, `rust`, `cpp` | Generation only (no sandbox runner) |

**CHECK constraint:** language must be one of the nine values above.

### `session_id` format

| Pattern | Example | Used in |
|---------|---------|---------|
| `assess-{12 hex}` | `assess-8b57ef381336` | `code_assessment_sessions.session_id`, `code_submissions.session_id`, `session_audit_events.session_id` |

---

## 3. Table definitions

### 3.1 `platform_code_config`

Single-row configuration store (primary key always `id = 1`).

| Column | PostgreSQL type | Nullable | Description |
|--------|-----------------|----------|-------------|
| `id` | `INTEGER` | NO | Always `1` |
| `config_json` | `TEXT` | NO | JSON string: `PlatformChallengeConfig` |
| `created_at` | `TIMESTAMPTZ` | NO | Row created |
| `updated_at` | `TIMESTAMPTZ` | NO | Last admin update |

**`config_json` structure:**

```json
{
  "challenge": {
    "categories": ["algorithms", "data_structures", "strings", "arrays"],
    "difficulty_levels": ["beginner", "intermediate", "advanced"],
    "challenges_per_candidate": 2,
    "total_time_minutes": 90,
    "min_time_per_challenge_minutes": 10,
    "max_time_per_challenge_minutes": 45,
    "duration_minutes": 20,
    "min_complexity": 1,
    "max_complexity": 5,
    "default_language": "python",
    "allowed_languages": ["python", "javascript", "typescript", "..."],
    "domain": "Programming",
    "e2b_execution_timeout_seconds": 30,
    "e2b_template": "code-interpreter-v1"
  }
}
```

**Example row:**

| id | config_json (abbreviated) |
|----|---------------------------|
| 1 | `{"challenge":{"challenges_per_candidate":2,"total_time_minutes":90,...}}` |

---

### 3.2 `code_challenges`

One row per coding problem (LLM-generated at session start or admin bootstrap).

| Column | PostgreSQL type | Nullable | Constraints | Description |
|--------|-----------------|----------|-------------|-------------|
| `id` | `SERIAL` | NO | PK | Surrogate key |
| `title` | `VARCHAR(255)` | NO | | Short problem name |
| `description` | `TEXT` | NO | | Problem statement (markdown/plain) |
| `starter_code` | `TEXT` | NO | | Monaco editor initial content |
| `language` | `VARCHAR(32)` | NO | CHECK (9 langs) | Execution language |
| `time_limit_seconds` | `INTEGER` | NO | CHECK 1–300 | E2B command timeout per run |
| `candidate_time_seconds` | `INTEGER` | NO | CHECK 60–7200 | Learner working time budget |
| `created_at` | `TIMESTAMPTZ` | NO | | |
| `updated_at` | `TIMESTAMPTZ` | NO | | |

**Example row:**

| id | title | language | time_limit_seconds | candidate_time_seconds |
|----|-------|----------|--------------------|-------------------------|
| 42 | Reverse a String | python | 30 | 1200 |

**`description` example:** `"Given a string s, return its reverse."`  
**`starter_code` example:** `"def solution(s: str) -> str:\n    pass"`

---

### 3.3 `code_test_cases`

Test inputs/outputs executed in E2B. Hidden cases are omitted on practice runs.

| Column | PostgreSQL type | Nullable | Constraints | Description |
|--------|-----------------|----------|-------------|-------------|
| `id` | `SERIAL` | NO | PK | |
| `challenge_id` | `INTEGER` | NO | FK → `code_challenges.id` | Parent challenge |
| `input` | `TEXT` | NO | | Code invoked in sandbox (e.g. `print(solution("abc"))`) |
| `expected_output` | `TEXT` | NO | | Expected stdout (trimmed compare) |
| `is_hidden` | `BOOLEAN` | NO | default `false` | If true, excluded from Run API |
| `weight` | `DOUBLE PRECISION` | NO | CHECK > 0, ≤ 100 | Score weight in weighted grade |
| `created_at` | `TIMESTAMPTZ` | NO | | |
| `updated_at` | `TIMESTAMPTZ` | NO | | |

**Index:** `ix_code_test_cases_challenge_id`

**Example rows (challenge_id = 42):**

| id | input | expected_output | is_hidden | weight |
|----|-------|-----------------|-----------|--------|
| 101 | `print(solution("hello"))` | `olleh` | false | 1.0 |
| 102 | `print(solution(""))` | `` | false | 1.0 |
| 103 | `print(solution("racecar"))` | `racecar` | true | 2.0 |

---

### 3.4 `code_assessment_sessions`

Timed multi-challenge assessment for one learner.

| Column | PostgreSQL type | Nullable | Constraints | Description |
|--------|-----------------|----------|-------------|-------------|
| `id` | `SERIAL` | NO | PK | Internal FK for attempts |
| `session_id` | `VARCHAR(64)` | NO | UNIQUE | Public id `assess-*` |
| `profile_json` | `TEXT` | NO | | JSON: `UserProfile` at session start |
| `config_snapshot` | `TEXT` | NO | | JSON: generation manifest + admin config copy |
| `status` | `VARCHAR(32)` | NO | | `active` \| `completed` \| `expired` |
| `started_at` | `TIMESTAMPTZ` | NO | | UTC session start |
| `expires_at` | `TIMESTAMPTZ` | NO | | UTC session deadline |
| `completed_at` | `TIMESTAMPTZ` | YES | | Set when learner finishes |
| `analysis_json` | `TEXT` | YES | | Cached `LearnerCodeAnalysis` (adaptive sessions) |
| `created_at` | `TIMESTAMPTZ` | NO | | |
| `updated_at` | `TIMESTAMPTZ` | NO | | |

**Index:** `ix_code_assessment_sessions_session_id` (unique)

**`profile_json` example:**

```json
{
  "name": "Alex",
  "skills": ["Python", "JavaScript"],
  "experience_level": "intermediate",
  "interests": [],
  "career_goals": [],
  "preferred_domains": ["Programming"],
  "previous_experience": "",
  "learning_objectives": ["Practice algorithms"],
  "prior_performance_summary": null
}
```

**`config_snapshot` example:**

```json
{
  "platform_config": { "challenge": { "challenges_per_candidate": 2, "total_time_minutes": 90 } },
  "generation_notes": "Assigned Python for slot 1, JavaScript for slot 2.",
  "challenges": [
    {
      "challenge_id": 42,
      "position": 1,
      "title": "Reverse a String",
      "language": "python",
      "difficulty": "intermediate",
      "category": "strings",
      "requirements": ["Handle empty string"],
      "evaluation_criteria": ["Correctness"],
      "max_score": 100,
      "estimated_duration": "20 minutes"
    }
  ]
}
```

**Example row:**

| session_id | status | started_at | expires_at |
|------------|--------|------------|------------|
| assess-8b57ef381336 | active | 2026-06-10T10:00:00Z | 2026-06-10T11:30:00Z |

---

### 3.5 `code_challenge_attempts`

Links one challenge slot to a timed session (timers + sandbox reuse).

| Column | PostgreSQL type | Nullable | Constraints | Description |
|--------|-----------------|----------|-------------|-------------|
| `id` | `SERIAL` | NO | PK | |
| `assessment_session_id` | `INTEGER` | NO | FK → `code_assessment_sessions.id` | Parent session |
| `challenge_id` | `INTEGER` | NO | FK → `code_challenges.id` | Assigned challenge |
| `started_at` | `TIMESTAMPTZ` | NO | | Slot start |
| `expires_at` | `TIMESTAMPTZ` | NO | | min(session expiry, candidate_time) |
| `submitted_at` | `TIMESTAMPTZ` | YES | | Set on successful submit |
| `graded_submission_id` | `INTEGER` | YES | FK → `code_submissions.id` | Final graded row |
| `e2b_sandbox_id` | `VARCHAR(128)` | YES | | Reused across practice runs |
| `run_count` | `INTEGER` | NO | default 0 | Number of practice runs |
| `created_at` | `TIMESTAMPTZ` | NO | | |
| `updated_at` | `TIMESTAMPTZ` | NO | | |

**Indexes:** `ix_code_challenge_attempts_session_id`, `ix_code_challenge_attempts_challenge_id`

**Example row:**

| assessment_session_id | challenge_id | e2b_sandbox_id | run_count | graded_submission_id |
|----------------------|--------------|----------------|-----------|----------------------|
| 7 | 42 | `sb_abc123` | 3 | 501 |

---

### 3.6 `code_runs`

One row per **practice** run (visible tests only; does not grade).

| Column | PostgreSQL type | Nullable | Description |
|--------|-----------------|----------|-------------|
| `id` | `SERIAL` | NO | PK |
| `attempt_id` | `INTEGER` | NO | FK → `code_challenge_attempts.id` |
| `outcome` | `VARCHAR(32)` | NO | e.g. `success`, `failure`, `timeout` |
| `passed_tests` | `INTEGER` | NO | Visible tests passed |
| `total_tests` | `INTEGER` | NO | Visible tests executed |
| `error` | `TEXT` | YES | Sandbox stderr / message |
| `created_at` | `TIMESTAMPTZ` | NO | |
| `updated_at` | `TIMESTAMPTZ` | NO | |

**Index:** `ix_code_runs_attempt_id`

**Example row:**

| attempt_id | outcome | passed_tests | total_tests | error |
|------------|---------|--------------|-------------|-------|
| 12 | success | 2 | 2 | null |

---

### 3.7 `code_submissions`

Final learner code for grading (all tests + LLM evaluation).

| Column | PostgreSQL type | Nullable | Constraints | Description |
|--------|-----------------|----------|-------------|-------------|
| `id` | `SERIAL` | NO | PK | |
| `challenge_id` | `INTEGER` | NO | FK → `code_challenges.id` | |
| `session_id` | `VARCHAR(64)` | NO | | `assess-*` (code session) |
| `submitted_code` | `TEXT` | NO | | Full source at submit time |
| `status` | `VARCHAR(32)` | NO | | `SubmissionStatus` enum |
| `score` | `DOUBLE PRECISION` | YES | 0.0–1.0 | Weighted test score (normalized) |
| `passed` | `BOOLEAN` | YES | | Tests + evaluation pass |
| `grading_metadata` | `TEXT` | YES | | JSON: tests, rubric, LLM evaluation |
| `created_at` | `TIMESTAMPTZ` | NO | | |
| `updated_at` | `TIMESTAMPTZ` | NO | | |

**Indexes:** `ix_code_submissions_challenge_id`, `ix_code_submissions_session_id`

**`grading_metadata` structure:**

```json
{
  "scores": [
    { "dimension": "correctness", "score": 0.95, "feedback": "All tests passed." }
  ],
  "test_results": [
    {
      "test_case_id": "101",
      "passed": true,
      "actual_output": "olleh",
      "expected_output": "olleh",
      "execution_time_ms": 42.0,
      "error": null
    }
  ],
  "total_tests": 3,
  "passed_tests": 3,
  "hidden_tests_count": 1,
  "evaluation": {
    "evaluation_score": 88,
    "evaluation_status": "Passed",
    "breakdown": {
      "correctness": 0.95,
      "completeness": 0.9,
      "code_quality": 0.85,
      "performance": 0.8,
      "creativity": 0.7,
      "documentation": 0.75
    },
    "strengths": ["Clear logic"],
    "weaknesses": ["Could handle edge cases"],
    "recommendations": ["Add type hints"],
    "next_difficulty": "intermediate",
    "feedback_summary": "Solid solution."
  },
  "error": null
}
```

**Example row:**

| id | challenge_id | session_id | score | passed | status |
|----|--------------|------------|-------|--------|--------|
| 501 | 42 | assess-8b57ef381336 | 0.95 | true | completed |

---

### 3.8 `session_audit_events`

Append-only audit trail (no `updated_at`).

| Column | PostgreSQL type | Nullable | Description |
|--------|-----------------|----------|-------------|
| `id` | `SERIAL` | NO | PK |
| `session_id` | `VARCHAR(64)` | NO | `assess-*` |
| `event_type` | `VARCHAR(64)` | NO | e.g. `session_started`, `session_completed` |
| `actor` | `VARCHAR(32)` | NO | e.g. `system`, `learner` |
| `metadata_json` | `TEXT` | YES | Extra context JSON |
| `created_at` | `TIMESTAMPTZ` | NO | Event time (default now) |

**Index:** `ix_session_audit_events_session_id`

**Example rows:**

| session_id | event_type | actor | metadata_json |
|------------|------------|-------|-----------------|
| assess-8b57ef381336 | session_started | system | `{"challenge_count":2}` |
| assess-8b57ef381336 | session_completed | learner | `{"challenges_submitted":2}` |

---

### 3.9 `code_memory_cards`

Silent evaluation snapshot per adaptive submit (Sprint 2).

| Column | PostgreSQL type | Nullable | Description |
|--------|-----------------|----------|-------------|
| `id` | `SERIAL` | NO | PK |
| `platform_session_id` | `TEXT` | YES | Platform UUID when agent path |
| `code_session_id` | `VARCHAR(64)` | NO | `assess-*` |
| `challenge_id` | `INTEGER` | NO | FK → `code_challenges.id` |
| `problem_type` | `VARCHAR(64)` | NO | Category e.g. `arrays` |
| `difficulty` | `VARCHAR(32)` | NO | `beginner` \| `intermediate` \| `advanced` |
| `language` | `VARCHAR(32)` | NO | Challenge language |
| `pass_rate` | `DOUBLE PRECISION` | NO | Objective pass ratio 0–1 |
| `efficiency` | `DOUBLE PRECISION` | NO | Performance ratio from run times |
| `rubric_score` | `DOUBLE PRECISION` | NO | Normalized LLM composite 0–1 |
| `dimension_signals_json` | `TEXT` | NO | Rubric dimension signals |
| `passed` | `BOOLEAN` | NO | Overall pass flag |
| `test_results_json` | `TEXT` | NO | Structured per-test results |
| `created_at` | `TIMESTAMPTZ` | NO | Card creation time |

**Indexes:** `ix_code_memory_cards_code_session_id`, `ix_code_memory_cards_platform_session_id`

**Example row:**

| code_session_id | problem_type | pass_rate | rubric_score | passed |
|-----------------|--------------|-----------|--------------|--------|
| assess-8b57ef381336 | arrays | 0.85 | 0.72 | true |

---

## 4. Relationships

```
platform_code_config (1 row)
        │
        ▼ (read at session start)
code_challenges ◄──── code_test_cases
        │
        ▼
code_assessment_sessions ◄──── code_challenge_attempts ────► code_runs
        │                              │
        │                              └──► code_submissions
        │
        └──► session_audit_events
```

**Cardinality (typical 2-challenge session):**

- 1 `code_assessment_sessions`
- 2 `code_challenges` (new rows per session generation)
- 6–15 `code_test_cases` (3–5 per challenge)
- 2 `code_challenge_attempts`
- 0–many `code_runs` per attempt
- 0–2 `code_submissions` (one per submitted challenge)

---

## 5. Related table (not owned by coding-tool)

**`proctoring_events`** — integrity events keyed by `session_id` (`assess-*` or platform UUID). Required when proctoring is enabled in the UI; schema lives in `backend/app/proctoring/models.py`, migration `0003`.

---

## 6. API ↔ table mapping

| API action | Primary tables written |
|------------|------------------------|
| `POST /api/v1/code/sessions` | `code_challenges`, `code_test_cases`, `code_assessment_sessions`, `code_challenge_attempts`, `session_audit_events` |
| `POST /api/v1/code/adaptive/sessions/{id}/submit` | `code_memory_cards`, `code_submissions`, optional new challenge rows |
| `GET /api/v1/code/adaptive/sessions/{id}/analysis` | Read `analysis_json` / aggregate cards |
| `POST /api/v1/code/submissions` | `code_submissions`, update `code_challenge_attempts` |
| `POST /api/v1/code/sessions/{id}/complete` | update `code_assessment_sessions`, `session_audit_events` |
| `GET/PUT /api/v1/admin/code-config` | `platform_code_config` |

---

## 7. Related documentation

- [backend/app/features/code/README.md](../backend/app/features/code/README.md)
- [database-schema-coding-tool.md](./database-schema-coding-tool.md) — users + platform orchestration
- [feature-contracts.md](./feature-contracts.md) — §5 code contract
