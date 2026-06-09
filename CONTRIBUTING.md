# Contributing

## Branch strategy

| Branch | Purpose |
|---|---|
| `main` | Demo-ready. PRs only. |
| `develop` | Integration. All feature PRs target this. |
| `feature/voice-tool` | Voice interview |
| `feature/mcq-tool` | MCQ protocol tool |
| `feature/diagram-tool` | Diagram / image reasoning tool |
| `feature/camera-tool` | Camera-on interview tool |
| `feature/e2b-tool` | E2B code execution tool |

## Rules
- Never modify `app/core/` — kernel is READ-ONLY.
- Every feature needs tests in `tests/features/test_<feature>.py`.
- New env vars must be added to `.env.example`.
- PRs target `develop`, not `main`.
