# Masaar — Unified Database Schema

> **Status:** Sprint 2 reference · Four tools active (voice, mcq, diagram, coding)  
> **Storage:** PostgreSQL via Supabase (production) · Docker PostgreSQL (development)  
> **Last updated:** Sprint 2 Week 2

---

## Non-Negotiable Rules

These rules apply to every table in every feature. No exceptions.

1. **No scores on tool response tables.** Grading is a decoupled layer. `grade_results` owns all scores. A learner-facing layer must never be able to query a score from the same table it reads question content from.
2. **`session_id` is always a `String(36)` UUID** on every tool table. It has no FK constraint today (deferred until `assessment_sessions` is built). Every tool table must include the comment `# FK deferred until assessment_sessions table exists`.
3. **No `TimestampMixin`.** It is SQLModel-based and incompatible with `Base`. Declare `created_at` manually on every table: `mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)`.
4. **`question_index` is required on every response table.** Without it the adaptive loop cannot reconstruct session order or know which question in the blueprint produced a given response.
5. **Platform tables are not owned by any tool.** `assessments`, `assessment_sessions`, `grade_results`, `memory_cards`, `skill_dimension_scores`, and `proctoring_events` live in `app/sessions/` and `app/admin/`. No tool imports or modifies them.
6. **Skill dimension scores are whole integers 1–10 only, or NULL for N/A.** Use `SMALLINT`. Never store decimals.
7. **Silent grading.** The learner never sees grading output during a session. All grading writes go to `grade_results` and `memory_cards` — never back to the tool response table.

---

## Schema Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1 — Platform Tables  (app/sessions/, app/admin/,          │
│                              app/proctoring/)                    │
│                                                                  │
│  assessments ──────────────────────────────────────────────┐    │
│  assessment_sessions  ◄── all tool tables FK here (uuid)   │    │
│  grade_results        ◄── one row per graded response       │    │
│  memory_cards         ◄── one evidence card per response    │    │
│  skill_dimension_scores ◄─ 5-dimension scores per question  │    │
│  proctoring_events    ◄── integrity events                  │    │
└─────────────────────────────────────────────────────────────────┘
         ▲               ▲               ▲               ▲
┌────────┴────┐  ┌───────┴─────┐  ┌─────┴──────┐  ┌────┴───────┐
│   VOICE     │  │    MCQ      │  │  DIAGRAM   │  │   CODING   │
│ app/features│  │ app/features│  │ app/features│  │ app/features│
│ /voice/     │  │ /mcq/       │  │ /diagram/  │  │ /code/     │
│             │  │             │  │            │  │            │
│ voice_      │  │ mcq_        │  │ diagram_   │  │ code_      │
│ sessions    │  │ questions   │  │ questions  │  │ challenges │
│             │  │ mcq_options │  │            │  │ + 7 more   │
│ voice_      │  │ mcq_        │  │ diagram_   │  │ tables     │
│ transcripts │  │ responses   │  │ answers    │  │            │
└─────────────┘  └─────────────┘  └────────────┘  └────────────┘
```

---

## Tier 1 — Platform Tables

### `assessments`

Owned by: `backend/app/admin/models.py`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | UUID | NO | PK, `gen_random_uuid()` | |
| `title` | TEXT | NO | | Short assessment name |
| `prompt` | TEXT | NO | | Admin's configuration prompt |
| `blueprint_json` | JSONB | NO | | Question plan: types, count, difficulty progression, time limits |
| `tool_config` | JSONB | NO | | Which tools are enabled: `{"voice": true, "mcq": true, "diagram": true, "coding": true}` |
| `status` | VARCHAR(20) | NO | DEFAULT `'draft'` | `draft` / `active` / `archived` |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |
| `updated_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

---

### `assessment_sessions`

Owned by: `backend/app/sessions/models.py`

**This is the parent every tool table references via `session_id`.** Its `id` is the UUID that flows through the entire system.

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | UUID | NO | PK, `gen_random_uuid()` | The platform session UUID |
| `assessment_id` | UUID | NO | FK → `assessments.id` | |
| `learner_profile_json` | JSONB | NO | | `{name, role, level, target_skills, consent_given}` |
| `status` | VARCHAR(20) | NO | DEFAULT `'pending'` | `pending` / `active` / `completed` / `expired` / `flagged` |
| `code_session_id` | VARCHAR(64) | YES | | Bridge to coding tool's `assess-*` session ID |
| `started_at` | TIMESTAMPTZ | YES | | Set when learner begins |
| `completed_at` | TIMESTAMPTZ | YES | | Set on completion or expiry |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |
| `updated_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

---

### `grade_results`

Owned by: `backend/app/sessions/models.py`

One row per graded question response. Written by the grading layer (Layer 5) after each answer. The tool that produced the response is identified by `tool_type` and `tool_session_id`. The LLM judge score is NULL until the judge runs at the end of the sprint.

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `tool_type` | VARCHAR(20) | NO | | `'voice'` / `'mcq'` / `'diagram'` / `'coding'` |
| `tool_session_id` | INTEGER | NO | | FK to the tool's own session row (e.g. `voice_sessions.id`) |
| `question_index` | INTEGER | NO | | Position in blueprint, 0-indexed |
| `rubric_scores` | JSONB | NO | | LLM rubric breakdown (see JSON reference below) |
| `llm_judge_score` | FLOAT | YES | | NULL until end-of-sprint LLM judge runs |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

**Index:** `ix_grade_results_session_id`

---

### `memory_cards`

Owned by: `backend/app/sessions/models.py`

One evidence card per response. Written by the Memory Card Extractor (Layer 6) immediately after grading. This is the input to the Skill Taxonomy Analysis layer (Layer 7). Tool-specific detail tables (e.g. `code_memory_cards`) write a summary row here.

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `tool_type` | VARCHAR(20) | NO | | `'voice'` / `'mcq'` / `'diagram'` / `'coding'` |
| `question_index` | INTEGER | NO | | Position in blueprint, 0-indexed |
| `difficulty` | VARCHAR(20) | NO | | `'beginner'` / `'intermediate'` / `'advanced'` |
| `evidence_summary` | TEXT | NO | | Human-readable insight extracted from this response |
| `dimension_signals` | JSONB | NO | | Per-dimension engagement signals (see JSON reference) |
| `passed` | BOOLEAN | NO | | Overall pass flag for this response |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

**Index:** `ix_memory_cards_session_id`

---

### `skill_dimension_scores`

Owned by: `backend/app/sessions/models.py`

Written by the Skill Taxonomy Analysis layer (Layer 7) after each memory card is processed. One row per question per session. All scores are whole integers 1–10. NULL means this dimension is not applicable to the tool that generated the question.

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `question_index` | INTEGER | NO | | Position in blueprint, 0-indexed |
| `tool_type` | VARCHAR(20) | NO | | Which tool produced this question |
| `thinking` | SMALLINT | YES | CHECK 1–10 | How the learner reasons through choices. NULL = N/A |
| `soft` | SMALLINT | YES | CHECK 1–10 | How they work with people. NULL = N/A |
| `work` | SMALLINT | YES | CHECK 1–10 | How they execute and deliver. NULL = N/A |
| `digital_ai` | SMALLINT | YES | CHECK 1–10 | How they use their tools. NULL = N/A |
| `growth` | SMALLINT | YES | CHECK 1–10 | How they take feedback and improve. NULL = N/A |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

**Constraint:** `CHECK (thinking BETWEEN 1 AND 10)` applied to each non-null dimension column.  
**Index:** `ix_skill_dimension_scores_session_id`

---

### `proctoring_events`

Owned by: `backend/app/proctoring/models.py`

Integrity events recorded in parallel during any tool session. Session key is the platform UUID.

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `event_type` | VARCHAR(32) | NO | | `tab_switch` / `copy_paste` / `screenshot` / `ai_usage` / `identity_fail` |
| `severity` | VARCHAR(16) | NO | | `low` / `medium` / `high` |
| `metadata` | JSONB | YES | | Extra context (browser info, timestamps, etc.) |
| `client_timestamp` | TIMESTAMPTZ | YES | | Browser-reported time |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

**Indexes:** `ix_proctoring_events_session_id`, `ix_proctoring_events_event_type`

---

## Tier 2 — Tool Tables

### Voice Tool

Owned by: `backend/app/features/voice/models.py`  
Status: ✅ Sprint 1 complete. No changes required.

#### `voice_sessions`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `question_text` | TEXT | NO | | The interview question for this round |
| `question_index` | INTEGER | NO | | Position in blueprint, 0-indexed |
| `status` | VARCHAR(20) | NO | DEFAULT `'pending'` | `pending` / `active` / `completed` / `timed_out` / `failed` |
| `time_limit_seconds` | INTEGER | NO | | Configured max seconds for this round |
| `started_at` | TIMESTAMPTZ | YES | | Set when recording begins |
| `ended_at` | TIMESTAMPTZ | YES | | Set on completion or timeout |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

> `elapsed_seconds` is never stored. Derived in `_check_time_node` as `(ended_at − started_at).total_seconds()`.

#### `voice_transcripts`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `voice_session_id` | INTEGER | NO | FK → `voice_sessions.id` CASCADE DELETE | |
| `chunk_index` | INTEGER | NO | | Order within session, 0-indexed |
| `transcript_text` | TEXT | NO | | Transcribed text of this audio chunk |
| `confidence` | FLOAT | NO | | STT confidence 0.0–1.0. Only stored if ≥ 0.6 |
| `provider` | VARCHAR(50) | NO | | `'azure_whisper'` |
| `audio_duration_ms` | INTEGER | YES | | Duration of this chunk in milliseconds |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

---

### MCQ Tool

Owned by: `backend/app/features/mcq/models.py`  
Status: ⚠️ Requires changes before Sprint 2 development continues (see notes).

#### `mcq_questions`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `question_text` | TEXT | NO | | |
| `difficulty` | VARCHAR(20) | NO | | `beginner` / `intermediate` / `advanced` |
| `correct_option` | VARCHAR(10) | NO | | Label of correct answer. **Never exposed to learner.** |
| `dimension` | VARCHAR(20) | YES | | Primary skill dimension this question targets |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

#### `mcq_options`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `question_id` | INTEGER | NO | FK → `mcq_questions.id` CASCADE DELETE | |
| `label` | VARCHAR(10) | NO | | `A` / `B` / `C` / `D` |
| `text` | TEXT | NO | | Option content |

#### `mcq_responses`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `question_id` | INTEGER | NO | FK → `mcq_questions.id` | |
| `question_index` | INTEGER | NO | | ⚠️ **ADD THIS** — position in blueprint, 0-indexed |
| `selected_option` | VARCHAR(10) | NO | | Learner's selected label |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

> ⚠️ **Remove from current model:** `is_correct`, `score`, `learner_id`.  
> Correctness is determined by comparing `selected_option` against `mcq_questions.correct_option` inside the grading layer. The result is written to `grade_results`, never back to this table.

---

### Diagram Tool

Owned by: `backend/app/features/diagram/models.py`  
Status: ⚠️ Requires changes before Sprint 2 development continues (see notes).

#### `diagram_questions`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `image_url` | TEXT | NO | | URL of the diagram/image |
| `prompt` | TEXT | NO | | Question posed about the image |
| `rubric` | JSONB | NO | | ⚠️ **Change from TEXT to JSONB** — structured grading criteria |
| `difficulty` | VARCHAR(20) | NO | | `beginner` / `intermediate` / `advanced` |
| `dimension` | VARCHAR(20) | YES | | Primary skill dimension targeted |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | |

#### `diagram_answers`

| Column | Type | Nullable | Constraint | Notes |
|--------|------|----------|------------|-------|
| `id` | INTEGER | NO | PK, auto-increment | |
| `session_id` | VARCHAR(36) | NO | NOT NULL, INDEX | Deferred FK → `assessment_sessions.id` |
| `question_id` | INTEGER | NO | FK → `diagram_questions.id` | |
| `question_index` | INTEGER | NO | | ⚠️ **ADD THIS** — position in blueprint, 0-indexed |
| `answer_text` | TEXT | NO | | Learner's written response |
| `submitted_at` | TIMESTAMPTZ | NO | | When the learner submitted |
| `created_at` | TIMESTAMPTZ | NO | `DEFAULT now()` | ⚠️ **ADD THIS** |

> ⚠️ **Remove from current model:** `score`, `grading_feedback`, `graded_at`.  
> All grading output goes to `grade_results`. This table is learner-facing and must contain zero grading information.

---

### Coding Tool

Owned by: `backend/app/features/code/models.py` (tool tables) and platform features (orchestration tables).  
Status: ⚠️ Platform tables need to be extracted from the coding feature into `app/sessions/` and `app/admin/`. All `code_*` tables remain unchanged.

#### Platform tables to extract

The following tables were designed by the coding tool and are correct in structure. They must move out of `app/features/code/` into the platform layer so all tools can share them:

| Table | Move to |
|-------|---------|
| `assessments` | `app/admin/models.py` |
| `assessment_sessions` | `app/sessions/models.py` |
| `grade_results` | `app/sessions/models.py` |
| `proctoring_events` | `app/proctoring/models.py` |

Their schemas are defined in **Tier 1** above and match what the coding tool designed, with minor alignment adjustments.

#### Coding tool tables (unchanged, stay in `app/features/code/`)

| Table | Purpose |
|-------|---------|
| `platform_code_config` | Single-row admin config for challenge generation |
| `code_challenges` | LLM-generated or bootstrap coding problems |
| `code_test_cases` | Visible and hidden test cases per challenge |
| `code_assessment_sessions` | Timed coding session (`assess-*` ID format, internal to coding tool) |
| `code_challenge_attempts` | One slot per challenge (timers, sandbox ID, run count) |
| `code_runs` | Practice runs against visible tests only |
| `code_submissions` | Final graded submission per challenge |
| `session_audit_events` | Append-only lifecycle audit log |
| `code_memory_cards` | Sprint 2: detail-level evidence card per submission (feeds `memory_cards`) |

> The coding tool uses two session identifiers. `assessment_sessions.id` (UUID) is the platform session. `code_assessment_sessions.session_id` (`assess-{12hex}`) is the coding-tool-internal session. They are bridged via `assessment_sessions.code_session_id`. When the coding tool writes a row to the shared `memory_cards` table, it uses the platform UUID, not the `assess-*` ID.

Full column definitions for all `code_*` tables are in `design/coding-tool-tables-reference.md`.

---

## Migration Chain

Migrations must run in this exact order. Platform tables must exist before tool tables add FK constraints.

| Revision | File | Tables |
|----------|------|--------|
| `0001` | `0001_mcq.py` | `mcq_questions`, `mcq_options`, `mcq_responses` — **chain root** |
| `0002` | `0002_voice.py` | `voice_sessions`, `voice_transcripts` |
| `0003` | `0003_platform.py` | `assessments`, `assessment_sessions` |
| `0004` | `0004_grading.py` | `grade_results`, `memory_cards`, `skill_dimension_scores` |
| `0005` | `0005_proctoring.py` | `proctoring_events` |
| `0006` | `0006_diagram.py` | `diagram_questions`, `diagram_answers` |
| `0007` | `0007_coding.py` | `platform_code_config`, all `code_*` tables |

> ⚠️ `alembic.ini` is currently a 0-byte stub. No migrations can run until it is configured. This is a Sprint 2 blocker.

---

## Adaptive Loop — Data Flow per Response

This maps each layer of the 4-layer adaptive loop (from the Sprint 2 Week 2 meeting) to the tables it reads from and writes to.

```
Learner submits response
        │
        ▼
┌─────────────────────────────────────────────┐
│  Layer 1 — Grading                          │
│  Reads:  [tool]_responses / transcripts     │
│  Reads:  [tool]_questions (rubric/answer)   │
│  Writes: grade_results                      │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Layer 2 — Memory Card Extraction           │
│  Reads:  grade_results (latest row)         │
│  Reads:  [tool]_questions (context)         │
│  Writes: memory_cards                       │
│  Writes: code_memory_cards (coding only)    │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Layer 3 — Skill Taxonomy Analysis          │
│  Reads:  memory_cards (all cards so far     │
│           for this session_id)              │
│  Writes: skill_dimension_scores             │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Layer 4 — Adaptive Contract                │
│  Reads:  skill_dimension_scores             │
│  Reads:  assessment_sessions (blueprint)    │
│  Output: next-question contract             │
│          {tool, difficulty, focus, stop?}   │
│  (no DB write — passed directly to          │
│   Generator Agent as context)               │
└─────────────────────────────────────────────┘
        │
        ├── continue → Generator Agent → next question
        └── stop    → Candidate Report
```

---

## JSON Column Reference

| Table | Column | Structure |
|-------|--------|-----------|
| `assessments` | `blueprint_json` | `{question_plans: [{tool, count, difficulty_range, time_limit}]}` |
| `assessments` | `tool_config` | `{voice: bool, mcq: bool, diagram: bool, coding: bool}` |
| `assessment_sessions` | `learner_profile_json` | `{name, role, level, target_skills, consent_given}` |
| `grade_results` | `rubric_scores` | `{dimensions: [{name, score, feedback}], overall: float}` |
| `memory_cards` | `dimension_signals` | `{thinking: bool, soft: bool, work: bool, digital_ai: bool, growth: bool}` |
| `diagram_questions` | `rubric` | `{criteria: [{label, weight, description}]}` |
| `code_assessment_sessions` | `profile_json` | `{name, skills, experience_level, preferred_domains}` |
| `code_submissions` | `grading_metadata` | Full E2B + LLM rubric breakdown (see coding-tool-tables-reference.md) |

---

## SQLAlchemy Model Conventions

All models must follow these patterns without exception:

```python
from app.core.database import Base, Mapped, mapped_column
from sqlalchemy import DateTime, String, Integer, func

class MyModel(Base):
    __tablename__ = "my_table"

    id: Mapped[int] = mapped_column(primary_key=True)

    # session_id pattern — always String, always deferred FK
    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )  # FK deferred until assessment_sessions table exists

    # Timestamps — always declared manually, never via TimestampMixin
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

**Logger rules (from kernel contract):**
```python
logger = get_logger(__name__)
logger.info("event_name", key=value)   # keyword args only, no f-strings
# No print(), no stdlib logging
```

---

## File Ownership

| Path | Owner | Contents |
|------|-------|----------|
| `backend/app/admin/models.py` | Sessions team | `assessments` |
| `backend/app/sessions/models.py` | Sessions team | `assessment_sessions`, `grade_results`, `memory_cards`, `skill_dimension_scores` |
| `backend/app/proctoring/models.py` | Sessions team | `proctoring_events` |
| `backend/app/features/voice/models.py` | Karim | `voice_sessions`, `voice_transcripts` |
| `backend/app/features/mcq/models.py` | Malak | `mcq_questions`, `mcq_options`, `mcq_responses` |
| `backend/app/features/diagram/models.py` | Abutaleb | `diagram_questions`, `diagram_answers` |
| `backend/app/features/code/models.py` | Nagah | All `code_*` tables, `platform_code_config`, `session_audit_events` |

---

*For coding tool column-level detail see `design/coding-tool-tables-reference.md`. For the full architecture see `design/design.md`.*
