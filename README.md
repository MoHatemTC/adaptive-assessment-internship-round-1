# Masaar — AI Adaptive Assessment Platform

> Sprints Internship · Round 1

An agentic assessment platform where the entire assessment runs as a single adaptive chat. An examiner agent — built on LangGraph — drives the session, invokes five specialised tools, adapts difficulty in real time, grades silently against rubrics, and delivers a verified five-dimension report with a radar chart.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + WebSockets |
| Agent / Orchestration | LangGraph (LangChain) |
| LLM Abstraction | LiteLLM |
| Database | PostgreSQL (async via SQLAlchemy) |
| Background Workers | Celery + Redis |
| Vector Store | Qdrant |
| Speech-to-Text | Deepgram |
| Code Sandbox | E2B |
| Observability | Langfuse |
| Frontend | Next.js 15 (App Router) + Tailwind CSS |
| State Management | Zustand |
| Infrastructure | Docker + Docker Compose + Nginx |

---

## Getting Started

### Prerequisites

Install these once:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — this is all you need to run everything

That's it. PostgreSQL, Redis, and Qdrant all spin up automatically via Docker Compose.

### Run the full stack

```bash
# Clone the repo
git clone https://github.com/YOUR_ORG/masaar-assessment-platform.git
cd masaar-assessment-platform

# Set up environment variables
cp .env.example .env
# Open .env and fill in your API keys (LITELLM_API_KEY, DEEPGRAM_API_KEY, etc.)

# Start everything (with hot reload for development)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Common commands

```bash
# Start all services
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Start in background
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Stop everything
docker compose down

# Run backend tests
docker compose exec backend pytest tests/ -v

# Run a specific test file
docker compose exec backend pytest tests/features/test_voice.py -v

# Run database migrations
docker compose exec backend alembic upgrade head

# View backend logs
docker compose logs backend -f

# Rebuild after dependency changes
docker compose build
```

---

## Project Structure

```
masaar-assessment-platform/
├── .github/                    # CI workflows + PR template
├── nginx/                      # Reverse proxy config
├── backend/
│   ├── app/
│   │   ├── core/               # Kernel — READ ONLY
│   │   ├── features/
│   │   │   ├── voice/          # Voice interview tool
│   │   │   ├── mcq/            # MCQ protocol tool
│   │   │   ├── diagram/        # Diagram / image tool
│   │   │   ├── camera/         # Camera interview tool
│   │   │   └── code/           # E2B code execution tool
│   │   ├── agent/              # LangGraph examiner agent
│   │   ├── admin/              # Assessment configuration API
│   │   ├── sessions/           # Session lifecycle API
│   │   ├── proctoring/         # Integrity monitoring
│   │   ├── reports/            # Scoring + report generation
│   │   └── workers/            # Celery background tasks
│   ├── migrations/             # Alembic migrations
│   └── tests/                  # pytest test suite
├── frontend/
│   └── src/
│       ├── app/                # Next.js App Router pages
│       ├── components/         # Shared UI + tool widgets
│       ├── features/voice/     # VoiceRecorder component
│       ├── hooks/              # Custom React hooks
│       ├── store/              # Zustand state stores
│       ├── lib/                # API + WebSocket clients
│       └── types/              # TypeScript definitions
├── docs/                       # Architecture + API docs
├── design/                     # Sprints design system
├── docker-compose.yml          # Production compose
└── docker-compose.dev.yml      # Dev overrides (hot reload)
```

> **`app/core/` is the kernel.** It is READ-ONLY for all team members. Build on top of it, never modify it.

---

## Feature Ownership

| Feature | Branch | Owner |
|---|---|---|
| Voice interview tool | `voice-agent` | Karim |
| MCQ protocol tool | `mcq-tool` | Malak |
| Diagram / image tool | `viz-tool` | Abutaleb |
| Camera interview tool | `avatar-tool` | Sherif |
| E2B code execution tool | `coding-tool` | Nagah |

---

## Branch Strategy

```
main          ← demo-ready, receives PRs from all feature branches
  ├── voice-agent
  ├── mcq-tool
  ├── viz-tool
  ├── avatar-tool
  └── coding-tool
```

Each team member works on their assigned branch and opens a Pull Request directly into main when their slice is complete.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values. Never commit a real `.env` file.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (pre-filled for Docker) |
| `REDIS_URL` | Redis connection string (pre-filled for Docker) |
| `LITELLM_API_KEY` | API key for LLM calls |
| `DEEPGRAM_API_KEY` | Speech-to-text (voice tool) |
| `QDRANT_URL` | Vector store URL (pre-filled for Docker) |
| `LANGFUSE_PUBLIC_KEY` | Observability tracing |
| `E2B_API_KEY` | Code sandbox (E2B tool) |

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full workflow, branch rules, and PR checklist.

---

## Documentation

| Document | Description |
|----------|-------------|
| [.cursor/MASAAR_CURSOR_FULL_PROJECT.md](./.cursor/MASAAR_CURSOR_FULL_PROJECT.md) | Master product spec and LangGraph design |
| [docs/architecture.md](./docs/architecture.md) | One-page architecture overview |
| [docs/system-architecture.md](./docs/system-architecture.md) | Detailed runtime diagrams (target + as-built) |
| [docs/database-schema.md](./docs/database-schema.md) | Target PostgreSQL DDL and migration appendix |
| [docs/database-schema-readme.md](./docs/database-schema-readme.md) | Full suggested schema (coding-tool + system + auth) for leads |
| [docs/database-schema-coding-tool.md](./docs/database-schema-coding-tool.md) | Coding-tool + users + orchestration only |
| [docs/coding-tool-tables-reference.md](./docs/coding-tool-tables-reference.md) | Coding-tool tables: columns, types, and sample data |
| [docs/feature-contracts.md](./docs/feature-contracts.md) | Interface requirements per feature slice |
| [docs/cursor-rules.md](./docs/cursor-rules.md) | Cursor / AI implementation rules |
| [docs/api-reference.md](./docs/api-reference.md) | Route index + link to OpenAPI |
| [docs/deployment.md](./docs/deployment.md) | Docker, nginx, WebSocket proxy |
