# Contributing

## Branch strategy

| Branch | Purpose |
|---|---|
| `main` | Demo-ready. PRs only. |
| `voice-agent` | Voice interview |
| `mcq-tool` | MCQ protocol tool |
| `viz-tool` | Diagram / image reasoning tool |
| `avatar-tool` | Camera-on interview tool |
| `coding-tool` | E2B code execution tool |

## Rules
- Never modify `app/core/` — kernel is READ-ONLY.
- New env vars must be added to `.env.example`.
