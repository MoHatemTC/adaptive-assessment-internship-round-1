import type { AdaptiveContract, DifficultyLevel, SupportedLanguage } from "@/lib/api";

/** How the coding UI is mounted in the platform shell. */
export type CodeChallengeMode = "standalone" | "embedded";

export interface CodeSessionCompleteSummary {
  questionsAnswered: number;
  reason: "learner" | "adaptive";
  sessionId: string;
  assessmentId: string;
}

export interface CodeChallengeViewProps {
  /** Platform assessment session UUID. Generated locally in standalone demo mode. */
  sessionId?: string;
  /** Parent assessment id from admin blueprint. */
  assessmentId?: string;
  /** Load a fixed challenge instead of LLM generation (dev / direct link). */
  initialChallengeId?: number;
  mode?: CodeChallengeMode;
  /** 1-based question index for the assessment progress header. */
  questionNumber?: number;
  /** Total questions in blueprint when known. */
  totalQuestions?: number;
  /** Optional countdown budget in seconds for the header timer. */
  timeLimitSeconds?: number;
  initialLanguage?: SupportedLanguage;
  /** Skip the pre-session language picker (embedded examiner flow). */
  autoStart?: boolean;
  onExit?: () => void;
  onSessionComplete?: (summary: CodeSessionCompleteSummary) => void;
  onSubmitted?: (payload: { contract: AdaptiveContract }) => void;
}

export function difficultyLabel(difficulty: DifficultyLevel): string {
  switch (difficulty) {
    case "beginner":
      return "Beginner";
    case "intermediate":
      return "Medium";
    case "advanced":
      return "Advanced";
    default:
      return difficulty;
  }
}
