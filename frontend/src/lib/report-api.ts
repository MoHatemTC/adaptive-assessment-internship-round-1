const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""
).replace(/\/$/, "");

function apiUrl(path: string): string {
  if (API_BASE) return `${API_BASE}${path}`;
  if (typeof window !== "undefined") return path;
  const origin = process.env.BACKEND_URL ?? "http://localhost:8000";
  return `${origin.replace(/\/$/, "")}${path}`;
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
}

export function getSessionRadarReport(
  sessionId: string,
): Promise<SessionRadarReport> {
  return fetch(apiUrl(`/api/v1/reports/sessions/${sessionId}/radar`), {
    headers: { Accept: "application/json" },
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
