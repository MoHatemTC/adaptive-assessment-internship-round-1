"use client";

import { useCallback, useEffect, useState } from "react";

import { AnsweredToolPlaceholder } from "@/components/chat/AnsweredToolPlaceholder";
import type { DiagramNextQuestion } from "@/features/diagram/useDiagramDriver";
import type { SubmitResult, ToolQuestionMessage } from "@/types/chat";
import {
  buildPreviewResult,
  runSubmitWithPreview,
} from "@/features/chat/submitWithPreview";
import { useChatStore } from "@/store/chatStore";
import { useDiagramDriver } from "@/features/diagram/useDiagramDriver";
import {
  formatQuestionTimer,
  useQuestionTimer,
} from "@/hooks/useQuestionTimer";

interface ChatDiagramMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (result: SubmitResult) => void | Promise<void>;
}

export function ChatDiagramMessage({ message, onAnswered }: ChatDiagramMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId);
  const initialPayload = message.payload as DiagramNextQuestion | null;
  const isAnswered = message.status === "answered";

  const driver = useDiagramDriver(sessionId ?? "", message.totalForTool, {
    initialPayload,
    initialQuestionIndex: message.questionIndex,
    skipBootstrap: isAnswered,
  });
  const question = driver.currentPayload;
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showQuestion, setShowQuestion] = useState(Boolean(initialPayload));
  const [submitError, setSubmitError] = useState<string | null>(null);

  const timerPaused = submitting || driver.status === "submitting" || driver.status === "loading";
  const { secondsRemaining } = useQuestionTimer(message.timeLimitSeconds ?? undefined, question?.id ?? driver.questionIndex, {
    enabled: Boolean(message.timeLimitSeconds),
    armed: Boolean(question) && !isAnswered,
    paused: timerPaused,
  });

  useEffect(() => {
    if (question) {
      setShowQuestion(Boolean(initialPayload));
      setAnswer("");
    }
  }, [question?.id, question, initialPayload]);

  const handleSubmit = useCallback(async () => {
    if (!question || !answer.trim() || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    const summary = answer.trim();
    const preview = buildPreviewResult("diagram", `Submitted: ${summary}`);
    try {
      await runSubmitWithPreview(
        preview,
        () => driver.submit(question.id, summary, driver.questionIndex),
        onAnswered,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Submit failed";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }, [question, answer, submitting, driver, onAnswered]);

  if (isAnswered) {
    return <AnsweredToolPlaceholder message={message} />;
  }

  if (driver.status === "loading" && !question) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#004EFF]" />
        <span className="text-sm text-[#1F2430]/70">Preparing diagram question…</span>
      </div>
    );
  }

  if ((driver.status === "error" && !question) || submitError) {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">{submitError ?? driver.error}</p>
      </div>
    );
  }

  if (!question) return null;

  if (!showQuestion) {
    return (
      <div className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <span className="inline-flex rounded-full bg-[#CCE0FF] px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-[#004EFF]">
            Diagram
          </span>
          <span className="text-xs text-[#A0A8B8]">
            Question {driver.questionIndex + 1} / {message.totalForTool}
            {secondsRemaining != null ? ` · ${formatQuestionTimer(secondsRemaining)}` : ""}
          </span>
        </div>
        <h2 className="mb-4 text-[18px] font-semibold text-[#1F2430]">
          Study the diagram below. One component is missing its label.
        </h2>
        <div
          className="overflow-x-auto rounded-2xl border border-[#D8DDF0] bg-white p-4"
          dangerouslySetInnerHTML={{ __html: question.svg_content }}
        />
        <div className="mt-3 flex items-center gap-2 text-xs text-[#606575]">
          <span className="inline-block h-3 w-6 rounded-sm border-2 border-dashed border-[#FFB300] bg-[#FFB30022]" />
          <span>The highlighted node with [?] is the one you need to identify.</span>
        </div>
        <button
          type="button"
          onClick={() => setShowQuestion(true)}
          className="mt-6 flex h-[43px] w-full items-center justify-center gap-2 rounded-lg bg-[#004EFF] text-sm font-semibold text-white transition hover:bg-[#3374FF]"
        >
          View Question →
        </button>
      </div>
    );
  }

  return (
    <div className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 shadow-sm">
      <div className="mb-2 flex items-center justify-between text-xs text-[#1F2430]/70">
        <span>
          Question {driver.questionIndex + 1} / {message.totalForTool}
        </span>
        {secondsRemaining != null ? (
          <span className="font-medium tabular-nums">
            {formatQuestionTimer(secondsRemaining)}
          </span>
        ) : null}
      </div>
      <div
        className="mb-4 overflow-hidden rounded-xl border border-[#D8DDF0] bg-white"
        style={{ maxHeight: 180, overflow: "hidden" }}
      >
        <div
          className="pointer-events-none scale-[0.6] origin-top-left"
          style={{ width: "167%" }}
          dangerouslySetInnerHTML={{ __html: question.svg_content }}
        />
      </div>
      <h2 className="mb-4 text-[18px] font-semibold text-[#1F2430]">
        {question.prompt}
      </h2>
      <input
        type="text"
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && answer.trim()) handleSubmit();
        }}
        placeholder="Type the name of the missing component…"
        disabled={submitting || driver.status === "submitting"}
        className="w-full rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 text-sm text-[#1F2430] placeholder-[#A0A8B8] outline-none transition focus:border-[#004EFF] focus:ring-2 focus:ring-[#004EFF]/10 disabled:opacity-60"
      />
      {(driver.status === "error" && driver.error) || submitError ? (
        <p className="mt-2 text-xs font-medium text-[#E5484D]">
          {submitError ?? driver.error}
        </p>
      ) : null}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={submitting || driver.status === "submitting" || !answer.trim()}
        className="mt-4 flex h-[43px] w-full items-center justify-center gap-2 rounded-lg bg-[#004EFF] text-sm font-semibold text-white transition hover:bg-[#3374FF] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting || driver.status === "submitting" ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Submitting…
          </>
        ) : (
          "Submit Answer"
        )}
      </button>
    </div>
  );
}
