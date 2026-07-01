"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { NormalizedToolStep, ToolType } from "@/types/chat";
import { pollDiagramPendingQuestion } from "@/hooks/useQuestionTimer";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export interface DiagramNextQuestion {
  id: number;
  svg_content: string;
  prompt: string;
  difficulty: string;
  dimension?: string | null;
}

export interface DiagramDriverState {
  status: "loading" | "ready" | "submitting" | "error";
  currentPayload: DiagramNextQuestion | null;
  questionIndex: number;
  totalBudget: number;
  error: string | null;
  submit: (questionId: number, answerText: string, currentQuestionIndex: number) => Promise<NormalizedToolStep>;
}

export function useDiagramDriver(
  sessionId: string,
  totalQuestions: number,
): DiagramDriverState {
  const [question, setQuestion] = useState<DiagramNextQuestion | null>(null);
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
        const startRes = await fetch(`${API_BASE}/diagram/sessions/${sessionId}/start`, {
          method: "POST",
        });
        if (!startRes.ok) {
          const body = (await startRes.json().catch(() => ({}))) as { detail?: string };
          throw new Error(body.detail ?? "Failed to load diagram question");
        }
        const startData = (await startRes.json()) as {
          status: string;
          total_questions: number;
          question: DiagramNextQuestion | null;
        };
        setBudget(startData.total_questions);

        if (startData.status === "ready" && startData.question) {
          setQuestion(startData.question);
          return;
        }

        const pending = await pollDiagramPendingQuestion(API_BASE, sessionId);
        setQuestion(pending.question);
        setBudget(pending.total_questions);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load diagram");
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId]);

  const submit = useCallback(
    async (questionId: number, answerText: string, currentQuestionIndex: number): Promise<NormalizedToolStep> => {
      setSubmitting(true);
      setError(null);

      try {
        const res = await fetch(`${API_BASE}/diagram/sessions/${sessionId}/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question_id: questionId,
            answer_text: answerText,
            question_index: currentQuestionIndex,
            total_questions: budget,
          }),
        });

        if (!res.ok) throw new Error("Failed to submit answer");

        const data = (await res.json()) as {
          next_question: DiagramNextQuestion | null;
          is_complete: boolean;
          status?: string;
        };

        if (data.is_complete) {
          return {
            tool: "diagram" as ToolType,
            isToolComplete: true,
            nextPayload: null,
            transitionText: "Got it — next question…",
          };
        }

        if (data.status === "generating" || !data.next_question) {
          const pending = await pollDiagramPendingQuestion(API_BASE, sessionId);
          setQuestion(pending.question);
          setQuestionIndex((prev) => prev + 1);
          return {
            tool: "diagram" as ToolType,
            isToolComplete: false,
            nextPayload: pending.question,
            transitionText: "Got it — next question…",
          };
        }

        const nextQ = data.next_question;
        setQuestion(nextQ);
        setQuestionIndex((prev) => prev + 1);
        return {
          tool: "diagram" as ToolType,
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
      }
    },
    [sessionId, budget],
  );

  const status: DiagramDriverState["status"] = error
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
