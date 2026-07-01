"use client";

import { useCallback } from "react";

import type { SubmitResult, ToolQuestionMessage } from "@/types/chat";
import { useChatStore } from "@/store/chatStore";
import McqCard from "@/features/mcq/McqCard";
import { useMcqDriver } from "@/features/mcq/useMcqDriver";

interface ChatMcqMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (result: SubmitResult) => void;
}

export function ChatMcqMessage({ message, onAnswered }: ChatMcqMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId);
  const driver = useMcqDriver(sessionId ?? "", message.totalForTool);
  const payload = driver.currentPayload;
  const currentIndex = driver.questionIndex;

  const handleSubmit = useCallback(
    async (questionId: number, selectedLabel: string) => {
      try {
        const result = await driver.submit(questionId, selectedLabel);
        onAnswered(result);
      } catch {
        // error is surfaced via driver.error
      }
    },
    [driver, onAnswered],
  );

  if (driver.status === "loading" && !payload) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#004EFF]" />
        <span className="text-sm text-[#1F2430]/70">Loading MCQ question…</span>
      </div>
    );
  }

  if (driver.status === "error" && !payload) {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">{driver.error}</p>
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
      </div>
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
