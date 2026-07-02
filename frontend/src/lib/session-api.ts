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

export async function signInSession(
  assessmentId: string,
  learnerProfile: LearnerProfile,
  cvFile: File | undefined,
  idCardFile: File,
): Promise<SessionSignInResponse> {
  const formData = new FormData();
  formData.append("assessment_id", assessmentId);
  formData.append("learner_profile", JSON.stringify(learnerProfile));
  if (cvFile) formData.append("cv_file", cvFile);
  formData.append("id_card_image", idCardFile);

  // Raw fetch (not the JSON `request` helper) so the browser sets the
  // multipart boundary automatically. Do not set Content-Type manually.
  const response = await fetch(apiUrl("/api/v1/sessions/sign-in"), {
    method: "POST",
    body: formData,
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
  return (await response.json()) as SessionSignInResponse;
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

export function getMySession(accessToken: string): Promise<SessionRead> {
  return request<SessionRead>("/api/v1/sessions/me", { method: "GET" }, accessToken);
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

export async function listAssessmentSessions(
  assessmentId: string,
  adminToken: string,
): Promise<Array<{ id: string; status: string; created_at: string; learner_name: string }>> {
  return request<
    Array<{ id: string; status: string; created_at: string; learner_name: string }>
  >(
    `/api/v1/sessions?assessment_id=${encodeURIComponent(assessmentId)}`,
    { method: "GET" },
    adminToken,
  );
}

export interface NextToolInfo {
  tool: string;
  difficulty: string;
  question_number: number;
  total_for_tool: number;
  time_limit_seconds?: number | null;
}

export interface ExaminerRespondResponse {
  current_tool: string | null;
  next_tool_info: NextToolInfo | null;
  is_complete: boolean;
}

/**
 * Advance the examiner router and learn which tool to render next. The answer
 * itself is graded by the tool's own endpoint; this only sequences tools.
 *
 * @param action - "start" to fetch the first tool, "next" to advance one
 *   question, or "complete_tool" to finish the current tool.
 */
export function submitResponse(
  sessionId: string,
  tool: string,
  action: "start" | "next" | "complete_tool",
  accessToken: string,
): Promise<ExaminerRespondResponse> {
  return request<ExaminerRespondResponse>(
    `/api/v1/sessions/${sessionId}/respond`,
    { method: "POST", body: JSON.stringify({ tool, action }) },
    accessToken,
  );
}

export type { VerificationStatus };
