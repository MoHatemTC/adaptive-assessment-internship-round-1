import Link from "next/link";

interface AssessmentVerifyPageProps {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ session_id?: string }>;
}

export default async function AssessmentVerifyPage({
  params,
  searchParams,
}: AssessmentVerifyPageProps) {
  const { token } = await params;
  const query = await searchParams;
  const sessionId = query.session_id ?? crypto.randomUUID();
  const chatHref = `/assessment/${token}/chat?session_id=${encodeURIComponent(sessionId)}`;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-6 px-4 py-8">
      <h1 className="text-2xl font-semibold text-neutral">Pre-assessment checks</h1>
      <div className="rounded-xl border border-border bg-surface-muted p-5 text-sm text-neutral/80">
        <p className="mb-3">
          Camera, microphone, tab-focus, and copy/paste monitoring are enabled during
          this assessment.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Allow camera and microphone access.</li>
          <li>Stay on this tab and keep fullscreen if requested.</li>
          <li>Avoid copy/paste and external AI tools during the test.</li>
        </ul>
      </div>
      <div className="flex gap-3">
        <Link
          href={chatHref}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60"
        >
          Continue to assessment
        </Link>
        <Link
          href="/code"
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-neutral hover:bg-surface-muted"
        >
          Open standalone demo
        </Link>
      </div>
    </main>
  );
}
