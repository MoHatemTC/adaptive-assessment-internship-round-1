import type {
  AudioAnalyzeResponse,
  CameraAnalyzeResponse,
  IdentityVerifyResponse,
  ProctoringEventBatchCreate,
  ProctoringEventCreate,
  ProctoringEventRead,
  ProctoringPolicyResponse,
  SessionIntegritySummary,
} from "@/features/proctoring/types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep default
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function getProctoringPolicy(
  sessionId: string,
): Promise<ProctoringPolicyResponse> {
  return request<ProctoringPolicyResponse>(
    `/api/v1/proctoring/sessions/${sessionId}/policy`,
  );
}

export function recordProctoringEvent(
  payload: ProctoringEventCreate,
): Promise<ProctoringEventRead> {
  return request<ProctoringEventRead>("/api/v1/proctoring/events", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function recordProctoringEventsBatch(
  payload: ProctoringEventBatchCreate,
): Promise<{ recorded: ProctoringEventRead[]; skipped: unknown[] }> {
  return request("/api/v1/proctoring/events/batch", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSessionIntegrity(
  sessionId: string,
): Promise<SessionIntegritySummary> {
  return request<SessionIntegritySummary>(
    `/api/v1/proctoring/sessions/${sessionId}/integrity`,
  );
}

export function analyzeCameraFrame(payload: {
  session_id: string;
  frame_b64: string;
  reference_image_b64?: string;
  client_timestamp?: string;
}): Promise<CameraAnalyzeResponse> {
  return request<CameraAnalyzeResponse>(
    `/api/v1/proctoring/sessions/${payload.session_id}/analyze-camera`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function analyzeAudioSignal(payload: {
  session_id: string;
  average_rms: number;
  microphone_muted: boolean;
  microphone_enabled: boolean;
  client_timestamp?: string;
}): Promise<AudioAnalyzeResponse> {
  return request<AudioAnalyzeResponse>(
    `/api/v1/proctoring/sessions/${payload.session_id}/analyze-audio`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function verifySessionIdentity(payload: {
  session_id: string;
  reference_image_b64: string;
  live_capture_b64: string;
}): Promise<IdentityVerifyResponse> {
  return request(
    `/api/v1/proctoring/sessions/${payload.session_id}/verify-identity`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}
