"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useParams, useRouter, useSearchParams } from "next/navigation";

import { CodeChallengeView } from "@/features/code/CodeChallengeView";
import { SessionProctoringShell } from "@/features/proctoring";
import AdaptiveVoiceSession from "@/features/voice/AdaptiveVoiceSession";
import McqCard, { McqOption } from "@/features/mcq/McqCard";
import {
  NextToolInfo,
  completeSession,
  submitResponse,
} from "@/lib/session-api";
import { readIdentityReference, readSessionAuth } from "@/lib/session-storage";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/**
 * Examiner chat router. The examiner is routing-only (it sequences *tools*),
 * while each tool widget runs its own internal question loop. When a tool
 * finishes, we advance the examiner with action="complete_tool" until the
 * assessment is complete. No scores are ever shown.
 */
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
  const started = useRef(false);

  const completeHref = useMemo(() => {
    const sid = sessionId ?? search.get("session_id");
    return sid
      ? `/assessment/${token}/complete?session_id=${encodeURIComponent(sid)}`
      : `/assessment/${token}/complete`;
  }, [sessionId, search, token]);

  // Resolve session credentials, then ask the examiner for the first tool.
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

  if (!currentTool || !sessionId) {
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
        accessToken={accessToken ?? undefined}
        manageLifecycle={false}
        enabled
        consentGiven={Boolean(referenceImageB64)}
        referenceImageB64={referenceImageB64 ?? undefined}
      >
        <div className="mx-auto mb-6 w-full max-w-2xl">
          <p className="text-sm font-medium capitalize text-[#1F2430]">
            {currentTool} section
          </p>
        </div>

        {currentTool === "code" && (
          <CodeChallengeView
            initialSessionId={sessionId}
            assessmentId={token}
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
            adminConfig={{ max_difficulty: "advanced" }}
            onComplete={() => advance("voice")}
          />
        )}

        {currentTool === "mcq" && (
          <ChatMcqRunner
            sessionId={sessionId}
            totalQuestions={toolInfo?.total_for_tool ?? 1}
            onComplete={() => advance("mcq")}
          />
        )}

        {currentTool === "diagram" && (
          <DiagramStub onNext={() => advance("diagram")} />
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

/**
 * Self-contained MCQ runner: seeds a first question, then loops through the
 * silent /answer endpoint until the tool's question budget is exhausted, then
 * signals the examiner to advance.
 */
function ChatMcqRunner({
  sessionId,
  totalQuestions,
  onComplete,
}: {
  sessionId: string;
  totalQuestions: number;
  onComplete: () => void;
}) {
  const [question, setQuestion] = useState<McqQuestion | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seeded = useRef(false);

  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    fetch(`${API_BASE}/mcq/questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_text:
          "Before answering an assessment question, what is the best first step?",
        difficulty: "easy",
        correct_option: "A",
        options: [
          { label: "A", text: "Read carefully and identify the requirement" },
          { label: "B", text: "Answer quickly without analysis" },
          { label: "C", text: "Skip it immediately" },
          { label: "D", text: "Pick the longest option" },
        ],
      }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("Failed to load MCQ");
        setQuestion((await res.json()) as McqQuestion);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load MCQ"),
      );
  }, []);

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
            total_questions: totalQuestions,
          }),
        });
        if (!res.ok) throw new Error("Failed to submit answer");
        const data = (await res.json()) as {
          next_question: McqQuestion | null;
          is_complete: boolean;
        };
        if (
          data.is_complete ||
          !data.next_question ||
          questionIndex + 1 >= totalQuestions
        ) {
          onComplete();
          return;
        }
        setQuestion(data.next_question);
        setQuestionIndex((prev) => prev + 1);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Submit failed");
      } finally {
        setSubmitting(false);
      }
    },
    [sessionId, questionIndex, totalQuestions, onComplete],
  );

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="w-full max-w-2xl text-sm text-[#1F2430]/70">
        Question {questionIndex + 1} of {totalQuestions}
      </div>
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
        <p className="text-sm text-[#1F2430]/70">Loading question…</p>
      )}
    </div>
  );
}

/** Placeholder for the diagram tool (built separately). */
function DiagramStub({ onNext }: { onNext: () => void }) {
  return (
    <div className="mx-auto w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 text-center">
      <p className="text-lg font-semibold text-[#1F2430]">Diagram question</p>
      <p className="mt-2 text-sm text-[#1F2430]/70">
        The diagram tool is coming soon.
      </p>
      <button
        type="button"
        onClick={onNext}
        className="mt-5 rounded-lg bg-[#004EFF] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#3374FF]"
      >
        Next
      </button>
    </div>
  );
}
