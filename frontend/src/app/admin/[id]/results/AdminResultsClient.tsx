"use client";

import { useParams, useSearchParams } from "next/navigation";

import { SessionRadarReportView } from "@/features/report/SessionRadarReportView";

export function AdminResultsClient() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const sessionId = search.get("session_id");

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold text-neutral">Assessment results</h1>
        <p className="mt-1 text-sm text-neutral/70">
          Assessment {params.id}
          {sessionId ? ` · Session ${sessionId}` : ""}
        </p>
      </header>

      {sessionId ? (
        <SessionRadarReportView
          sessionId={sessionId}
          title="Candidate skill profile"
        />
      ) : (
        <p className="text-sm text-neutral/70">
          Open this page with{" "}
          <code className="rounded bg-surface-muted px-1">?session_id=&lt;uuid&gt;</code>{" "}
          to view the radar report.
        </p>
      )}
    </main>
  );
}
