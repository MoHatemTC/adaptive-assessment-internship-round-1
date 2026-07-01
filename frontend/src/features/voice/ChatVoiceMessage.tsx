"use client";

import { useCallback } from "react";

import type { ToolQuestionMessage, NormalizedToolStep } from "@/types/chat";
import { useChatStore } from "@/store/chatStore";
import VoiceRecorder from "@/features/voice/VoiceRecorder";
import { useVoiceDriver } from "@/features/voice/useVoiceDriver";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

function getWsBase(): string {
  return API_BASE.replace(/^https/, "wss").replace(/^http/, "ws");
}

interface ChatVoiceMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (step: NormalizedToolStep) => void;
}

export function ChatVoiceMessage({ message, onAnswered }: ChatVoiceMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId) ?? "";
  const driver = useVoiceDriver({
    sessionId,
    initialQuestion: "",
    initialDifficulty: "beginner",
    timeLimitSeconds: message.timeLimitSeconds ?? 120,
    learnerProfile: {},
    adminConfig: {},
    maxQuestions: message.totalForTool,
  });

  const handleRecordingComplete = useCallback(
    async () => {
      try {
        const step = await driver.submit();
        onAnswered(step);
      } catch {
        // error surfaced via driver.error
      }
    },
    [driver, onAnswered],
  );

  const wsUrl = `${getWsBase()}/voice/sessions`;

  if (driver.phase === "error") {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">
          {driver.error ?? "An unexpected error occurred."}
        </p>
        <button
          type="button"
          onClick={driver.handleRetry}
          className="mt-3 rounded-lg bg-[#004EFF] px-4 py-2 text-sm font-medium text-white hover:bg-[#3374FF]"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="w-full max-w-2xl space-y-4">
      <div
        key={driver.questionIndex}
        className="rounded-2xl border border-[#D8DDF0] bg-white px-8 py-7 shadow-sm"
      >
        <p className="text-lg font-medium leading-relaxed text-[#1F2430]">
          {driver.questionText || "Tell me about a recent technical challenge you faced and how you solved it."}
        </p>
      </div>

      {driver.phase === "initializing" && (
        <div className="flex flex-col items-center rounded-2xl border border-[#D8DDF0] bg-white px-6 py-7 shadow-sm">
          <div className="flex items-center gap-2">
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                className="h-2 w-2 rounded-full bg-[#004EFF]"
                style={{
                  animation: "dotPulse 900ms ease-in-out infinite",
                  animationDelay: `${delay}ms`,
                }}
              />
            ))}
          </div>
          <p className="mt-3 text-sm text-[#343434]">Preparing your question…</p>
        </div>
      )}

      {driver.phase === "recording" && driver.voiceSessionId !== null && (
        <div className="flex flex-col items-center">
          <VoiceRecorder
            voiceSessionId={String(driver.voiceSessionId)}
            timeLimitSeconds={message.timeLimitSeconds ?? 120}
            onComplete={handleRecordingComplete}
            wsUrl={wsUrl}
          />
          <p className="mt-4 text-center text-sm text-[#343434]">
            Speak clearly. Recording stops automatically.
          </p>
        </div>
      )}

      {driver.phase === "processing" && (
        <div className="flex flex-col items-center rounded-2xl border border-[#D8DDF0] bg-white px-6 py-7 shadow-sm">
          <div className="flex items-center gap-2">
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                className="h-2 w-2 rounded-full bg-[#004EFF]"
                style={{
                  animation: "dotPulse 900ms ease-in-out infinite",
                  animationDelay: `${delay}ms`,
                }}
              />
            ))}
          </div>
          <p className="mt-3 text-sm text-[#343434]">Analyzing your response…</p>
        </div>
      )}

      {driver.phase === "transitioning" && (
        <div className="flex flex-col items-center rounded-2xl border border-[#D8DDF0] bg-white px-6 py-7 shadow-sm">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width={24}
            height={24}
            viewBox="0 0 24 24"
            fill="none"
            stroke="#004EFF"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-6 w-6"
            aria-hidden="true"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
          <p className="mt-3 text-sm text-[#343434]">Loading next…</p>
        </div>
      )}
    </div>
  );
}
