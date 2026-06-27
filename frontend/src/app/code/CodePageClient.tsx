"use client";

import { CodeChallengeView } from "@/features/code/CodeChallengeView";
import { SessionProctoringShell } from "@/features/proctoring";
import {
  readIdentityReference,
  readSessionAccessToken,
} from "@/lib/session-storage";

export interface CodePageClientProps {
  challengeId?: number;
  sessionId?: string;
  assessmentId?: string;
  enableProctoring?: boolean;
}

export function CodePageClient({
  challengeId,
  sessionId,
  assessmentId,
  enableProctoring = false,
}: CodePageClientProps) {
  const view = (
    <CodeChallengeView
      initialChallengeId={challengeId}
      initialSessionId={sessionId}
      assessmentId={assessmentId}
    />
  );

  if (!enableProctoring || !sessionId) {
    return view;
  }

  const referenceImageB64 = readIdentityReference();
  const accessToken = readSessionAccessToken();

  return (
    <SessionProctoringShell
      sessionId={sessionId}
      accessToken={accessToken ?? undefined}
      enabled
      consentGiven={Boolean(referenceImageB64)}
      referenceImageB64={referenceImageB64 ?? undefined}
    >
      {view}
    </SessionProctoringShell>
  );
}
