"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getCodeSession, type SessionRead } from "@/lib/api";

const POLL_INTERVAL_MS = 15_000;

export function useSessionPoll(sessionId: string | null, enabled = true) {
  const [session, setSession] = useState<SessionRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) return null;
    try {
      const data = await getCodeSession(sessionId);
      setSession(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh session");
      return null;
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || !enabled) {
      setSession(null);
      return;
    }

    void refresh();
    timerRef.current = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);

    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
      }
    };
  }, [sessionId, enabled, refresh]);

  return { session, setSession, refresh, error };
}
