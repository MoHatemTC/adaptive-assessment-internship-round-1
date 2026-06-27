"use client";

import type { ReactNode } from "react";

import { SessionProctoringShell } from "@/features/proctoring";
import {
  readIdentityReference,
  readSessionAccessToken,
  readSessionId,
} from "@/lib/session-storage";

/** Wraps tool demo pages when a platform session exists in browser storage. */
export function PlatformSessionProctoring({ children }: { children: ReactNode }) {
  const sessionId = readSessionId();
  const accessToken = readSessionAccessToken();
  const referenceImageB64 = readIdentityReference();

  if (!sessionId || !accessToken) {
    return <>{children}</>;
  }

  return (
    <SessionProctoringShell
      sessionId={sessionId}
      accessToken={accessToken}
      manageLifecycle={false}
      enabled
      consentGiven={Boolean(referenceImageB64)}
      referenceImageB64={referenceImageB64 ?? undefined}
    >
      {children}
    </SessionProctoringShell>
  );
}
