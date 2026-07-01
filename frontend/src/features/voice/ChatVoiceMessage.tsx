"use client";

import { useCallback, useState } from "react";

import { AnsweredToolPlaceholder } from "@/components/chat/AnsweredToolPlaceholder";
import type { SubmitResult, ToolQuestionMessage } from "@/types/chat";
import {
  buildPreviewResult,
  runSubmitWithPreview,
} from "@/features/chat/submitWithPreview";
import { useChatStore } from "@/store/chatStore";
import VoiceRecorder from "@/features/voice/VoiceRecorder";
import { type Difficulty } from "@/lib/voice-api";
import {
  type VoiceQuestionPayload,
  useVoiceDriver,
} from "@/features/voice/useVoiceDriver";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const DEFAULT_VOICE_QUESTION =
  "Tell me about a recent technical challenge you faced and how you solved it.";

function getWsBase(): string {
  return API_BASE.replace(/^https/, "wss").replace(/^http/, "ws");
}

interface ChatVoiceMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (result: SubmitResult) => void | Promise<void>;
}

export function ChatVoiceMessage({ message, onAnswered }: ChatVoiceMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId) ?? "";
  const bootstrapPayload = message.payload as VoiceQuestionPayload | null;
  const isAnswered = message.status === "answered";
  const initialDifficulty = (message.difficulty as Difficulty | undefined) ?? "beginner";

  const driver = useVoiceDriver({
    sessionId,
    initialQuestion: DEFAULT_VOICE_QUESTION,
    initialDifficulty,
    initialQuestionIndex: message.questionIndex,
    timeLimitSeconds: message.timeLimitSeconds ?? 120,
    learnerProfile: {},
    adminConfig: {
      max_difficulty: "advanced",
      max_questions: message.totalForTool,
    },
    maxQuestions: message.totalForTool,
    bootstrapPayload,
    skipBootstrap: isAnswered,
  });
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleRecordingComplete = useCallback(async () => {
    setSubmitError(null);
    const preview = buildPreviewResult("voice", "Voice response submitted");
    try {
      await runSubmitWithPreview(preview, () => driver.submit(), onAnswered);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Voice submit failed";
      setSubmitError(msg);
    }
  }, [driver, onAnswered]);

  const wsUrl = `${getWsBase()}/voice/sessions`;

  if (isAnswered) {
    return <AnsweredToolPlaceholder message={message} />;
  }

  if (driver.phase === "error" || submitError) {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">
          {submitError ?? driver.error ?? "An unexpected error occurred."}
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
          {driver.questionText || DEFAULT_VOICE_QUESTION}
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
    </div>
  );
}
