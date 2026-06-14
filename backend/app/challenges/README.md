# LLM Challenge Generator

Generates personalized programming challenges from learner profiles with admin-controlled time budgets.

## Flow

```
UserProfile + PlatformChallengeConfig
        ↓
generate_code_challenges()
        ↓
time_budget.normalize_challenge_times()
        ↓
ChallengeGenerationResult → code.service (persist)
```

## Rules

- Only the LLM generates challenges — users never author them.
- Config from `GET /api/v1/admin/code-config` (defaults in `defaults.py`).
- LLM assigns `candidate_time_seconds` by difficulty; sum must fit `total_time_minutes`.
- `time_limit_seconds` is the E2B execution cap only.

## API

- `POST /api/v1/code/challenges/generate` — generate without a timed session
- `POST /api/v1/code/sessions` — generate as part of a timed assessment
