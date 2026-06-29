"use client";

import { useEffect, useRef, useState } from "react";

/** Countdown that starts only when ``armed`` and pauses while ``paused``. */
export function useQuestionTimer(
  totalSeconds: number | undefined,
  resetKey: string | number,
  options?: {
    enabled?: boolean;
    armed?: boolean;
    paused?: boolean;
    onExpired?: () => void;
  },
): { secondsRemaining: number | null; expired: boolean } {
  const enabled = options?.enabled !== false && (totalSeconds ?? 0) > 0;
  const armed = options?.armed !== false;
  const paused = options?.paused === true;
  const running = enabled && armed && !paused;
  const onExpired = options?.onExpired;
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(
    running ? totalSeconds! : null,
  );
  const [expired, setExpired] = useState(false);
  const firedRef = useRef(false);
  const onExpiredRef = useRef(onExpired);
  onExpiredRef.current = onExpired;

  useEffect(() => {
    firedRef.current = false;
    setExpired(false);
    if (!running || totalSeconds == null) {
      setSecondsRemaining(null);
      return;
    }
    setSecondsRemaining(totalSeconds);

    const timer = window.setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev == null) return prev;
        if (prev <= 1) {
          window.clearInterval(timer);
          if (!firedRef.current) {
            firedRef.current = true;
            setExpired(true);
            onExpiredRef.current?.();
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => window.clearInterval(timer);
  }, [running, resetKey, totalSeconds]);

  return { secondsRemaining: running ? secondsRemaining : null, expired };
}

export function formatQuestionTimer(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** Poll an MCQ pending-question endpoint until ready or timeout. */
export async function pollMcqPendingQuestion(
  apiBase: string,
  sessionId: string,
  options?: { intervalMs?: number; maxAttempts?: number },
): Promise<{
  question: {
    id: number;
    question_text: string;
    options: { label: string; text: string }[];
  };
  total_questions: number;
}> {
  const intervalMs = options?.intervalMs ?? 500;
  const maxAttempts = options?.maxAttempts ?? 180;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const response = await fetch(
      `${apiBase}/mcq/sessions/${sessionId}/pending-question`,
    );
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(body.detail ?? "Failed to load question");
    }
    const data = (await response.json()) as {
      status: string;
      total_questions: number;
      error?: string | null;
      question: {
        id: number;
        question_text: string;
        options: { label: string; text: string }[];
      } | null;
    };
    if (data.status === "failed") {
      throw new Error(data.error ?? "Failed to generate the next question");
    }
    if (data.status === "ready" && data.question) {
      return { question: data.question, total_questions: data.total_questions };
    }
    await sleep(intervalMs);
  }
  throw new Error("Timed out waiting for the next question");
}

export async function pollDiagramPendingQuestion(
  apiBase: string,
  sessionId: string,
  options?: { intervalMs?: number; maxAttempts?: number },
): Promise<{
  question: {
    id: number;
    svg_content: string;
    prompt: string;
    difficulty: string;
    dimension?: string | null;
  };
  total_questions: number;
}> {
  const intervalMs = options?.intervalMs ?? 500;
  const maxAttempts = options?.maxAttempts ?? 180;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const response = await fetch(
      `${apiBase}/diagram/sessions/${sessionId}/pending-question`,
    );
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(body.detail ?? "Failed to load diagram question");
    }
    const data = (await response.json()) as {
      status: string;
      total_questions: number;
      error?: string | null;
      question: {
        id: number;
        svg_content: string;
        prompt: string;
        difficulty: string;
        dimension?: string | null;
      } | null;
    };
    if (data.status === "failed") {
      throw new Error(data.error ?? "Failed to generate the next diagram question");
    }
    if (data.status === "ready" && data.question) {
      return { question: data.question, total_questions: data.total_questions };
    }
    await sleep(intervalMs);
  }
  throw new Error("Timed out waiting for the next diagram question");
}
