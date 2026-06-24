const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export type DimensionName =
  | "thinking"
  | "soft"
  | "work"
  | "digital_ai"
  | "growth";

export interface DimensionRadarPoint {
  name: DimensionName;
  label: string;
  score: number | null;
}

export interface SessionRadarReport {
  session_id: string;
  dimensions: DimensionRadarPoint[];
  overall_score: number | null;
  questions_answered: number;
  tools_used: string[];
  strengths: string[];
  growth_areas: string[];
  evidence_highlights: string[];
  summary: string;
  generated_at: string;
  integrity?: {
    verification_status: string;
    high_severity_count: number;
    threshold: number;
    identity_verified: boolean;
  } | null;
}

export function getSessionRadarReport(
  sessionId: string,
  options?: { accessToken?: string },
): Promise<SessionRadarReport> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options?.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  return fetch(apiUrl(`/api/v1/reports/sessions/${sessionId}/radar`), {
    headers,
  }).then(async (response) => {
    if (!response.ok) {
      let detail = `Request failed with status ${response.status}`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // keep default
      }
      throw new Error(detail);
    }
    return (await response.json()) as SessionRadarReport;
  });
}
