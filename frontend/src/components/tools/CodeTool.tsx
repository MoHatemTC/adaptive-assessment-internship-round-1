"use client";

import { CodeEditor } from "@/features/code/CodeEditor";
import { CountdownTimer } from "@/features/code/CountdownTimer";
import type {
  AdaptiveSubmitResponse,
  ChallengeRead,
  SessionChallengeRead,
  SubmissionRead,
} from "@/lib/api";

export interface CodeToolProps {
  /** Timed assessment session id (`assess-*`). */
  sessionId: string;
  /** Challenge slot from a session or a standalone challenge read model. */
  challenge: SessionChallengeRead | ChallengeRead;
  /** Session-wide remaining seconds (optional; shown when provided). */
  sessionRemainingSeconds?: number;
  disabled?: boolean;
  blockClipboard?: boolean;
  adaptiveMode?: boolean;
  adaptiveGrading?: "api" | "agent";
  onSubmitted?: (result: SubmissionRead) => void;
  onAdaptiveSubmitted?: (result: AdaptiveSubmitResponse) => void;
  onSubmitCode?: (code: string) => void;
  onRunComplete?: () => void;
}

function isSessionChallenge(
  challenge: SessionChallengeRead | ChallengeRead,
): challenge is SessionChallengeRead {
  return "challenge_id" in challenge && "remaining_seconds" in challenge;
}

function toEditorChallenge(challenge: SessionChallengeRead | ChallengeRead): ChallengeRead {
  if (isSessionChallenge(challenge)) {
    return {
      id: challenge.challenge_id,
      title: challenge.title,
      description: challenge.description,
      starter_code: challenge.starter_code,
      language: challenge.language,
      time_limit_seconds: challenge.time_limit_seconds,
      candidate_time_seconds: challenge.candidate_time_seconds,
      test_cases: challenge.test_cases,
    };
  }
  return challenge;
}

/**
 * Embeddable code challenge widget for the adaptive chat examiner.
 * Wraps the Monaco editor with Run / Submit and optional countdown timers.
 */
export function CodeTool({
  sessionId,
  challenge,
  sessionRemainingSeconds,
  disabled = false,
  blockClipboard = false,
  adaptiveMode = false,
  adaptiveGrading = "api",
  onSubmitted,
  onAdaptiveSubmitted,
  onSubmitCode,
  onRunComplete,
}: CodeToolProps) {
  const slot = isSessionChallenge(challenge) ? challenge : null;

  return (
    <div className="space-y-3 rounded-xl border border-border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Coding challenge
        </p>
        <div className="flex flex-wrap gap-2">
          {sessionRemainingSeconds !== undefined && (
            <CountdownTimer remainingSeconds={sessionRemainingSeconds} label="Session" />
          )}
          {slot && (
            <CountdownTimer remainingSeconds={slot.remaining_seconds} label="Challenge" />
          )}
        </div>
      </div>
      <CodeEditor
        challenge={toEditorChallenge(challenge)}
        sessionId={sessionId}
        remainingSeconds={slot?.remaining_seconds}
        disabled={disabled || (slot?.submitted ?? false)}
        blockClipboard={blockClipboard}
        adaptiveMode={adaptiveMode}
        adaptiveGrading={adaptiveGrading}
        onSubmitted={onSubmitted}
        onAdaptiveSubmitted={onAdaptiveSubmitted}
        onSubmitCode={onSubmitCode}
        onRunComplete={onRunComplete}
      />
    </div>
  );
}
