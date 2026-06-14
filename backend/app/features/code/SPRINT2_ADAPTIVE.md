# Sprint 2 — Adaptive Coding Loop (E2B)

Four-layer adaptive loop: typed agent I/O → silent evaluation memory cards → analysis → adaptation.

## agent_integration

### I/O contracts

| Type | Purpose |
|------|---------|
| `CodeToolInput` | Agent turn input: session ids, profile, admin config, target difficulty/category/language, optional challenge + code |
| `CodeToolOutput` | Silent output: pass rate, efficiency, rubric composite, dimension signals, memory card id (no learner scores) |

Entrypoint: `run_adaptive_code_turn()` in `backend/app/features/code/agent_tool.py`.

### HTTP routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/code/adaptive/sessions` | Start adaptive session (first challenge only) |
| GET | `/api/v1/code/adaptive/sessions/{id}` | Session + loop metadata |
| POST | `/api/v1/code/adaptive/sessions/{id}/submit` | Silent submit → evaluate → analyze → adapt |
| GET | `/api/v1/code/adaptive/sessions/{id}/analysis` | Mentor/debug dimension estimates |

### LangGraph loop

Platform graph nodes (`backend/app/agent/graph/nodes.py`):

1. `init_adaptive_session` — creates adaptive code session (one challenge)
2. `wait_for_learner` — WebSocket connect gate
3. `run_adaptive_examination` — push/wait/submit loop via `examine_adaptive_code_session`
4. `persist_grades` / `complete_session`

State fields: `memory_card_ids`, `current_difficulty`, `challenges_completed`, `analysis_snapshot`.

## evaluation_memory_cards

Table `code_memory_cards` (migration `0007_code_memory_cards`):

| Column | Meaning |
|--------|---------|
| `pass_rate` | Weighted objective test pass ratio (0–1) |
| `efficiency` | Performance ratio from execution times |
| `rubric_score` | Normalized LLM composite (0–1) |
| `dimension_signals_json` | Per-dimension rubric signals |
| `problem_type` | Challenge category (e.g. `arrays`) |
| `test_results_json` | Full per-test results (storage only) |

Service: `backend/app/features/code/evaluation_memory.py` — E2B via shared `grading.py`, LLM rubric via `evaluate_code_submission`, persist card, return `CodeToolOutput`.

**Silent policy:** learner submit endpoint returns `AdaptiveSubmitResponse` without scores; grades remain in `code_submissions.grading_metadata` for audit.

## analysis

Service: `backend/app/features/code/analysis.py`

- Input: all memory cards for `code_session_id`
- Output: `LearnerCodeAnalysis` (dimension estimates, strong/weak problem types, averages, turns)
- Recent cards weighted with decay `0.85`
- Strong type if avg pass ≥ 0.8; weak if < 0.5
- Snapshot persisted on `code_assessment_sessions.analysis_json`

Example after 2 turns: weak `strings`, strong `arrays`, `turns_completed: 2`.

## adaptation

Service: `backend/app/features/code/adaptation.py`

Rules (v1):

- Last pass ≥ 0.85 and rubric ≥ 0.7 → bump difficulty
- Pass < 0.5 or rubric < 0.4 → lower difficulty
- Prefer weak problem types; occasionally rotate strong types
- Language from `language_profile.assign_challenge_languages`
- Clamped to admin `difficulty_levels` and `allowed_languages`

Single challenge generation: `generate_single_adaptive_challenge()` in `backend/app/challenges/generator.py`.

## tests

```bash
cd backend
pytest tests/features/test_adaptive_evaluation.py \
       tests/features/test_adaptive_analysis.py \
       tests/features/test_adaptive_adaptation.py \
       tests/features/test_adaptive_loop.py \
       tests/agent/test_adaptive_graph.py -q
```

Integration tests require `TEST_DATABASE_URL`.

Coverage map:

| File | Focus |
|------|-------|
| `test_adaptive_evaluation.py` | Memory card persistence, `CodeToolOutput` |
| `test_adaptive_analysis.py` | Strong/weak type aggregation |
| `test_adaptive_adaptation.py` | Difficulty up/down rules |
| `test_adaptive_loop.py` | Start → submit → analysis HTTP path |
| `test_adaptive_graph.py` | Graph compile + adaptive state |
