"use client";

import { useCallback, useState } from "react";

import { AnsweredToolPlaceholder } from "@/components/chat/AnsweredToolPlaceholder";
import type { AdaptiveContract } from "@/lib/api";
import type { SubmitResult, ToolQuestionMessage } from "@/types/chat";
import {
  buildPreviewResult,
  buildUserAnswerMessage,
} from "@/features/chat/submitWithPreview";
import { useChatContext } from "@/features/chat/chatContext";
import { useChatStore } from "@/store/chatStore";
import { CodeEditor } from "@/features/code/CodeEditor";
import { CodeQuestionPanel } from "@/features/code/CodeQuestionPanel";
import {
  type CodeQuestionPayload,
  useCodeDriver,
} from "@/features/code/useCodeDriver";
import { generateCodeChallenge } from "@/lib/api";

interface ChatCodeMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (result: SubmitResult) => void | Promise<void>;
}

export function ChatCodeMessage({ message, onAnswered }: ChatCodeMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId) ?? "";
  const { assessmentToken } = useChatContext();
  const bootstrapPayload = message.payload as CodeQuestionPayload | null;
  const isAnswered = message.status === "answered";

  const driver = useCodeDriver({
    sessionId,
    assessmentId: assessmentToken,
    maxQuestions: message.totalForTool,
    bootstrapPayload,
    skipBootstrap: isAnswered,
  });

  const [generatingNext, setGeneratingNext] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const challenge = driver.challenge;

  const handleSubmitted = useCallback(
    async ({ contract: newContract }: { contract: AdaptiveContract }) => {
      setSubmitError(null);
      const answered = newContract.question_index;
      const reachedLimit =
        message.totalForTool > 0 && answered >= message.totalForTool;
      const isToolComplete = newContract.stop || reachedLimit;

      const preview = buildPreviewResult("code", "Submitted code solution");
      await onAnswered({ ...preview, phase: "preview" });

      try {
        if (isToolComplete) {
          await onAnswered({
            answerMessage: preview.answerMessage,
            step: {
              tool: "code",
              isToolComplete: true,
              nextPayload: null,
              transitionText: "Got it — next question…",
            },
            phase: "final",
          });
          return;
        }

        setGeneratingNext(true);
        const nextChallenge = await generateCodeChallenge({
          session_id: sessionId,
          assessment_id: assessmentToken,
          contract: newContract,
          language: driver.language,
        });

        await onAnswered({
          answerMessage: buildUserAnswerMessage("code", "Submitted code solution"),
          step: {
            tool: "code",
            isToolComplete: false,
            nextPayload: {
              challenge: nextChallenge.challenge,
              contract: nextChallenge.contract,
              questionIndex: nextChallenge.contract.question_index,
              difficulty: nextChallenge.contract.difficulty,
            } satisfies CodeQuestionPayload,
            nextQuestionIndex: nextChallenge.contract.question_index,
            transitionText: "Got it — next question…",
          },
          phase: "final",
        });
      } catch (err) {
        console.error("Code submit failed", err);
        const msg = err instanceof Error ? err.message : "Submit failed";
        setSubmitError(msg);
      } finally {
        setGeneratingNext(false);
      }
    },
    [message.totalForTool, sessionId, assessmentToken, driver.language, onAnswered],
  );

  if (isAnswered) {
    return <AnsweredToolPlaceholder message={message} />;
  }

  if (driver.status === "loading" && !challenge) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#004EFF]" />
        <span className="text-sm text-[#1F2430]/70">Preparing coding challenge…</span>
      </div>
    );
  }

  if ((driver.status === "error" && !challenge) || submitError) {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">{submitError ?? driver.error}</p>
      </div>
    );
  }

  if (!challenge) return null;

  return (
    <div className="w-full max-w-4xl space-y-4">
      {generatingNext && (
        <div className="rounded-lg border border-[#004EFF]/20 bg-[#004EFF]/5 p-3 text-sm text-[#004EFF]">
          Answer recorded — LLM is authoring your next challenge…
        </div>
      )}
      <CodeQuestionPanel challenge={challenge} difficulty={driver.difficulty} />
      <CodeEditor
        key={`${challenge.id}-${driver.questionIndex}`}
        challenge={challenge}
        sessionId={sessionId}
        assessmentId={assessmentToken}
        questionIndex={driver.questionIndex}
        difficulty={driver.difficulty}
        onSubmitted={handleSubmitted}
        disabled={generatingNext}
      />
    </div>
  );
}
