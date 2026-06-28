"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import {
  AssessmentHubClient,
  readHubSessionId,
} from "@/features/assessment/AssessmentHubClient";

export default function AssessmentHubPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const search = useSearchParams();
  const assessmentId = params.token;
  const sessionId = readHubSessionId(search.get("session_id"));

  useEffect(() => {
    if (!sessionId) {
      router.replace(`/assessment/${assessmentId}/verify`);
    }
  }, [assessmentId, router, sessionId]);

  if (!sessionId) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-neutral/70">
        Loading session…
      </main>
    );
  }

  return <AssessmentHubClient assessmentId={assessmentId} sessionId={sessionId} />;
}
