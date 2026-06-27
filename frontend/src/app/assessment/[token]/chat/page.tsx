"use client";

import { useMemo } from "react";

import { useParams, useRouter, useSearchParams } from "next/navigation";

import { CodeChallengeView } from "@/features/code/CodeChallengeView";
import { SessionProctoringShell } from "@/features/proctoring";
import {
  readIdentityReference,
  readSessionAccessToken,
} from "@/lib/session-storage";

export default function AssessmentChatPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const search = useSearchParams();

  const token = params.token;
  const sessionId = search.get("session_id") ?? undefined;
  const referenceImageB64 = useMemo(() => readIdentityReference(), []);
  const accessToken = useMemo(() => readSessionAccessToken(), []);
  const completeHref = useMemo(() => {
    if (!sessionId) return `/assessment/${token}/complete`;
    return `/assessment/${token}/complete?session_id=${encodeURIComponent(sessionId)}`;
  }, [sessionId, token]);

  const challenge = (
    <CodeChallengeView
      initialSessionId={sessionId}
      assessmentId={token}
      onSessionComplete={({ reason }) => {
        if (reason === "adaptive") {
          router.push(completeHref);
        }
      }}
    />
  );

  if (!sessionId) {
    return <main className="min-h-screen bg-surface px-4 py-8">{challenge}</main>;
  }

  return (
    <main className="min-h-screen bg-surface px-4 py-8">
      <SessionProctoringShell
        sessionId={sessionId}
        accessToken={accessToken ?? undefined}
        manageLifecycle={false}
        enabled
        consentGiven={Boolean(referenceImageB64)}
        referenceImageB64={referenceImageB64 ?? undefined}
      >
        {challenge}
      </SessionProctoringShell>
    </main>
  );
}
