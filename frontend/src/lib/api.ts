const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""
).replace(/\/$/, "");

function apiUrl(path: string): string {
  if (API_BASE_URL) return `${API_BASE_URL}${path}`;
  if (typeof window !== "undefined") return path;
  const origin = process.env.BACKEND_URL ?? "http://localhost:8000";
  return `${origin.replace(/\/$/, "")}${path}`;
}

export type ToolType = "voice" | "mcq" | "diagram" | "coding";
export type DifficultyLevel = "beginner" | "intermediate" | "advanced";
export type DimensionName =
  | "thinking"
  | "soft"
  | "work"
  | "digital_ai"
  | "growth";

export interface DimensionScore {
  thinking: number | null;
  soft: number | null;
  work: number | null;
  digital_ai: number | null;
  growth: number | null;
}

export interface AdaptiveContract {
  session_id: string;
  question_index: number;
  tool_type: ToolType;
  difficulty: DifficultyLevel;
  focus_dimension: DimensionName | null;
  stop: boolean;
  memory_summary: string;
  cumulative_scores: DimensionScore;
}

export interface TestCaseRead {
  id: number;
  input: string;
  expected_output: string | null;
  is_hidden: boolean;
  weight: number;
}

export interface ChallengeRead {
  id: number;
  title: string;
  description: string;
  starter_code: string;
  language: string;
  time_limit_seconds: number;
  test_cases: TestCaseRead[];
  created_at: string;
  updated_at: string;
}

export interface ChallengeListItem {
  id: number;
  title: string;
  language: string;
  time_limit_seconds: number;
  created_at: string;
}

export type SubmissionStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface RubricScoreRead {
  dimension: string;
  score: number;
  feedback: string;
}

export interface TestCaseResult {
  test_case_id: string;
  passed: boolean;
  actual_output: string;
  expected_output: string;
  execution_time_ms: number;
  error: string | null;
}

export interface SubmissionRead {
  id: number;
  challenge_id: number;
  session_id: string;
  submitted_code: string;
  status: SubmissionStatus;
  score: number | null;
  passed: boolean | null;
  scores: RubricScoreRead[];
  test_results: TestCaseResult[];
  total_tests: number;
  passed_tests: number;
  hidden_tests_count: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateSubmissionRequest {
  challenge_id: number;
  session_id: string;
  submitted_code: string;
}

export interface AdaptiveSubmitRequest {
  challenge_id: number;
  session_id: string;
  assessment_id: string;
  submitted_code: string;
  question_index: number;
  difficulty: DifficultyLevel;
}

export interface AdaptiveSubmitResponse {
  submission_id: number;
  passed: boolean | null;
  score: number | null;
  llm_rubric: LlmRubricSummary | null;
  contract: AdaptiveContract;
  next_challenge: ChallengeRead | null;
}

export interface LlmRubricSummary {
  approach_score: number;
  approach_feedback: string;
  efficiency_score: number;
  efficiency_feedback: string;
  overall: number;
}

export interface GenerateChallengeRequest {
  session_id: string;
  assessment_id: string;
  contract?: AdaptiveContract | null;
}

export interface GenerateChallengeResponse {
  challenge: ChallengeRead;
  contract: AdaptiveContract;
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
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Response had no JSON body; keep the default message.
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function getChallenge(challengeId: number): Promise<ChallengeRead> {
  return request<ChallengeRead>(`/api/v1/code/challenges/${challengeId}`);
}

export function listChallenges(): Promise<ChallengeListItem[]> {
  return request<ChallengeListItem[]>("/api/v1/code/challenges");
}

export function createCodeSubmission(
  payload: CreateSubmissionRequest,
): Promise<SubmissionRead> {
  return request<SubmissionRead>("/api/v1/code/submissions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createAdaptiveCodeSubmission(
  payload: AdaptiveSubmitRequest,
): Promise<AdaptiveSubmitResponse> {
  return request<AdaptiveSubmitResponse>("/api/v1/code/adaptive-submit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function generateCodeChallenge(
  payload: GenerateChallengeRequest,
): Promise<GenerateChallengeResponse> {
  return request<GenerateChallengeResponse>("/api/v1/code/generate-challenge", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getCodeSubmission(
  submissionId: number,
): Promise<SubmissionRead> {
  return request<SubmissionRead>(`/api/v1/code/submissions/${submissionId}`);
}
