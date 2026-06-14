# API Reference

Interactive OpenAPI docs: **http://localhost:8000/docs** (when the stack is running).

This page indexes route groups. For request/response shapes, use OpenAPI or the shared schemas in [shared/schemas/](../shared/schemas/).

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB, LLM, E2B status |
| GET | `/api/v1/health` | Same as above |

---

## Integrations

Cross-feature discovery and examiner orchestration. See [feature-contracts.md](./feature-contracts.md).

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/api/v1/integrations/capabilities` | **Implemented** | Feature manifest for chat UI / agent |
| GET | `/api/v1/integrations/sessions/{id}/timed-summary` | **Implemented** | Multi-challenge session progress |
| GET | `/api/v1/integrations/sessions/{id}/integrity-flags` | **Implemented** | Shared `IntegrityFlag` list |
| POST | `/api/v1/integrations/sessions/{id}/push-next` | **Implemented** | Push next code challenge (WebSocket) |
| POST | `/api/v1/integrations/sessions/{id}/examine` | **Implemented** | Run all remaining code challenges |
| WS | `/api/v1/integrations/sessions/{id}/ws` | **Implemented** | Examiner question/answer channel |

WebSocket base: `ws://localhost:8000` (not port 3000).

---

## Code execution (`/api/v1/code`)

Feature README: [backend/app/features/code/README.md](../backend/app/features/code/README.md)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/code/sessions` | Start timed assessment (profile → generate challenges) |
| GET | `/api/v1/code/sessions/{id}` | Session status, timers, challenge slots |
| POST | `/api/v1/code/sessions/{id}/complete` | Formal finish + audit |
| GET | `/api/v1/code/sessions/{id}/submissions` | All graded submissions in session |
| POST | `/api/v1/code/runs` | Practice run (visible tests) |
| POST | `/api/v1/code/submissions` | Final graded submit |
| POST | `/api/v1/code/challenges/generate` | Generate without starting session |
| GET/POST | `/api/v1/code/challenges` | List / create challenges |
| GET | `/api/v1/code/challenges/{id}` | Challenge detail (learner view) |
| GET | `/api/v1/code/submissions/{id}` | Graded submission + evaluation |

---

## Proctoring (`/api/v1/proctoring`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/proctoring/events` | Record integrity event |
| GET | `/api/v1/proctoring/sessions/{id}/report` | Integrity report |
| GET | `/api/v1/proctoring/config` | Thresholds and messages |
| GET | `/api/v1/proctoring/sessions/{id}/violations` | Violation summary |
| GET | `/api/v1/proctoring/admin/sessions` | Admin integrity review list |

---

## Admin (`/api/v1/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/code-config` | Platform challenge generation config |
| PUT | `/api/v1/admin/code-config` | Update config (`X-Admin-Key`) |

---

## Planned route groups

| Prefix | Owner | Status |
|--------|-------|--------|
| `/api/v1/sessions` | Platform | Unified chat session lifecycle |
| `/api/v1/grading` | Platform | Async grade status |
| `/api/v1/reports` | Platform | Final assessment report |

Spec: [.cursor/MASAAR_CURSOR_FULL_PROJECT.md](../.cursor/MASAAR_CURSOR_FULL_PROJECT.md) §10.

---

## Related documentation

- [system-architecture.md](./system-architecture.md) — when each API is called in the flow
- [database-schema.md](./database-schema.md) — tables behind each route group
