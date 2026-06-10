# Diagram / Visualization Feature — Sprint 1

**Owner:** Mohamed Abutaleb  
**Branch:** `viz-tool`  
**Tool name (agent):** `diagram_generate_visualization`

---

## Overview

The Diagram feature is one of five assessment tools the **Masaar AI Adaptive Assessment Platform** exposes to its LangGraph examiner agent. When the agent decides a learner's answer or topic would benefit from a visual explanation, it calls this tool with a plain-English description. The tool responds with a fully rendered SVG diagram URL that the frontend displays instantly — no image-generation APIs, no external rendering servers required at runtime.

### How it works end-to-end

```
Examiner Agent
     │
     │  calls tool: "diagram_generate_visualization"
     ▼
DiagramService.create_diagram(prompt)
     │
     ├─ 1. Insert a "pending" Diagram row in PostgreSQL
     │
     ├─ 2. Ask LiteLLM (e.g. gpt-4o) to write Mermaid.js code
     │       for the requested system / flow / schema
     │
     ├─ 3. Serialize Mermaid code → JSON state → Base64
     │
     ├─ 4. Construct  https://mermaid.ink/svg/<base64>
     │       (open-source, no auth, renders any valid Mermaid)
     │
     ├─ 5. Update row: status="completed", image_url=<url>
     │
     └─ 6. Return DiagramResponse to agent / HTTP caller

Frontend
     └─ <img src={diagram.image_url} />   ← renders the SVG
```

### Why Mermaid + mermaid.ink?

- **Structured output** — LLMs produce correct Mermaid syntax far more reliably than pixel-level images.
- **No cost** — `mermaid.ink` is a free, open-source rendering service. No API keys needed.
- **SVG quality** — Output is infinitely scalable, copy-pasteable, and accessible.
- **Graceful fallback** — If the LLM call fails, the service falls back to a template diagram so the endpoint never crashes.

---

## Files

```
backend/app/features/diagram/
├── README.md        ← you are here
├── __init__.py      ← exports router, model, service, and LangChain tools
├── models.py        ← SQLModel ORM table: diagrams
├── schemas.py       ← Pydantic request / response schemas
├── service.py       ← DiagramService: LLM generation + DB persistence
├── api.py           ← FastAPI router: POST /diagram, GET /diagram/{id}, …
└── tool.py          ← LangChain StructuredTool for the examiner agent
```

---

## Database Model — `models.py`

Table name: **`diagrams`**

| Column | Type | Description |
|---|---|---|
| `id` | `UUID` (PK) | Auto-generated unique identifier |
| `user_id` | `UUID` (nullable) | Learner session ID (optional) |
| `prompt` | `Text` | Original plain-English description |
| `image_url` | `Text` (nullable) | Rendered `mermaid.ink` SVG URL |
| `status` | `String` | `pending` → `completed` or `failed` |
| `created_at` | `DateTime` | Inherited from `TimestampMixin` |
| `updated_at` | `DateTime` | Inherited from `TimestampMixin` |

Uses **SQLModel 2.0 / SQLAlchemy 2.0 async** style — same as every other feature in the project. Inherits `TimestampMixin` from `app.core.database` for automatic audit columns.

```python
# models.py pattern
class Diagram(SQLModel, TimestampMixin, table=True):
    __tablename__ = "diagrams"
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    ...
```

---

## Schemas — `schemas.py`

### `DiagramCreateRequest`
```json
{
  "prompt": "Three-tier web application with React, FastAPI, and PostgreSQL",
  "user_id": "550e8400-e29b-41d4-a716-446655440000"   // optional
}
```

### `DiagramResponse`
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "prompt": "Three-tier web application with React, FastAPI, and PostgreSQL",
  "image_url": "https://mermaid.ink/svg/eyJjb2RlIjoiZ3JhcGggVEQuLi4ifQ==",
  "status": "completed",
  "created_at": "2026-06-11T09:00:00Z"
}
```

---

## Service — `service.py`

`DiagramService` contains three methods:

### `create_diagram(db, prompt, user_id?)`
The main generation pipeline (described in the overview above).  
LLM system prompt instructs the model to:
- Return **only** raw Mermaid code (no markdown fences, no explanations)
- Use standard diagram types: `graph TD`, `sequenceDiagram`, `classDiagram`, `stateDiagram-v2`, `erDiagram`
- Apply dark-mode friendly styling where applicable

The service also cleans the LLM output defensively — if the model ignores instructions and wraps the code in triple backticks, the fences are stripped before encoding.

### `get_diagram(db, diagram_id)`
Fetches a single `Diagram` row by its UUID.

### `list_user_diagrams(db, user_id)`
Returns all diagrams associated with a specific learner UUID.

---

## API — `api.py`

Router prefix: `/diagram`  
All endpoints use `AsyncSession = Depends(get_db)` from `app.core.deps`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/diagram/health` | Health check — returns `{"status": "ready", "feature": "diagram"}` |
| `POST` | `/diagram` | Generate a new diagram from a prompt. Returns `DiagramResponse` (201) |
| `GET` | `/diagram/{diagram_id}` | Fetch a specific diagram by UUID. Returns 404 if not found |
| `GET` | `/diagram/user/{user_id}` | List all diagrams for a learner UUID |

### Example: generate a diagram
```bash
curl -X POST http://localhost:8000/diagram \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Sequence diagram for OAuth2 authorization code flow"}'
```

```json
{
  "id": "abc123...",
  "prompt": "Sequence diagram for OAuth2 authorization code flow",
  "image_url": "https://mermaid.ink/svg/eyJjb2RlIjoic2VxdWVuY2VEaWFncmFtLi4uIn0=",
  "status": "completed",
  "created_at": "2026-06-11T09:01:00Z"
}
```

Paste the `image_url` into any browser to see the rendered SVG.

---

## LangChain Tool — `tool.py`

The tool is registered as a `StructuredTool` and exported via `get_diagram_tools()`.  
The agent kernel imports it exactly like the MCQ tools:

```python
from app.features.diagram.tool import get_diagram_tools, DIAGRAM_TOOLS
```

### Tool contract

| Property | Value |
|---|---|
| `name` | `diagram_generate_visualization` |
| `description` | "Generate a visual diagram (e.g. system architecture, sequence diagram, database schema) based on a textual prompt to present to the learner." |
| `args_schema` | `GenerateDiagramToolInput` |

### `GenerateDiagramToolInput`
```python
class GenerateDiagramToolInput(BaseModel):
    prompt: str        # required — description of the diagram to generate
    user_id: str       # optional — learner UUID string
```

### Agent usage example
```python
# Inside a LangGraph node or agent
result = await generate_diagram_for_agent_async(
    prompt="ER diagram for a platform with Users, Courses, and Enrollments",
    user_id="session-uuid-here",
)
# result["image_url"] → send to frontend to render
```

Both **async** (`generate_diagram_for_agent_async`) and **sync** (`generate_diagram_for_agent`) wrappers are provided. The sync wrapper uses `asyncio.run()` for environments that call LangChain tools synchronously.

---

## Frontend — `DiagramView.tsx`

Location: `frontend/src/features/diagram/DiagramView.tsx`

A fully self-contained React component (Next.js, TypeScript, Tailwind CSS) following the **Sprints AI design system** from `design/design.md`:

- **Prompt textarea** with auto-resize and `⌘↵` keyboard shortcut
- **Suggestion chips** for common diagram types
- **Generate button** — calls `POST /diagram`, shows spinner while pending
- **SVG result viewer** — renders the `image_url` in an `<img>` tag
- **Click-to-expand fullscreen** overlay with close button
- **Download SVG** button
- **Loading skeleton**, **empty state**, and **error state**

```tsx
// Usage inside assessment chat
import { DiagramView } from "@/features/diagram/DiagramView";

<DiagramView
  initialPrompt="Database schema for the current assessment"
  userId={session.userId}
/>
```

---

## Integration checklist

To wire this feature into the running application, the following steps are needed:

- [ ] **Router registration** — include `diagram_router` in `app/main.py`:
  ```python
  from app.features.diagram.api import router as diagram_router
  app.include_router(diagram_router)
  ```

- [ ] **Database migration** — create `backend/migrations/versions/0002_diagram.py`:
  ```python
  op.create_table("diagrams",
      sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
      sa.Column("user_id", pg.UUID(as_uuid=True), nullable=True),
      sa.Column("prompt", sa.Text(), nullable=False),
      sa.Column("image_url", sa.Text(), nullable=True),
      sa.Column("status", sa.String(), nullable=False, server_default="pending"),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
  )
  ```
  Then run: `docker compose exec backend alembic upgrade head`

- [ ] **Agent tool registry** — add `DIAGRAM_TOOLS` alongside MCQ tools in the agent graph:
  ```python
  from app.features.diagram.tool import DIAGRAM_TOOLS
  all_tools = MCQ_TOOLS + DIAGRAM_TOOLS + ...
  ```

- [ ] **Environment** — no new env variables needed. Uses `LITELLM_API_KEY` and `LITELLM_MODEL` already defined in `app/config.py`.

---

## Run & Test

```bash
# Start the full stack (includes DB, Redis, backend, frontend)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Run diagram feature tests
docker compose exec backend pytest tests/features/test_diagram.py -v

# Check the health endpoint
curl http://localhost:8000/diagram/health

# Browse Swagger UI
open http://localhost:8000/docs
```

---

## Diagram types supported

The LLM is prompted to produce any valid Mermaid diagram type:

| Type | Mermaid keyword | Use case |
|---|---|---|
| Flowchart | `graph TD` / `graph LR` | System flows, pipelines, decision trees |
| Sequence | `sequenceDiagram` | API calls, auth flows, WebSocket messages |
| Class | `classDiagram` | OOP models, type hierarchies |
| State | `stateDiagram-v2` | Session states, lifecycle diagrams |
| ER | `erDiagram` | Database schemas, table relationships |
| Gantt | `gantt` | Timelines, project phases |

---

## Error handling

| Scenario | Behaviour |
|---|---|
| LLM call times out / fails | Falls back to a template `graph TD` diagram; row status = `completed` |
| LLM returns invalid Mermaid | `mermaid.ink` returns an error image; status still = `completed` |
| `mermaid.ink` unreachable | `image_url` is set; row status = `failed` |
| DB write fails | Exception propagates; FastAPI returns 500 |
| Diagram not found by ID | FastAPI returns 404 |
