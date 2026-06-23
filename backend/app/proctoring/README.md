# Proctoring & Integrity (Backend)

Platform-wide integrity monitoring for every question type. Events are recorded
in parallel during a learner session; the service computes a per-session
verification status and auto-flags sessions when high-severity events exceed a
configurable threshold.

## Architecture

```
Mohamed FE (integrity monitor)
        │
        ▼
POST /api/v1/proctoring/events
POST /api/v1/proctoring/sessions/{id}/verify-identity
GET  /api/v1/proctoring/sessions/{id}/integrity
        │
        ▼
app/proctoring/service.py  ──►  proctoring_events (Postgres)
        │                         assessment_sessions.status = flagged
        ▼
app/shared/schemas/proctoring.py  (published contract)
```

Identity images are compared in memory via a pluggable face-match provider:

- **Hugging Face (default):** ArcFace ONNX embeddings from
  `onnx-community/arcface-onnx` — cosine similarity vs `FACE_MATCH_THRESHOLD`.
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
|----------|---------|
| `FACE_PROVIDER` | `huggingface`, `azure`, or `auto` (prefer HF, then Azure) |
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
  | "tab_switch" | "copy_paste" | "screenshot"
  | "ai_usage" | "identity_fail" | "identity_verified";

type ProctoringSeverity = "low" | "medium" | "high";

interface ProctoringEventCreate {
  session_id: string;
  event_type: ProctoringEventType;
  severity: ProctoringSeverity;
  metadata?: Record<string, unknown>;
  client_timestamp?: string; // ISO-8601
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
|-----------|--------|
| No `identity_verified` and no `identity_fail` | `pending` |
| Any `identity_fail` event | `identity_failed` |
| High-severity count ≥ threshold or session `flagged` | `flagged` |
| `identity_verified` and below threshold | `verified` |

## Testing

```bash
cd backend && pytest tests/proctoring/ -q
```
