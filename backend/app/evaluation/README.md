# LLM Evaluator

Shared evaluation layer for the challenge generation and evaluation platform.

## Role

The **LLM Evaluator** scores user submissions using:

1. **Admin configuration** (`PlatformEvaluationConfig`) — weights, passing threshold, AI strictness
2. **Deterministic signals** — e.g. E2B test results for correctness/performance
3. **LiteLLM** (via `app.core.llm`) — subjective dimensions and actionable feedback

## Output shape

Matches the platform evaluation contract:

```json
{
  "challenge_id": 1,
  "score": 87,
  "status": "Passed",
  "breakdown": {
    "correctness": 35,
    "completeness": 14,
    "code_quality": 17,
    "performance": 14,
    "creativity": 4,
    "documentation": 3
  },
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommendations": ["..."],
  "next_difficulty": "Intermediate"
}
```

## Admin config

Defaults live in `defaults.py`. When `app/admin/` is implemented, load
`PlatformEvaluationConfig` from the database instead of defaults.

## Usage

```python
from app.evaluation import evaluate_code_submission
from app.evaluation.schemas import CodeEvaluationContext

result = await evaluate_code_submission(CodeEvaluationContext(...))
```
