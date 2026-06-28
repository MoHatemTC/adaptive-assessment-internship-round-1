"use client";

import Link from "next/link";

import { SessionProctoringShell } from "@/features/proctoring";
import {
  readIdentityReference,
  readSessionAccessToken,
  readSessionId,
} from "@/lib/session-storage";

export interface AssessmentHubClientProps {
  assessmentId: string;
  sessionId: string;
}

const TOOLS = [
  {
    id: "coding",
    title: "Coding challenge",
    description: "Adaptive code loop with sandbox grading and integrity monitoring.",
    href: (assessmentId: string, sessionId: string) =>
      `/assessment/${assessmentId}/chat?session_id=${encodeURIComponent(sessionId)}`,
  },
  {
    id: "code-standalone",
    title: "Coding (standalone)",
    description: "Same coding UI at /code with proctoring enabled.",
    href: (assessmentId: string, sessionId: string) =>
      `/code?session_id=${encodeURIComponent(sessionId)}&assessment_id=${encodeURIComponent(assessmentId)}&proctoring=1`,
  },
  {
    id: "mcq",
    title: "MCQ adaptive loop",
    description: "Multiple-choice questions with silent grading.",
    href: () => "/assessment/mcq",
  },
  {
    id: "voice",
    title: "Voice interview",
    description: "Spoken responses with transcription and rubric grading.",
    href: () => "/assessment/voice",
  },
  {
    id: "diagram",
    title: "Diagram analysis",
    description: "SVG diagram questions with adaptive difficulty.",
    href: () => "/assessment/diagram",
  },
] as const;

export function AssessmentHubClient({
  assessmentId,
  sessionId,
}: AssessmentHubClientProps) {
  const accessToken = readSessionAccessToken();
  const referenceImageB64 = readIdentityReference();
  const completeHref = `/assessment/${assessmentId}/complete?session_id=${encodeURIComponent(sessionId)}`;

  const hub = (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 px-4 py-10">
      <header className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Session active
        </p>
        <h1 className="text-2xl font-semibold text-neutral">Choose an assessment tool</h1>
        <p className="text-sm text-neutral/75">
          Proctoring is active for this session. Pick any tool below — integrity
          monitoring continues across tools using the same session id.
        </p>
        <p className="font-mono text-xs text-neutral/50">
          session: {sessionId.slice(0, 8)}…
        </p>
      </header>

      <ul className="grid gap-4 sm:grid-cols-2">
        {TOOLS.map((tool) => (
          <li key={tool.id}>
            <Link
              href={tool.href(assessmentId, sessionId)}
              className="flex h-full flex-col rounded-xl border border-border bg-white p-5 shadow-sm transition hover:border-primary/40 hover:shadow-md"
            >
              <h2 className="font-semibold text-neutral">{tool.title}</h2>
              <p className="mt-2 flex-1 text-sm text-neutral/70">{tool.description}</p>
              <span className="mt-4 text-sm font-medium text-primary">Open →</span>
            </Link>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-3 border-t border-border pt-6">
        <Link
          href={completeHref}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-60"
        >
          Finish assessment
        </Link>
        <Link
          href={`/assessment/${assessmentId}/verify`}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-neutral hover:bg-surface-muted"
        >
          Re-verify
        </Link>
      </div>
    </main>
  );

  if (!accessToken) {
    return hub;
  }

  return (
    <SessionProctoringShell
      sessionId={sessionId}
      accessToken={accessToken}
      manageLifecycle={false}
      enabled
      consentGiven={Boolean(referenceImageB64)}
      referenceImageB64={referenceImageB64 ?? undefined}
    >
      {hub}
    </SessionProctoringShell>
  );
}

/** Redirect helper when session id missing from URL but present in storage. */
export function readHubSessionId(searchSessionId: string | null): string | null {
  return searchSessionId ?? readSessionId();
}
