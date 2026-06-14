import { getApiBaseUrl } from "@/lib/endpoints";

const API_BASE = getApiBaseUrl();

export interface HealthStatus {
  status: string;
  db: boolean;
  llm: boolean;
  e2b: boolean;
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
  candidate_time_seconds?: number;
  test_cases: TestCaseRead[];
}

export interface TestCaseResult {
  test_case_id: string;
  passed: boolean;
  actual_output: string;
  expected_output: string;
  execution_time_ms: number;
  error: string | null;
}

export interface RubricScore {
  dimension: string;
  score: number;
  feedback: string;
}

export interface ScoreBreakdown {
  correctness: number;
  completeness: number;
  code_quality: number;
  performance: number;
  creativity: number;
  documentation: number;
}

export interface SubmissionRead {
  id: number;
  challenge_id: number;
  session_id: string;
  submitted_code: string;
  status: string;
  score: number | null;
  passed: boolean | null;
  scores: RubricScore[];
  test_results: TestCaseResult[];
  total_tests: number;
  passed_tests: number;
  hidden_tests_count: number;
  error: string | null;
  evaluation_score?: number | null;
  evaluation_status?: string | null;
  breakdown?: ScoreBreakdown | null;
  strengths?: string[];
  weaknesses?: string[];
  recommendations?: string[];
  next_difficulty?: string | null;
  feedback_summary?: string | null;
}

export interface SubmissionCreate {
  challenge_id: number;
  session_id: string;
  submitted_code: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export interface UserProfile {
  name: string;
  skills: string[];
  experience_level: string;
  interests?: string[];
  career_goals?: string[];
  preferred_domains?: string[];
  previous_experience?: string;
  learning_objectives?: string[];
  prior_performance_summary?: string | null;
}

export interface GeneratedChallengeRead {
  challenge_id: number;
  title: string;
  difficulty: string;
  category: string;
  description: string;
  requirements: string[];
  evaluation_criteria: string[];
  max_score: number;
  estimated_duration: string;
  candidate_time_seconds: number;
  starter_code: string;
  language: string;
  time_limit_seconds: number;
  test_cases: TestCaseRead[];
}

export interface SessionChallengeRead extends GeneratedChallengeRead {
  attempt_id: number;
  position: number;
  challenge_count: number;
  remaining_seconds: number;
  submitted: boolean;
  run_count: number;
}

export interface SessionRead {
  session_id: string;
  status: string;
  total_remaining_seconds: number;
  expires_at: string;
  challenges: SessionChallengeRead[];
  generation_notes: string;
  adaptive?: boolean;
  turns_completed?: number;
  total_questions?: number;
  current_difficulty?: string;
}

export interface AdaptiveSubmitResponse {
  session_id: string;
  status: string;
  turns_completed: number;
  total_questions: number;
  session_complete: boolean;
  message: string;
}

export interface AdaptiveSessionRead extends SessionRead {
  adaptive: boolean;
  turns_completed: number;
  total_questions: number;
  current_difficulty: string;
}

export interface LearnerCodeAnalysis {
  dimension_estimates: Record<string, number>;
  strong_problem_types: string[];
  weak_problem_types: string[];
  average_pass_rate: number;
  average_efficiency: number;
  average_rubric_score: number;
  turns_completed: number;
}

export interface RunRead {
  outcome: string;
  test_results: TestCaseResult[];
  passed_tests: number;
  total_tests: number;
  error: string | null;
  remaining_seconds: number;
  run_count: number;
}

export interface RunCreate {
  session_id: string;
  challenge_id: number;
  submitted_code: string;
}

export interface ChallengeGenerationSettings {
  categories: string[];
  difficulty_levels: string[];
  challenges_per_candidate: number;
  total_time_minutes: number;
  min_time_per_challenge_minutes: number;
  max_time_per_challenge_minutes: number;
  duration_minutes: number;
  min_complexity: number;
  max_complexity: number;
  default_language: string;
  allowed_languages: string[];
  domain: string;
  e2b_execution_timeout_seconds: number;
  e2b_template: string;
}

export interface PlatformChallengeConfig {
  challenge: ChallengeGenerationSettings;
}

export interface GenerateChallengesResponse {
  challenges: GeneratedChallengeRead[];
  generation_notes: string;
}

export function generateCodeChallenges(
  profile: UserProfile,
): Promise<GenerateChallengesResponse> {
  return request<GenerateChallengesResponse>("/api/v1/code/challenges/generate", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function startCodeSession(profile: UserProfile): Promise<SessionRead> {
  return request<SessionRead>("/api/v1/code/sessions", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function startAdaptiveSession(profile: UserProfile): Promise<AdaptiveSessionRead> {
  return request<AdaptiveSessionRead>("/api/v1/code/adaptive/sessions", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function getAdaptiveSession(sessionId: string): Promise<AdaptiveSessionRead> {
  return request<AdaptiveSessionRead>(`/api/v1/code/adaptive/sessions/${sessionId}`);
}

export function submitAdaptiveTurn(
  sessionId: string,
  body: { challenge_id: number; submitted_code: string },
): Promise<AdaptiveSubmitResponse> {
  return request<AdaptiveSubmitResponse>(`/api/v1/code/adaptive/sessions/${sessionId}/submit`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getAdaptiveAnalysis(sessionId: string): Promise<LearnerCodeAnalysis> {
  return request<LearnerCodeAnalysis>(`/api/v1/code/adaptive/sessions/${sessionId}/analysis`);
}

export function getCodeSession(sessionId: string): Promise<SessionRead> {
  return request<SessionRead>(`/api/v1/code/sessions/${sessionId}`);
}

export interface SessionSubmissionsRead {
  session_id: string;
  submissions: SubmissionRead[];
}

export function getSessionSubmissions(
  sessionId: string,
): Promise<SessionSubmissionsRead> {
  return request<SessionSubmissionsRead>(
    `/api/v1/code/sessions/${sessionId}/submissions`,
  );
}

export function runCode(body: RunCreate): Promise<RunRead> {
  return request<RunRead>("/api/v1/code/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

export type {
  IntegrityEventCreate,
  IntegrityReport,
  IntegritySessionSummary,
  RecordEventsRequest,
} from "@/types/proctoring";

export function recordProctoringEvents(
  body: import("@/types/proctoring").RecordEventsRequest,
): Promise<{ recorded: number; session_id: string }> {
  return request("/api/v1/proctoring/events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ProctoringConfigRead {
  warning_thresholds: Record<string, number>;
  notification_messages: Record<string, string>;
  event_types: string[];
}

export interface ViolationSummary {
  session_id: string;
  total_violations: number;
  escalation_level: "none" | "warning" | "elevated";
  counts_by_type: Record<string, number>;
  integrity_score: number;
  risk_level: string;
}

export interface SessionCompletionRead {
  session_id: string;
  status: string;
  completed_at: string;
  challenges_submitted: number;
  challenges_total: number;
  unsubmitted_challenge_ids: number[];
  integrity_score: number | null;
  integrity_risk_level: string | null;
  message: string;
}

export function getProctoringConfig(): Promise<ProctoringConfigRead> {
  return request<ProctoringConfigRead>("/api/v1/proctoring/config");
}

export function getViolationSummary(sessionId: string): Promise<ViolationSummary> {
  return request<ViolationSummary>(`/api/v1/proctoring/sessions/${sessionId}/violations`);
}

export function completeCodeSession(
  sessionId: string,
  confirmUnsubmitted = false,
): Promise<SessionCompletionRead> {
  return request<SessionCompletionRead>(`/api/v1/code/sessions/${sessionId}/complete`, {
    method: "POST",
    body: JSON.stringify({ confirm_unsubmitted: confirmUnsubmitted }),
  });
}

export function getIntegrityReport(
  sessionId: string,
): Promise<import("@/types/proctoring").IntegrityReport> {
  return request(`/api/v1/proctoring/sessions/${sessionId}/report`);
}

export function getIntegrationCapabilities(): Promise<
  import("@/integrations/types").FeatureCapability[]
> {
  return request("/api/v1/integrations/capabilities");
}

export function getSessionIntegrityFlags(
  sessionId: string,
): Promise<import("@/integrations/types").IntegrityFlag[]> {
  return request(`/api/v1/integrations/sessions/${sessionId}/integrity-flags`);
}

export function getTimedSessionSummary(
  sessionId: string,
): Promise<import("@/integrations/types").TimedCodeSessionSummary> {
  return request(`/api/v1/integrations/sessions/${sessionId}/timed-summary`);
}

export function getAdminIntegritySessions(
  adminKey?: string,
): Promise<import("@/types/proctoring").IntegritySessionSummary[]> {
  const headers: Record<string, string> = {};
  if (adminKey) {
    headers["X-Admin-Key"] = adminKey;
  }
  return request("/api/v1/proctoring/admin/sessions", { headers });
}

export function getCodeConfig(): Promise<PlatformChallengeConfig> {
  return request<PlatformChallengeConfig>("/api/v1/admin/code-config");
}

export function updateCodeConfig(
  config: PlatformChallengeConfig,
  adminKey?: string,
): Promise<PlatformChallengeConfig> {
  const headers: Record<string, string> = {};
  if (adminKey) {
    headers["X-Admin-Key"] = adminKey;
  }
  return request<PlatformChallengeConfig>("/api/v1/admin/code-config", {
    method: "PUT",
    headers,
    body: JSON.stringify(config),
  });
}

export function getCodeChallenge(id: number): Promise<ChallengeRead> {
  return request<ChallengeRead>(`/api/v1/code/challenges/${id}`);
}

export function createCodeSubmission(
  body: SubmissionCreate,
): Promise<SubmissionRead> {
  return request<SubmissionRead>("/api/v1/code/submissions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getCodeSubmission(id: number): Promise<SubmissionRead> {
  return request<SubmissionRead>(`/api/v1/code/submissions/${id}`);
}

// ── Platform sessions (LangGraph agent-driven) ─────────────────────────────

export interface StartSessionRequest {
  name: string;
  skills: string[];
  experience_level?: string;
  preferred_domains?: string[];
  learning_objectives?: string[];
  prior_performance_summary?: string | null;
  assessment_id?: string | null;
  consent_given?: boolean;
  camera_enabled?: boolean;
}

export interface SessionStartResponse {
  session_id: string;
  access_token: string;
  ws_url: string;
  status: string;
  assessment_id: string;
}

export interface PlatformSessionRead {
  session_id: string;
  assessment_id: string;
  status: string;
  code_session_id: string | null;
  skill_scores: Record<string, number>;
  started_at: string | null;
  completed_at: string | null;
  ws_url: string;
}

export function startPlatformSession(
  body: StartSessionRequest,
): Promise<SessionStartResponse> {
  return request<SessionStartResponse>("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getPlatformSession(sessionId: string): Promise<PlatformSessionRead> {
  return request<PlatformSessionRead>(`/api/v1/sessions/${sessionId}`);
}
