import Link from "next/link";

import { DEMO_ASSESSMENT_ID } from "@/lib/platform-session";

export default function DemoGuidePage() {
  const assessmentId = DEMO_ASSESSMENT_ID;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold text-neutral">Demo walkthrough</h1>

      <ol className="list-decimal space-y-4 pl-5 text-sm text-neutral/80">
        <li>
          <strong className="text-neutral">Seed the demo assessment</strong> (once per Supabase):
          <pre className="mt-2 overflow-x-auto rounded-lg bg-neutral/5 p-3 text-xs">
            docker compose exec backend python scripts/seed_demo_assessment.py
          </pre>
          Copy the printed UUID into{" "}
          <code className="rounded bg-surface-muted px-1">NEXT_PUBLIC_DEMO_ASSESSMENT_ID</code>{" "}
          in <code className="rounded bg-surface-muted px-1">.env</code> and restart frontend.
        </li>
        <li>
          <strong className="text-neutral">Start the stack</strong>:
          <pre className="mt-2 rounded-lg bg-neutral/5 p-3 text-xs">
            docker compose up -d backend frontend redis
          </pre>
        </li>
        <li>
          <strong className="text-neutral">Learner flow</strong>: verify camera → sign-in →
          proctoring start → tool hub → pick a tool → finish on complete page (radar report).
        </li>
        <li>
          <strong className="text-neutral">Admin</strong>: create assessments at{" "}
          <Link href="/admin" className="text-primary underline">
            /admin
          </Link>
          .
        </li>
      </ol>

      {assessmentId ? (
        <Link
          href={`/assessment/${assessmentId}/verify`}
          className="inline-flex w-fit rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-60"
        >
          Open verify for demo assessment
        </Link>
      ) : (
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Demo assessment id not configured. Run the seed script and set{" "}
          <code>NEXT_PUBLIC_DEMO_ASSESSMENT_ID</code>.
        </p>
      )}

      <div className="border-t border-border pt-4 text-sm">
        <p className="font-medium text-neutral">Standalone tool pages (use platform session when set)</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral/70">
          <li>
            <Link href="/assessment/mcq" className="text-primary underline">
              /assessment/mcq
            </Link>
          </li>
          <li>
            <Link href="/assessment/voice" className="text-primary underline">
              /assessment/voice
            </Link>
          </li>
          <li>
            <Link href="/assessment/diagram" className="text-primary underline">
              /assessment/diagram
            </Link>
          </li>
          <li>
            <Link href="/code" className="text-primary underline">
              /code
            </Link>
          </li>
        </ul>
      </div>

      <Link href="/" className="text-sm text-primary underline">
        ← Back home
      </Link>
    </main>
  );
}
