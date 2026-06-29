"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useParams, useRouter, useSearchParams } from "next/navigation";

import { AssessmentTimerShell } from "@/features/assessment/AssessmentTimerShell";
import { CodeChallengeView } from "@/features/code/CodeChallengeView";
import DiagramTool, {
  type DiagramNextQuestion,
} from "@/features/diagram/DiagramTool";
import { SessionProctoringShell } from "@/features/proctoring";
import AdaptiveVoiceSession from "@/features/voice/AdaptiveVoiceSession";
import McqCard, { McqOption } from "@/features/mcq/McqCard";
import {
  formatQuestionTimer,
  pollDiagramPendingQuestion,
  pollMcqPendingQuestion,
  useQuestionTimer,
} from "@/hooks/useQuestionTimer";
import {
  NextToolInfo,
  completeSession,
  submitResponse,
} from "@/lib/session-api";
import { readIdentityReference, readSessionAuth } from "@/lib/session-storage";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export default function AssessmentChatPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const search = useSearchParams();

  const token = params.token;
  const referenceImageB64 = useMemo(() => readIdentityReference(), []);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [currentTool, setCurrentTool] = useState<string | null>(null);
  const [toolInfo, setToolInfo] = useState<NextToolInfo | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toolLoading, setToolLoading] = useState(false);
  const started = useRef(false);

  const completeHref = useMemo(() => {
    const sid = sessionId ?? search.get("session_id");
    return sid
      ? `/assessment/${token}/complete?session_id=${encodeURIComponent(sid)}`
      : `/assessment/${token}/complete`;
  }, [sessionId, search, token]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const stored = readSessionAuth();
    const sid = search.get("session_id") ?? stored.sessionId;
    const tok = stored.token;
    if (!sid || !tok) {
      setError("Missing session credentials. Please restart the assessment.");
      return;
    }
    setSessionId(sid);
    setAccessToken(tok);

    submitResponse(sid, "", "start", tok)
      .then((res) => {
        setCurrentTool(res.current_tool);
        setToolInfo(res.next_tool_info);
        setIsComplete(res.is_complete);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not start"),
      );
  }, [search]);

  const advance = useCallback(
    (tool: string) => {
      if (!sessionId || !accessToken) return;
      submitResponse(sessionId, tool, "complete_tool", accessToken)
        .then(async (res) => {
          setCurrentTool(res.current_tool);
          setToolInfo(res.next_tool_info);
          setIsComplete(res.is_complete);
          if (res.is_complete) {
            try {
              await completeSession(sessionId, accessToken);
            } catch (err) {
              console.warn("Failed to mark session complete", err);
            }
            router.push(completeHref);
          }
        })
        .catch((err) =>
          setError(err instanceof Error ? err.message : "Could not advance"),
        );
    },
    [sessionId, accessToken, router, completeHref],
  );

  useEffect(() => {
    if (!isComplete || !sessionId || !accessToken) return;
    (async () => {
      try {
        await completeSession(sessionId, accessToken);
      } catch (err) {
        console.warn("Failed to mark session complete", err);
      }
      router.push(completeHref);
    })();
  }, [isComplete, sessionId, accessToken, completeHref, router]);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface px-4">
        <p className="rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-4 text-sm text-[#E5484D]">
          {error}
        </p>
      </main>
    );
  }

  if (!currentTool || !sessionId || !accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface px-4">
        <p className="text-sm text-[#1F2430]/70">Preparing your assessment…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-surface px-4 py-8">
      <SessionProctoringShell
        sessionId={sessionId}
        accessToken={accessToken}
        manageLifecycle={false}
        enabled
        consentGiven={Boolean(referenceImageB64)}
        referenceImageB64={referenceImageB64 ?? undefined}
      >
        <AssessmentTimerShell
          sessionId={sessionId}
          accessToken={accessToken}
          paused={toolLoading}
        />

        <div className="mx-auto mb-6 w-full max-w-2xl">
          <p className="text-sm font-medium capitalize text-[#1F2430]">
            {currentTool} section
          </p>
        </div>

        {currentTool === "code" && (
          <CodeChallengeView
            initialSessionId={sessionId}
            assessmentId={token}
            maxQuestions={toolInfo?.total_for_tool}
            questionTimeLimitSeconds={toolInfo?.time_limit_seconds ?? 600}
            onSessionComplete={() => advance("code")}
          />
        )}

        {currentTool === "voice" && (
          <AdaptiveVoiceSession
            sessionId={sessionId}
            initialQuestion="Tell me about a recent technical challenge you faced and how you solved it."
            initialDifficulty={
              (toolInfo?.difficulty as "beginner" | "intermediate" | "advanced") ??
              "beginner"
            }
            learnerProfile={{}}
            adminConfig={{
              max_difficulty: "advanced",
              max_questions: toolInfo?.total_for_tool ?? 10,
            }}
            onComplete={() => advance("voice")}
          />
        )}

        {currentTool === "mcq" && (
          <ChatMcqRunner
            sessionId={sessionId}
            totalQuestions={toolInfo?.total_for_tool ?? 1}
            timeLimitSeconds={toolInfo?.time_limit_seconds ?? undefined}
            onLoadingChange={setToolLoading}
            onComplete={() => advance("mcq")}
          />
        )}

        {currentTool === "diagram" && (
          <ChatDiagramRunner
            sessionId={sessionId}
            totalQuestions={toolInfo?.total_for_tool ?? 1}
            timeLimitSeconds={toolInfo?.time_limit_seconds ?? undefined}
            onLoadingChange={setToolLoading}
            onComplete={() => advance("diagram")}
          />
        )}
      </SessionProctoringShell>
    </main>
  );
}

interface McqQuestion {
  id: number;
  question_text: string;
  options: McqOption[];
}

function ChatMcqRunner({
  sessionId,
  totalQuestions,
  timeLimitSeconds,
  onLoadingChange,
  onComplete,
}: {
  sessionId: string;
  totalQuestions: number;
  timeLimitSeconds?: number;
  onLoadingChange: (loading: boolean) => void;
  onComplete: () => void;
}) {
  const [question, setQuestion] = useState<McqQuestion | null>(null);
  const [budget, setBudget] = useState(totalQuestions);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seeded = useRef(false);

  const timerPaused = loading || submitting;
  const { secondsRemaining } = useQuestionTimer(timeLimitSeconds, question?.id ?? questionIndex, {
    enabled: Boolean(timeLimitSeconds),
    armed: Boolean(question),
    paused: timerPaused,
  });

  useEffect(() => {
    onLoadingChange(loading || submitting);
  }, [loading, onLoadingChange, submitting]);

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

  const handleSubmit = useCallback(
    async (questionId: number, selectedLabel: string) => {
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
          onComplete();
          return;
        }
        if (data.status === "generating" || !data.next_question) {
          setLoading(true);
          const pending = await pollMcqPendingQuestion(API_BASE, sessionId);
          setQuestion(pending.question);
          setBudget(pending.total_questions);
          setQuestionIndex((prev) => prev + 1);
          return;
        }
        if (questionIndex + 1 >= budget) {
          onComplete();
          return;
        }
        setQuestion(data.next_question);
        setQuestionIndex((prev) => prev + 1);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Submit failed");
      } finally {
        setSubmitting(false);
        setLoading(false);
      }
    },
    [sessionId, questionIndex, budget, onComplete],
  );

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex w-full max-w-2xl items-center justify-between text-sm text-[#1F2430]/70">
        <span>
          Question {question ? questionIndex + 1 : "…"} of {budget}
        </span>
        {secondsRemaining != null ? (
          <span className="font-medium tabular-nums">
            {formatQuestionTimer(secondsRemaining)}
          </span>
        ) : null}
      </div>
      {(loading || submitting) && !question && (
        <p className="text-sm text-[#1F2430]/70">Preparing your question…</p>
      )}
      {submitting && question && (
        <p className="text-sm text-[#1F2430]/70">
          Answer saved — preparing your next question…
        </p>
      )}
      {error && (
        <p className="w-full max-w-2xl rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-3 text-sm text-[#E5484D]">
          {error}
        </p>
      )}
      {question ? (
        <McqCard
          key={question.id}
          questionId={question.id}
          questionText={question.question_text}
          options={question.options}
          onSubmit={handleSubmit}
          isSubmitting={submitting}
        />
      ) : (
        !error && (
          <p className="text-sm text-[#1F2430]/70">Loading question…</p>
        )
      )}
    </div>
  );
}

function ChatDiagramRunner({
  sessionId,
  totalQuestions,
  timeLimitSeconds,
  onLoadingChange,
  onComplete,
}: {
  sessionId: string;
  totalQuestions: number;
  timeLimitSeconds?: number;
  onLoadingChange: (loading: boolean) => void;
  onComplete: () => void;
}) {
  const [question, setQuestion] = useState<DiagramNextQuestion | null>(null);
  const [budget, setBudget] = useState(totalQuestions);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seeded = useRef(false);

  const { secondsRemaining } = useQuestionTimer(
    timeLimitSeconds,
    question?.id ?? questionIndex,
    {
      enabled: Boolean(timeLimitSeconds),
      armed: Boolean(question),
      paused: loading || busy,
    },
  );

  useEffect(() => {
    onLoadingChange(loading || busy);
  }, [busy, loading, onLoadingChange]);

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

  if (error) {
    return (
      <p className="mx-auto w-full max-w-2xl rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-3 text-sm text-[#E5484D]">
        {error}
      </p>
    );
  }

  if (!question) {
    return (
      <p className="text-center text-sm text-[#1F2430]/70">Preparing your diagram…</p>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      {secondsRemaining != null ? (
        <div className="w-full max-w-2xl text-right text-sm font-medium tabular-nums text-[#1F2430]/70">
          {formatQuestionTimer(secondsRemaining)}
        </div>
      ) : null}
      <DiagramTool
        key={question.id}
        questionId={question.id}
        svgContent={question.svg_content}
        prompt={question.prompt}
        questionIndex={questionIndex}
        totalQuestions={budget}
        sessionId={sessionId}
        onBusyChange={setBusy}
        onComplete={onComplete}
        onNext={(nextQuestion) => {
          setQuestion(nextQuestion);
          setQuestionIndex((prev) => prev + 1);
        }}
      />
    </div>
  );
}
