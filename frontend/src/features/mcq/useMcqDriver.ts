"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { SubmitResult, ToolType, UserAnswerMessage } from "@/types/chat";
import { pollMcqPendingQuestion } from "@/hooks/useQuestionTimer";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export interface McqQuestion {
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
  submit: (questionId: number, selectedLabel: string) => Promise<SubmitResult>;
}

export interface McqDriverOptions {
  initialPayload?: McqQuestion | null;
  initialQuestionIndex?: number;
  skipBootstrap?: boolean;
}

export function useMcqDriver(
  sessionId: string,
  totalQuestions: number,
  options?: McqDriverOptions,
): McqDriverState {
  const {
    initialPayload = null,
    initialQuestionIndex = 0,
    skipBootstrap = false,
  } = options ?? {};

  const [question, setQuestion] = useState<McqQuestion | null>(initialPayload);
  const [budget, setBudget] = useState(totalQuestions);
  const [questionIndex, setQuestionIndex] = useState(initialQuestionIndex);
  const [loading, setLoading] = useState(!skipBootstrap && !initialPayload);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seeded = useRef(false);

  useEffect(() => {
    if (skipBootstrap) {
      setLoading(false);
      return;
    }
    if (initialPayload) {
      setQuestion(initialPayload);
      setQuestionIndex(initialQuestionIndex);
      setLoading(false);
      return;
    }
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
  }, [sessionId, skipBootstrap, initialPayload, initialQuestionIndex]);

  const submit = useCallback(
    async (questionId: number, selectedLabel: string): Promise<SubmitResult> => {
      setSubmitting(true);
      setError(null);

      const answerMessage: UserAnswerMessage = {
        id: `ans-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        kind: "user_answer",
        role: "user",
        createdAt: Date.now(),
        tool: "mcq",
        summary: `Selected: ${selectedLabel}`,
      };

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
            answerMessage,
            step: {
              tool: "mcq" as ToolType,
              isToolComplete: true,
              nextPayload: null,
              transitionText: "Got it — next question…",
            },
          };
        }

        if (data.status === "generating" || !data.next_question) {
          setLoading(true);
          const pending = await pollMcqPendingQuestion(API_BASE, sessionId);
          const nextQ = pending.question;
          const nextIndex = questionIndex + 1;
          setQuestion(nextQ);
          setBudget(pending.total_questions);
          setQuestionIndex(nextIndex);
          return {
            answerMessage,
            step: {
              tool: "mcq" as ToolType,
              isToolComplete: false,
              nextPayload: nextQ,
              nextQuestionIndex: nextIndex,
              transitionText: "Got it — next question…",
            },
          };
        }

        if (questionIndex + 1 >= budget) {
          return {
            answerMessage,
            step: {
              tool: "mcq" as ToolType,
              isToolComplete: true,
              nextPayload: null,
              transitionText: "Got it — next question…",
            },
          };
        }

        const nextQ = data.next_question;
        const nextIndex = questionIndex + 1;
        setQuestion(nextQ);
        setQuestionIndex(nextIndex);
        return {
          answerMessage,
          step: {
            tool: "mcq" as ToolType,
            isToolComplete: false,
            nextPayload: nextQ,
            nextQuestionIndex: nextIndex,
            transitionText: "Got it — next question…",
          },
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
