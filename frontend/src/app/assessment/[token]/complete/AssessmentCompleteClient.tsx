"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { SessionRadarReportView } from "@/features/report/SessionRadarReportView";

export function AssessmentCompleteClient({ token }: { token: string }) {
  const search = useSearchParams();
  const sessionId = search.get("session_id");
  const accessToken =
    search.get("access_token") ??
    (typeof window !== "undefined"
      ? sessionStorage.getItem("masaar_session_token")
      : null);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-neutral">Assessment complete</h1>
        <p className="text-sm text-neutral/80">
          Thank you for completing your assessment. Your skill profile is below.
        </p>
      </header>

      {sessionId ? (
        <SessionRadarReportView
          sessionId={sessionId}
          accessToken={accessToken ?? undefined}
        />
      ) : (
        <p className="text-sm text-neutral/70">
          No session id provided — radar report unavailable.
        </p>
      )}

      <div className="flex gap-3 pt-2">
        <Link
          href={`/assessment/${token}`}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-neutral hover:bg-surface-muted"
        >
          Start again
        </Link>
        <Link
          href="/"
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60"
        >
          Back to home
        </Link>
      </div>
    </main>
  );
}
