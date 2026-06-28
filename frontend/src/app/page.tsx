import Link from "next/link";

import { DEMO_ASSESSMENT_ID } from "@/lib/platform-session";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function fetchHealth(): Promise<{ status: string; db?: boolean; qdrant?: boolean }> {
  try {
    const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!response.ok) return { status: "error" };
    return (await response.json()) as { status: string; db?: boolean; qdrant?: boolean };
  } catch {
    return { status: "unreachable" };
  }
}

export default async function HomePage() {
  const health = await fetchHealth();
  const demoId = DEMO_ASSESSMENT_ID;
  const learnerStart = demoId
    ? `/assessment/${demoId}/verify`
    : "/demo";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center gap-8 px-4 py-12">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">
          Masaar Assessment Platform
        </p>
        <h1 className="text-3xl font-bold text-neutral">Adaptive assessments with integrity</h1>
        <p className="text-neutral/75">
          Verify identity, start a proctored session, then try coding, MCQ, voice, or diagram
          tools from one hub.
        </p>
      </header>

      <div className="rounded-xl border border-border bg-surface-muted p-4 text-sm">
        <p className="font-medium text-neutral">API health</p>
        <ul className="mt-2 space-y-1 text-neutral/70">
          <li>Status: {health.status}</li>
          {health.db != null && <li>Database: {health.db ? "connected" : "down"}</li>}
          {health.qdrant != null && <li>Qdrant: {health.qdrant ? "connected" : "down"}</li>}
        </ul>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link
          href={learnerStart}
          className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-60"
        >
          Start learner demo
        </Link>
        <Link
          href="/demo"
          className="rounded-lg border border-border px-5 py-2.5 text-sm font-medium text-neutral hover:bg-surface-muted"
        >
          Demo guide
        </Link>
        <Link
          href="/admin"
          className="rounded-lg border border-border px-5 py-2.5 text-sm font-medium text-neutral hover:bg-surface-muted"
        >
          Admin
        </Link>
      </div>

      {!demoId && (
        <p className="text-xs text-neutral/60">
          Set <code className="rounded bg-surface-muted px-1">NEXT_PUBLIC_DEMO_ASSESSMENT_ID</code>{" "}
          after running <code className="rounded bg-surface-muted px-1">seed_demo_assessment.py</code>.
        </p>
      )}
    </main>
  );
}
