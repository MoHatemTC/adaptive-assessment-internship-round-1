import { redirect } from "next/navigation";

interface AssessmentPageProps {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ session_id?: string }>;
}

export default async function AssessmentPage({
  params,
  searchParams,
}: AssessmentPageProps) {
  const { token } = await params;
  const query = await searchParams;
  const sessionId = query.session_id ?? crypto.randomUUID();
  redirect(`/assessment/${token}/verify?session_id=${encodeURIComponent(sessionId)}`);
}
