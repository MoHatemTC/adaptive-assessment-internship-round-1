import type { SessionIntegritySnapshot, VerificationStatus } from "@/features/proctoring/types";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export interface LearnerProfile {
  name?: string;
  role?: string;
  level?: string;
  target_skills?: string[];
  consent_given: boolean;
}

export interface SessionSignInResponse {
  session_id: string;
  access_token: string;
  token_type: string;
}

export interface SessionRead {
  id: string;
  assessment_id: string;
  learner_profile: Record<string, unknown>;
  status: string;
  code_session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  integrity: SessionIntegritySnapshot | null;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  accessToken?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(apiUrl(path), { ...init, headers });
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

export function signInSession(payload: {
  assessment_id: string;
  learner_profile: LearnerProfile;
}): Promise<SessionSignInResponse> {
  return request<SessionSignInResponse>("/api/v1/sessions/sign-in", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function startSession(
  sessionId: string,
  accessToken: string,
): Promise<SessionRead> {
  return request<SessionRead>(
    `/api/v1/sessions/${sessionId}/start`,
    { method: "POST" },
    accessToken,
  );
}

export function completeSession(
  sessionId: string,
  accessToken: string,
): Promise<SessionRead> {
  return request<SessionRead>(
    `/api/v1/sessions/${sessionId}/complete`,
    { method: "POST" },
    accessToken,
  );
}

export type { VerificationStatus };
