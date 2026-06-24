import { Suspense } from "react";

import { AssessmentCompleteClient } from "./AssessmentCompleteClient";

interface AssessmentCompletePageProps {
  params: Promise<{ token: string }>;
}

export default async function AssessmentCompletePage({
  params,
}: AssessmentCompletePageProps) {
  const { token } = await params;

  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-3xl px-4 py-8 text-sm text-neutral/70">
          Loading your report…
        </main>
      }
    >
      <AssessmentCompleteClient token={token} />
    </Suspense>
  );
}
