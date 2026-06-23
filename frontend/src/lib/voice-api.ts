const API_BASE =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
    /\/$/,
    "",
  );

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // No JSON body; keep the default message.
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export type Difficulty = "beginner" | "intermediate" | "advanced";
export type FollowUpDepth = "simple" | "deep";

export interface StartSessionPayload {
  session_id: string;
  question_text: string;
  question_index: number;
  time_limit_seconds: number;
  target_difficulty: Difficulty;
  learner_profile: Record<string, unknown>;
  admin_config: Record<string, unknown>;
}

export interface StartSessionResponse {
  voice_session_id: number;
  session_id: string;
  question_text: string;
  question_index: number;
  time_limit_seconds: number;
  status: string;
}

export interface AdaptiveContract {
  next_question_text: string;
  difficulty: Difficulty;
  follow_up_depth: FollowUpDepth;
  stop: boolean;
  focus_dimension: string | null;
  question_index: number;
}

export interface ProcessSessionResponse {
  flagged: boolean;
  flag_reason: string | null;
  memory_summary: string;
  adaptive_contract: AdaptiveContract | null;
}

export interface SessionAnalysis {
  total_voice_questions: number;
  mastery_level: string;
  focus_dimension: string | null;
  recommended_depth: FollowUpDepth;
}

export function startAdaptiveVoiceSession(
  payload: StartSessionPayload,
): Promise<StartSessionResponse> {
  return request<StartSessionResponse>("/voice/adaptive/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function processVoiceSession(
  voice_session_id: number,
  payload: StartSessionPayload & { voice_session_id: number },
): Promise<ProcessSessionResponse> {
  return request<ProcessSessionResponse>(
    `/voice/adaptive/sessions/${voice_session_id}/process`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getSessionAnalysis(
  session_id: string,
): Promise<SessionAnalysis> {
  return request<SessionAnalysis>(
    `/voice/adaptive/sessions/${session_id}/analysis`,
  );
}
