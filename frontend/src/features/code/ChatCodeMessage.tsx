"use client";

import { useCallback, useEffect, useState } from "react";

import type { ToolQuestionMessage, NormalizedToolStep } from "@/types/chat";
import { useChatStore } from "@/store/chatStore";
import { CodeEditor } from "@/features/code/CodeEditor";
import { CodeQuestionPanel } from "@/features/code/CodeQuestionPanel";
import { useCodeDriver } from "@/features/code/useCodeDriver";
import { generateCodeChallenge } from "@/lib/api";

interface ChatCodeMessageProps {
  message: ToolQuestionMessage;
  onAnswered: (step: NormalizedToolStep) => void;
}

export function ChatCodeMessage({ message, onAnswered }: ChatCodeMessageProps) {
  const sessionId = useChatStore((s) => s.sessionId) ?? "";

  const driver = useCodeDriver({
    sessionId,
    assessmentId: "",
    maxQuestions: message.totalForTool,
  });

  const [challenge, setChallenge] = useState(driver.challenge);
  const [generatingNext, setGeneratingNext] = useState(false);

  useEffect(() => {
    if (driver.challenge) setChallenge(driver.challenge);
  }, [driver.challenge]);

  const handleSubmitted = useCallback(
    async ({ contract: newContract }: { contract: { stop: boolean; question_index: number } }) => {
      const answered = newContract.question_index;
      const reachedLimit =
        message.totalForTool > 0 && answered >= message.totalForTool;

      if (newContract.stop || reachedLimit) {
        onAnswered({
          tool: "code",
          isToolComplete: true,
          nextPayload: null,
          transitionText: "Got it — next question…",
        });
        return;
      }

      setGeneratingNext(true);
      try {
        const result = await generateCodeChallenge({
          session_id: sessionId,
          assessment_id: "",
          contract: newContract as Parameters<typeof generateCodeChallenge>[0]["contract"],
          language: driver.language,
        });
        setChallenge(result.challenge);
      } catch {
        // error surfaced via driver
      } finally {
        setGeneratingNext(false);
      }
    },
    [message.totalForTool, sessionId, driver.language, onAnswered],
  );

  if (driver.status === "loading" && !challenge) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#004EFF]" />
        <span className="text-sm text-[#1F2430]/70">Preparing coding challenge…</span>
      </div>
    );
  }

  if (driver.status === "error" && !challenge) {
    return (
      <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
        <p className="text-sm text-[#E5484D]">{driver.error}</p>
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
        assessmentId=""
        questionIndex={driver.questionIndex}
        difficulty={driver.difficulty}
        onSubmitted={handleSubmitted}
        disabled={generatingNext}
      />
    </div>
  );
}
