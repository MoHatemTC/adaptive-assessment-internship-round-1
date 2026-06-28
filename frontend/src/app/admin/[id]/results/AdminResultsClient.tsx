"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SessionRadarReportView } from "@/features/report/SessionRadarReportView";
import { listAssessmentSessions } from "@/lib/session-api";

interface SessionListItem {
  id: string;
  status: string;
  created_at: string;
  learner_name: string;
}

export function AdminResultsClient() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const sessionId = search.get("session_id");
  const adminToken =
    typeof window !== "undefined" ? localStorage.getItem("masaar_admin_token") : null;

  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionId || !adminToken) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listAssessmentSessions(params.id, adminToken)
      .then((loaded) => {
        if (!cancelled) setSessions(loaded);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load sessions");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, adminToken, params.id]);

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
          accessToken={adminToken ?? undefined}
        />
      ) : loading ? (
        <p className="text-sm text-neutral/70">Loading sessions…</p>
      ) : error ? (
        <p className="rounded-lg border border-error/30 bg-error/5 p-3 text-sm text-error">
          {error}
        </p>
      ) : sessions.length === 0 ? (
        <p className="text-sm text-neutral/70">
          No completed sessions yet for this assessment.
        </p>
      ) : (
        <ul className="space-y-2">
          {sessions.map((session) => (
            <li
              key={session.id}
              className="flex items-center justify-between rounded-lg border border-border bg-white px-4 py-3"
            >
              <div>
                <p className="text-sm font-medium text-neutral">
                  {session.learner_name}
                </p>
                <p className="text-xs text-neutral/60">
                  Completed {new Date(session.created_at).toLocaleString()}
                </p>
              </div>
              <Link
                href={`/admin/${params.id}/results?session_id=${encodeURIComponent(session.id)}`}
                className="rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-primary-60"
              >
                View Report
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
