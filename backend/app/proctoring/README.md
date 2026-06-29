# Proctoring & Integrity (Backend)

Platform-wide integrity monitoring for every question type. Events are recorded
in parallel during a learner session; the service computes a per-session
verification status and auto-flags sessions when high-severity events exceed a
configurable threshold.

## Architecture

```text
Mohamed FE (integrity monitor)
        │
        ▼
POST /api/v1/proctoring/events
POST /api/v1/proctoring/events/batch
GET  /api/v1/proctoring/sessions/{id}/policy
POST /api/v1/proctoring/sessions/{id}/verify-identity
POST /api/v1/proctoring/sessions/{id}/analyze-camera
POST /api/v1/proctoring/sessions/{id}/analyze-audio
GET  /api/v1/proctoring/sessions/{id}/integrity
        │
        ▼
app/proctoring/service.py  ──►  proctoring_events (Postgres)
        │                         assessment_sessions.status = flagged
        ▼
app/shared/schemas/proctoring.py  (published contract)
```

Identity and live camera frames are analyzed in memory via a pluggable provider:

- **VLM (recommended with Sprint.ai):** Kimi K2.6 via LiteLLM (`FACE_PROVIDER=vlm`
  or `auto` when `LITELLM_API_KEY` is set). Handles identity verification and
  periodic `analyze-camera` frame checks.
- **Hugging Face:** ArcFace ONNX embeddings from `onnx-community/arcface-onnx`.
- **Azure Face API:** optional fallback when `FACE_PROVIDER=azure`.

Only match scores are stored in event metadata — never raw image bytes (PDPL alignment).

## Admin configuration

Set the high-severity threshold per assessment in `tool_config` or `blueprint_json`:

```json
{
  "proctoring": {
    "high_severity_threshold": 3
  }
}
```

When omitted, `PROCTORING_HIGH_SEVERITY_THRESHOLD` from `.env` is used (dev fallback).

## Environment

| Variable | Purpose |
| -------- | ------- |
| `FACE_PROVIDER` | `vlm`, `huggingface`, `azure`, or `auto` (prefer VLM when LiteLLM configured) |
| `LITELLM_API_KEY` / `LITELLM_BASE_URL` / `LITELLM_MODEL` | Required for VLM proctoring (e.g. `openai/FW-Kimi-K2.6`) |
| `LITELLM_VISION_MODEL` | Optional dedicated vision model; defaults to `LITELLM_MODEL` |
| `HF_TOKEN` | Hugging Face token for model download (optional for public models) |
| `HF_FACE_MODEL_REPO` | HF repo with ArcFace ONNX weights (default `onnx-community/arcface-onnx`) |
| `HF_FACE_MODEL_FILE` | ONNX filename (default `arcface.onnx`) |
| `FACE_API_ENDPOINT` | Azure Face API base URL |
| `FACE_API_KEY` | Azure subscription key |
| `FACE_MATCH_THRESHOLD` | Minimum similarity (0–1) for identity match |
| `PROCTORING_HIGH_SEVERITY_THRESHOLD` | Dev fallback flag threshold |

## API contract (Mohamed — mirror in TypeScript)

### `POST /api/v1/proctoring/events`

```typescript
type ProctoringEventType =
  | "tab_switch" | "window_blur" | "fullscreen_exit"
  | "devtools_open" | "context_menu" | "print_attempt"
  | "copy" | "paste" | "copy_paste"
  | "screenshot" | "ai_usage" | "idle_timeout"
  | "identity_fail" | "identity_verified"
  | "face_absent" | "multiple_faces" | "camera_obstructed" | "camera_disabled"
  | "looking_away" | "identity_mismatch"
  | "microphone_muted" | "microphone_disabled" | "audio_absent";

type ProctoringSeverity = "low" | "medium" | "high";

interface ProctoringEventCreate {
  session_id: string;
  event_type: ProctoringEventType;
  severity?: ProctoringSeverity; // server assigns canonical severity
  metadata?: Record<string, unknown>;
  client_timestamp?: string; // ISO-8601
}
```

### `POST /api/v1/proctoring/events/batch`

```typescript
interface ProctoringEventBatchCreate {
  session_id: string;
  events: ProctoringEventCreate[]; // max 50
}

interface ProctoringEventBatchResponse {
  recorded: ProctoringEventRead[];
  skipped: Array<{ event_type: ProctoringEventType; reason: string }>;
}
```

### `GET /api/v1/proctoring/sessions/{session_id}/policy`

```typescript
interface ProctoringPolicyResponse {
  session_id: string;
  high_severity_threshold: number;
  enabled_checks: ProctoringEventType[];
  camera_poll_interval_seconds: number;
  event_cooldown_seconds: number;
  require_camera: boolean;
  require_microphone: boolean;
  default_severities: Record<ProctoringEventType, ProctoringSeverity>;
}
```

### `POST /api/v1/proctoring/sessions/{session_id}/verify-identity`

```typescript
interface IdentityVerifyRequest {
  session_id: string;
  reference_image_b64: string;
  live_capture_b64: string;
}

type VerificationStatus =
  | "pending" | "verified" | "flagged" | "identity_failed";

interface IdentityVerifyResponse {
  verified: boolean;
  match_score: number | null;
  verification_status: VerificationStatus;
  message?: string;
}
```

Requires `consent_given: true` in the session's `learner_profile_json`.

### `POST /api/v1/proctoring/sessions/{session_id}/analyze-camera`

Periodic live webcam check during the session. The VLM inspects the frame and
records violation events server-side (face absent, multiple faces, etc.).

```typescript
interface CameraAnalyzeRequest {
  session_id: string;
  frame_b64: string;
  reference_image_b64?: string; // enrolled photo for identity continuity
  client_timestamp?: string;
}

interface CameraAnalyzeResponse {
  compliant: boolean;
  face_visible: boolean;
  face_count: number;
  identity_match_score: number | null;
  violations: Array<{
    event_type: ProctoringEventType;
    severity: ProctoringSeverity;
    description: string;
  }>;
  events_recorded: ProctoringEventRead[];
}
```

Recommended FE flow: capture a JPEG frame every 15–30s after identity verification,
include `reference_image_b64` when available, and surface `violations` to the monitor UI.

### `POST /api/v1/proctoring/sessions/{session_id}/analyze-audio`

Microphone-integrity check from client-side signal metrics (no raw audio upload).

```typescript
interface AudioAnalyzeRequest {
  session_id: string;
  average_rms: number;       // 0.0-1.0
  microphone_muted: boolean;
  microphone_enabled: boolean;
  client_timestamp?: string;
}

interface AudioAnalyzeResponse {
  compliant: boolean;
  violations: Array<{
    event_type: ProctoringEventType;
    severity: ProctoringSeverity;
    description: string;
  }>;
  events_recorded: ProctoringEventRead[];
}
```

### `GET /api/v1/proctoring/sessions/{session_id}/integrity`

```typescript
interface SessionIntegritySummary {
  session_id: string;
  verification_status: VerificationStatus;
  high_severity_count: number;
  threshold: number;
  identity_verified: boolean;
  events: ProctoringEventRead[];
}
```

## Verification status rules

| Condition | Status |
| --------- | ------ |
| No `identity_verified` and no `identity_fail` | `pending` |
| Any `identity_fail` event | `identity_failed` |
| High-severity count ≥ threshold or session `flagged` | `flagged` |
| `identity_verified` and below threshold | `verified` |

## Testing

```bash
cd backend && pytest tests/proctoring/ -q
```

## Sprint 4 integration (Karim / Abutaleb)

### Karim — wire enforcement in new tool endpoints

Call at the top of any handler that accepts a platform ``session_id``:

```python
from app.proctoring.enforcement import ensure_tool_session_allowed

await ensure_tool_session_allowed(db, session_id)
```

Already wired: code generate/submit, MCQ answer, diagram answer, voice adaptive start, examiner ``POST /sessions/{id}/respond``.

Bearer-authenticated routes should use:

```python
from app.proctoring.deps import require_active_proctored_session
```

### Abutaleb — admin integrity + chat UI

- **Integrity panel:** `GET /api/v1/admin/sessions/{session_id}/integrity-summary` (admin JWT)
- **Frontend helper:** `getSessionIntegritySummary(sessionId)` in `frontend/src/lib/admin-api.ts`
- **Chat proctoring:** wrap tools in `SessionProctoringShell` with `manageLifecycle={false}`; session completes only via explicit complete page
- **Post-completion pipeline:** `complete_session` enqueues Celery `reports.build_session_radar` → `reports.email_session_report` (requires `SMTP_*` env)

### LLM judge (stretch)

- Stub: `app/agent/nodes/judge.py` — `run_session_judge(db, session_id)` reads `grade_results.rubric_scores.overall`
- Karim: ensure each tool loop writes `grade_results` before examiner advances

### Env (email)

| Variable | Purpose |
| -------- | ------- |
| `SMTP_HOST` | Mail server |
| `SMTP_PORT` | Default 587 |
| `SMTP_USER` / `SMTP_PASSWORD` | Auth |
| `SMTP_FROM` | From address |
| `ADMIN_REPORT_EMAIL` | Admin copy on completion |

