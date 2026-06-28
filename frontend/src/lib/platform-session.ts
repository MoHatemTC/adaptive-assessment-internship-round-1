import { readSessionId } from "@/lib/session-storage";

/** Platform session UUID from verify flow, or a local fallback for standalone tool demos. */
export function resolvePlatformSessionId(fallback?: string): string {
  const stored = readSessionId();
  if (stored) return stored;
  return fallback ?? crypto.randomUUID();
}

export const DEMO_ASSESSMENT_ID =
  process.env.NEXT_PUBLIC_DEMO_ASSESSMENT_ID?.trim() || "";
