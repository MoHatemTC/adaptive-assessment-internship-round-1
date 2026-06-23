import { CodeChallengeView } from "@/features/code/CodeChallengeView";

interface CodePageProps {
  searchParams: Promise<{
    challenge_id?: string;
    session_id?: string;
    assessment_id?: string;
  }>;
}

export default async function CodePage({ searchParams }: CodePageProps) {
  const params = await searchParams;
  const challengeId = params.challenge_id
    ? Number.parseInt(params.challenge_id, 10)
    : undefined;

  return (
    <CodeChallengeView
      mode="standalone"
      sessionId={params.session_id}
      assessmentId={params.assessment_id}
      initialChallengeId={
        challengeId != null && !Number.isNaN(challengeId)
          ? challengeId
          : undefined
      }
    />
  );
}
