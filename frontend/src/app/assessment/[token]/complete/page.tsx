import Link from "next/link";

interface AssessmentCompletePageProps {
  params: Promise<{ token: string }>;
}

export default async function AssessmentCompletePage({
  params,
}: AssessmentCompletePageProps) {
  const { token } = await params;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-4 px-4 py-8">
      <h1 className="text-2xl font-semibold text-neutral">Assessment complete</h1>
      <p className="text-sm text-neutral/80">
        Your responses and integrity events were recorded successfully.
      </p>
      <div className="flex gap-3">
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
