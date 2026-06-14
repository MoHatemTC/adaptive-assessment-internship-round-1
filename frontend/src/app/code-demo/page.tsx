"use client";

import { useEffect, useState } from "react";

import { IntegrityMonitor } from "@/components/proctoring/IntegrityMonitor";
import { ProctoringGate } from "@/components/proctoring/ProctoringGate";
import { CodeTool } from "@/components/tools/CodeTool";
import { useSessionPoll } from "@/hooks/useSessionPoll";
import { startCodeSession } from "@/lib/api";

const DEMO_PROFILE = {
  name: "Demo User",
  skills: ["Python"],
  experience_level: "intermediate",
  preferred_domains: ["Programming"],
  learning_objectives: ["Try the E2B code editor with Run and Submit"],
};

export default function CodeDemoPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [secureReady, setSecureReady] = useState(false);
  const { session, setSession, refresh } = useSessionPoll(sessionId, Boolean(sessionId));
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    startCodeSession(DEMO_PROFILE)
      .then((result) => {
        setSessionId(result.session_id);
        setSession(result);
      })
      .catch((err: Error) => {
        setError(err.message || "Could not start demo session.");
      })
      .finally(() => setLoading(false));
  }, [setSession]);

  const challenge = session?.challenges[0] ?? null;

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <h1 className="text-2xl font-bold text-neutral">Code Editor Demo</h1>
      <p className="text-sm text-neutral/70">
        Timed session with proctoring, Run (visible tests), and Submit (full grading).
      </p>

      {loading && <p className="text-sm text-neutral/60">Starting demo session…</p>}

      {error && (
        <div className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">
          {error}
        </div>
      )}

      {session && !secureReady && sessionId && (
        <ProctoringGate sessionId={sessionId} onReady={() => setSecureReady(true)} />
      )}

      {session && challenge && secureReady && (
        <>
          <IntegrityMonitor sessionId={session.session_id} enabled={session.status === "active"} />
          <p className="text-xs text-neutral/50">Session: {session.session_id}</p>
          <CodeTool
            sessionId={session.session_id}
            challenge={challenge}
            sessionRemainingSeconds={session.total_remaining_seconds}
            disabled={challenge.submitted || session.status !== "active"}
            blockClipboard
            onRunComplete={() => void refresh()}
          />
        </>
      )}
    </main>
  );
}
