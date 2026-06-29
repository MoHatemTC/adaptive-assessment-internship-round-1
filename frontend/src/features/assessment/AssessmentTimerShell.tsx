"use client";

import { useEffect, useMemo, useState } from "react";

import { formatQuestionTimer } from "@/hooks/useQuestionTimer";
import { getMySession } from "@/lib/session-api";

export interface AssessmentTimerShellProps {
  sessionId: string;
  accessToken: string;
  questionSecondsRemaining?: number | null;
  questionLabel?: string;
  paused?: boolean;
}

function parseDeadline(profile: Record<string, unknown>): number | null {
  const limits = profile._session_limits;
  if (!limits || typeof limits !== "object") return null;
  const raw = (limits as Record<string, unknown>).session_deadline_at;
  if (typeof raw !== "string") return null;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? null : ms;
}

export function AssessmentTimerShell({
  sessionId,
  accessToken,
  questionSecondsRemaining,
  questionLabel = "Question",
  paused = false,
}: AssessmentTimerShellProps) {
  const [deadlineMs, setDeadlineMs] = useState<number | null>(null);
  const [sessionSeconds, setSessionSeconds] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMySession(accessToken)
      .then((session) => {
        if (cancelled) return;
        setDeadlineMs(parseDeadline(session.learner_profile));
      })
      .catch(() => {
        if (!cancelled) setDeadlineMs(null);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, sessionId]);

  useEffect(() => {
    if (!deadlineMs || paused) {
      return;
    }
    const tick = () => {
      const remaining = Math.max(0, Math.floor((deadlineMs - Date.now()) / 1000));
      setSessionSeconds(remaining);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [deadlineMs, paused]);

  const showSession = sessionSeconds !== null;
  const showQuestion =
    questionSecondsRemaining !== null && questionSecondsRemaining !== undefined;

  const sessionExpired = showSession && sessionSeconds === 0;

  const banner = useMemo(() => {
    if (sessionExpired) {
      return "Session time has expired.";
    }
    return null;
  }, [sessionExpired]);

  if (!showSession && !showQuestion) return null;

  return (
    <div className="mx-auto mb-4 flex w-full max-w-2xl flex-wrap items-center justify-between gap-2 rounded-xl border border-[#D8DDF0] bg-white px-4 py-2 text-sm text-[#1F2430]">
      {showSession ? (
        <span className={sessionExpired ? "font-semibold text-[#E5484D]" : ""}>
          Session {formatQuestionTimer(sessionSeconds ?? 0)}
        </span>
      ) : (
        <span />
      )}
      {showQuestion ? (
        <span>
          {questionLabel}{" "}
          {formatQuestionTimer(questionSecondsRemaining ?? 0)}
        </span>
      ) : null}
      {banner ? (
        <span className="w-full text-xs font-medium text-[#E5484D]">{banner}</span>
      ) : null}
    </div>
  );
}
