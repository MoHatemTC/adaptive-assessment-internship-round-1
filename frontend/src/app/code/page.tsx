import { CodePageClient } from "./CodePageClient";

interface CodePageProps {
  searchParams: Promise<{
    challenge_id?: string;
    session_id?: string;
    assessment_id?: string;
    proctoring?: string;
  }>;
}

export default async function CodePage({ searchParams }: CodePageProps) {
  const params = await searchParams;
  const challengeId = params.challenge_id
    ? Number.parseInt(params.challenge_id, 10)
    : undefined;

  return (
    <main className="min-h-screen bg-surface px-4 py-8">
      <CodePageClient
        challengeId={
          challengeId != null && !Number.isNaN(challengeId)
            ? challengeId
            : undefined
        }
        sessionId={params.session_id}
        assessmentId={params.assessment_id}
        enableProctoring={params.proctoring === "1"}
      />
    </main>
  );
}
