import {
  clearAdminToken,
  isAdminTokenValid,
  SessionExpiredError,
} from "@/lib/admin-auth";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/** localStorage key for the admin JWT. Shared with the results page. */
export const ADMIN_TOKEN_KEY = "masaar_admin_token";

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Read the admin JWT from localStorage (empty string when unauthenticated). */
export function getAdminToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(ADMIN_TOKEN_KEY) ?? "";
}

/** Persist the admin JWT to localStorage. */
export function setAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

function authHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${getAdminToken()}`,
  };
}

async function readError(response: Response): Promise<string> {
  let detail = `Request failed with status ${response.status}`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    // keep default
  }
  return detail;
}

/** Authenticated admin fetch — clears stale JWT and throws on 401. */
async function adminFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  if (!isAdminTokenValid()) {
    clearAdminToken();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("admin-session-expired"));
    }
    throw new SessionExpiredError();
  }

  const headers = {
    ...authHeaders(),
    ...(init.headers as Record<string, string> | undefined),
  };

  const response = await fetch(apiUrl(path), { ...init, headers });

  if (response.status === 401) {
    clearAdminToken();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("admin-session-expired"));
    }
    throw new SessionExpiredError();
  }

  return response;
}

export type AssessmentStatus = "draft" | "active" | "archived";

export interface ToolBlueprint {
  enabled: boolean;
  question_count: number;
  min_difficulty: string;
  max_difficulty: string;
  time_limit_seconds: number | null;
}

export interface Blueprint {
  title: string;
  description: string;
  tools: Record<string, ToolBlueprint>;
  skill_dimensions: string[];
  total_questions: number;
}

export interface AssessmentRead {
  id: string;
  title: string;
  prompt: string;
  blueprint_json: Record<string, unknown>;
  tool_config: Record<string, unknown>;
  status: string;
  cv_required: boolean;
  created_at: string;
  updated_at: string;
}

export interface BlueprintGenerateResponse {
  assessment_id: string;
  title: string;
  blueprint: Blueprint;
  shareable_link: string;
}

export interface AssessmentLinkResponse {
  assessment_id: string;
  shareable_link: string;
  title: string;
  status: string;
}

/** Authenticate as admin. The backend expects a JSON body. */
export async function adminLogin(
  username: string,
  password: string,
): Promise<{ access_token: string }> {
  const response = await fetch(apiUrl("/api/v1/auth/token"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as { access_token: string };
}

export async function createAssessment(data: {
  title: string;
  prompt: string;
  tool_config: Record<string, boolean>;
  cv_required: boolean;
}): Promise<AssessmentRead> {
  const response = await adminFetch("/api/v1/admin/assessments", {
    method: "POST",
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AssessmentRead;
}

export async function generateBlueprint(
  assessmentId: string,
): Promise<BlueprintGenerateResponse> {
  const response = await adminFetch(
    `/api/v1/admin/assessments/${assessmentId}/generate-blueprint`,
    { method: "POST" },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as BlueprintGenerateResponse;
}

export async function listAssessments(): Promise<AssessmentRead[]> {
  const response = await adminFetch("/api/v1/admin/assessments");
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AssessmentRead[];
}

export async function getAssessment(id: string): Promise<AssessmentRead> {
  const response = await adminFetch(`/api/v1/admin/assessments/${id}`);
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AssessmentRead;
}

export async function getShareableLink(
  assessmentId: string,
): Promise<AssessmentLinkResponse> {
  const response = await adminFetch(
    `/api/v1/admin/assessments/${assessmentId}/link`,
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AssessmentLinkResponse;
}

/** Integrity snapshot for admin results panel (Abutaleb). */
export interface SessionIntegritySnapshot {
  verification_status: string;
  high_severity_count: number;
  threshold: number;
  identity_verified: boolean;
}

export async function getSessionIntegritySummary(
  sessionId: string,
): Promise<SessionIntegritySnapshot> {
  const response = await adminFetch(
    `/api/v1/admin/sessions/${sessionId}/integrity-summary`,
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as SessionIntegritySnapshot;
}

export { SessionExpiredError } from "@/lib/admin-auth";
