import { CodeChallengeView } from "@/features/code/CodeChallengeView";

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
  const enableProctoring = params.proctoring === "1";

  return (
    <main className="min-h-screen bg-surface px-4 py-8">
      <CodeChallengeView
        initialChallengeId={
          challengeId != null && !Number.isNaN(challengeId)
            ? challengeId
            : undefined
        }
        initialSessionId={params.session_id}
        assessmentId={params.assessment_id}
        enableProctoring={enableProctoring}
      />
    </main>
  );
}
