"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SessionRadarReportView } from "@/features/report/SessionRadarReportView";
import {
  getSessionIntegritySummary,
  type SessionIntegritySnapshot,
} from "@/lib/admin-api";
import { listAssessmentSessions } from "@/lib/session-api";

interface SessionListItem {
  id: string;
  status: string;
  created_at: string;
  learner_name: string;
}

function IntegrityPanel({ snapshot }: { snapshot: SessionIntegritySnapshot }) {
  return (
    <section className="rounded-xl border border-border bg-white p-4">
      <h2 className="text-sm font-semibold text-neutral">Integrity summary</h2>
      <dl className="mt-3 grid gap-2 text-sm text-neutral/80 sm:grid-cols-2">
        <div>
          <dt className="text-neutral/60">Verification</dt>
          <dd className="capitalize">{snapshot.verification_status.replace(/_/g, " ")}</dd>
        </div>
        <div>
          <dt className="text-neutral/60">Identity verified</dt>
          <dd>{snapshot.identity_verified ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt className="text-neutral/60">High-severity events</dt>
          <dd>
            {snapshot.high_severity_count} / {snapshot.threshold}
          </dd>
        </div>
      </dl>
    </section>
  );
}

export function AdminResultsClient() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const sessionId = search.get("session_id");
  const adminToken =
    typeof window !== "undefined" ? localStorage.getItem("masaar_admin_token") : null;

  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [integrity, setIntegrity] = useState<SessionIntegritySnapshot | null>(null);
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

  useEffect(() => {
    if (!sessionId || !adminToken) return;
    let cancelled = false;
    getSessionIntegritySummary(sessionId)
      .then((snapshot) => {
        if (!cancelled) setIntegrity(snapshot);
      })
      .catch(() => {
        if (!cancelled) setIntegrity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, adminToken]);

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
        <div className="space-y-6">
          {integrity ? <IntegrityPanel snapshot={integrity} /> : null}
          <SessionRadarReportView
            sessionId={sessionId}
            title="Candidate skill profile"
            accessToken={adminToken ?? undefined}
          />
        </div>
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
