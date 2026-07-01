"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { NormalizedToolStep, ToolType } from "@/types/chat";
import { pollMcqPendingQuestion } from "@/hooks/useQuestionTimer";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

interface McqQuestion {
  id: number;
  question_text: string;
  options: { label: string; text: string }[];
}

export interface McqDriverState {
  status: "loading" | "ready" | "submitting" | "error";
  currentPayload: McqQuestion | null;
  questionIndex: number;
  totalBudget: number;
  error: string | null;
  submit: (questionId: number, selectedLabel: string) => Promise<NormalizedToolStep>;
}

export function useMcqDriver(
  sessionId: string,
  totalQuestions: number,
): McqDriverState {
  const [question, setQuestion] = useState<McqQuestion | null>(null);
  const [budget, setBudget] = useState(totalQuestions);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seeded = useRef(false);

  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    (async () => {
      try {
        const startRes = await fetch(`${API_BASE}/mcq/sessions/${sessionId}/start`, {
          method: "POST",
        });
        if (!startRes.ok) {
          const body = (await startRes.json().catch(() => ({}))) as { detail?: string };
          throw new Error(body.detail ?? "Failed to load MCQ");
        }
        const startData = (await startRes.json()) as {
          status: string;
          total_questions: number;
          question: McqQuestion | null;
        };
        setBudget(startData.total_questions);

        if (startData.status === "ready" && startData.question) {
          setQuestion(startData.question);
          return;
        }

        const pending = await pollMcqPendingQuestion(API_BASE, sessionId);
        setQuestion(pending.question);
        setBudget(pending.total_questions);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load MCQ");
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId]);

  const submit = useCallback(
    async (questionId: number, selectedLabel: string): Promise<NormalizedToolStep> => {
      setSubmitting(true);
      setError(null);

      try {
        const res = await fetch(`${API_BASE}/mcq/sessions/${sessionId}/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question_id: questionId,
            selected_option: selectedLabel,
            question_index: questionIndex,
          }),
        });

        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(body.detail ?? "Failed to submit answer");
        }

        const data = (await res.json()) as {
          next_question: McqQuestion | null;
          is_complete: boolean;
          status?: string;
        };

        if (data.is_complete) {
          return {
            tool: "mcq" as ToolType,
            isToolComplete: true,
            nextPayload: null,
            transitionText: "Got it — next question…",
          };
        }

        if (data.status === "generating" || !data.next_question) {
          setLoading(true);
          const pending = await pollMcqPendingQuestion(API_BASE, sessionId);
          const nextQ = pending.question;
          setQuestion(nextQ);
          setBudget(pending.total_questions);
          setQuestionIndex((prev) => prev + 1);
          return {
            tool: "mcq" as ToolType,
            isToolComplete: false,
            nextPayload: nextQ,
            transitionText: "Got it — next question…",
          };
        }

        if (questionIndex + 1 >= budget) {
          return {
            tool: "mcq" as ToolType,
            isToolComplete: true,
            nextPayload: null,
            transitionText: "Got it — next question…",
          };
        }

        const nextQ = data.next_question;
        setQuestion(nextQ);
        setQuestionIndex((prev) => prev + 1);
        return {
          tool: "mcq" as ToolType,
          isToolComplete: false,
          nextPayload: nextQ,
          transitionText: "Got it — next question…",
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Submit failed";
        setError(msg);
        throw err;
      } finally {
        setSubmitting(false);
        setLoading(false);
      }
    },
    [sessionId, questionIndex, budget],
  );

  const status: McqDriverState["status"] = error
    ? "error"
    : submitting
      ? "submitting"
      : loading
        ? "loading"
        : "ready";

  return {
    status,
    currentPayload: question,
    questionIndex,
    totalBudget: budget,
    error,
    submit,
  };
}
