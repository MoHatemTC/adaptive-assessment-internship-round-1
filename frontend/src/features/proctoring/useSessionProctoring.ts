"use client";

import { useEffect, useRef } from "react";

import { startSession } from "@/lib/session-api";
import {
  readSessionAccessToken,
  readSessionId,
} from "@/lib/session-storage";

import { useProctoring, type UseProctoringOptions } from "./useProctoring";

export interface UseSessionProctoringOptions
  extends Omit<UseProctoringOptions, "sessionId"> {
  sessionId?: string;
  accessToken?: string;
  /** Call platform session start/stop APIs (default true when token present). */
  manageLifecycle?: boolean;
}

/**
 * Platform-wide proctoring hook: optional session start/stop lifecycle plus
 * integrity monitoring (camera, mic, browser signals).
 */
export function useSessionProctoring({
  sessionId: sessionIdProp,
  accessToken: accessTokenProp,
  manageLifecycle = true,
  enabled = true,
  ...proctoringOptions
}: UseSessionProctoringOptions) {
  const sessionId = sessionIdProp ?? readSessionId() ?? "";
  const accessToken = accessTokenProp ?? readSessionAccessToken() ?? "";
  const lifecycleStartedRef = useRef(false);

  useEffect(() => {
    if (!manageLifecycle || !enabled || !sessionId || !accessToken) {
      return;
    }
    if (lifecycleStartedRef.current) {
      return;
    }
    lifecycleStartedRef.current = true;

    void startSession(sessionId, accessToken).catch(() => {
      lifecycleStartedRef.current = false;
    });

    return () => {
      lifecycleStartedRef.current = false;
    };
  }, [accessToken, enabled, manageLifecycle, sessionId]);

  const monitoring = useProctoring({
    ...proctoringOptions,
    sessionId,
    enabled: enabled && Boolean(sessionId),
  });

  return { sessionId, accessToken, ...monitoring };
}
