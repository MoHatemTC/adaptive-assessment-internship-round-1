"use client";

import { useMemo } from "react";

import { useParams, useRouter, useSearchParams } from "next/navigation";

import { CodeChallengeView } from "@/features/code/CodeChallengeView";

export default function AssessmentChatPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const search = useSearchParams();

  const token = params.token;
  const sessionId = search.get("session_id") ?? undefined;
  const completeHref = useMemo(() => {
    if (!sessionId) return `/assessment/${token}/complete`;
    return `/assessment/${token}/complete?session_id=${encodeURIComponent(sessionId)}`;
  }, [sessionId, token]);

  return (
    <main className="min-h-screen bg-surface px-4 py-8">
      <CodeChallengeView
        initialSessionId={sessionId}
        assessmentId={token}
        enableProctoring
        onSessionComplete={({ reason }) => {
          if (reason === "adaptive") {
            router.push(completeHref);
          }
        }}
      />
    </main>
  );
}
