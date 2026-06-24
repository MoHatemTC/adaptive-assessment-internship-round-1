import { AssessmentVerifyClient } from "@/features/assessment/AssessmentVerifyClient";

interface AssessmentVerifyPageProps {
  params: Promise<{ token: string }>;
}

export default async function AssessmentVerifyPage({
  params,
}: AssessmentVerifyPageProps) {
  const { token } = await params;
  return <AssessmentVerifyClient assessmentId={token} />;
}
