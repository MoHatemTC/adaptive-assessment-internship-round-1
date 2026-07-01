"use client";

import { useCallback, useState } from "react";

import { AnsweredToolPlaceholder } from "@/components/chat/AnsweredToolPlaceholder";
import type { McqQuestion } from "@/features/mcq/useMcqDriver";
import type { SubmitResult, ToolQuestionMessage } from "@/types/chat";
import {
  buildPreviewResult,
  runSubmitWithPreview,
} from "@/features/chat/submitWithPreview";
import { useChatStore } from "@/store/chatStore";
import McqCard from "@/features/mcq/McqCard";
import { useMcqDriver } from "@/features/mcq/useMcqDriver";
import {
  formatQuestionTimer,
  useQuestionTimer,
} from "@/hooks/useQuestionTimer";

interface ChatMcqMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (result: SubmitResult) => void | Promise<void>;
}

export function ChatMcqMessage({ message, onAnswered }: ChatMcqMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId);
  const initialPayload = message.payload as McqQuestion | null;
  const isAnswered = message.status === "answered";

  const driver = useMcqDriver(sessionId ?? "", message.totalForTool, {
    initialPayload,
    initialQuestionIndex: message.questionIndex,
    skipBootstrap: isAnswered,
  });
  const payload = driver.currentPayload;
  const currentIndex = driver.questionIndex;
  const [submitError, setSubmitError] = useState<string | null>(null);

  const timerPaused = driver.status === "loading" || driver.status === "submitting";
  const { secondsRemaining } = useQuestionTimer(message.timeLimitSeconds ?? undefined, payload?.id ?? currentIndex, {
    enabled: Boolean(message.timeLimitSeconds),
    armed: Boolean(payload) && !isAnswered,
    paused: timerPaused,
  });

  const handleSubmit = useCallback(
    async (questionId: number, selectedLabel: string) => {
      setSubmitError(null);
      const preview = buildPreviewResult("mcq", `Selected: ${selectedLabel}`);
      try {
        await runSubmitWithPreview(
          preview,
          () => driver.submit(questionId, selectedLabel),
          onAnswered,
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Submit failed";
        setSubmitError(msg);
      }
    },
    [driver, onAnswered],
  );

  if (isAnswered) {
    return <AnsweredToolPlaceholder message={message} />;
  }

  if (driver.status === "loading" && !payload) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#004EFF]" />
        <span className="text-sm text-[#1F2430]/70">Loading MCQ question…</span>
      </div>
    );
  }

  if ((driver.status === "error" && !payload) || submitError) {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">{submitError ?? driver.error}</p>
      </div>
    );
  }

  if (!payload) {
    return null;
  }

  return (
    <div className="w-full max-w-2xl">
      <div className="mb-2 flex items-center justify-between text-xs text-[#1F2430]/70">
        <span>
          Question {currentIndex + 1} of {message.totalForTool}
        </span>
        {secondsRemaining != null ? (
          <span className="font-medium tabular-nums">
            {formatQuestionTimer(secondsRemaining)}
          </span>
        ) : null}
      </div>
      {driver.status === "submitting" && (
        <p className="mb-2 text-sm text-[#1F2430]/70">
          Answer saved — preparing your next question…
        </p>
      )}
      <McqCard
        key={`${payload.id}-${currentIndex}`}
        questionId={payload.id}
        questionText={payload.question_text}
        options={payload.options}
        onSubmit={handleSubmit}
        isSubmitting={driver.status === "submitting"}
      />
    </div>
  );
}
