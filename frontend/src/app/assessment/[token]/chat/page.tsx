"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import { useParams, useRouter, useSearchParams } from "next/navigation";

import type { ToolType, ToolQuestionMessage, NormalizedToolStep } from "@/types/chat";
import { useChatStore } from "@/store/chatStore";
import { AssessmentTimerShell } from "@/features/assessment/AssessmentTimerShell";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { SessionProctoringShell } from "@/features/proctoring";
import { toolRegistry } from "@/features/chat/toolRegistry";
import { submitResponse } from "@/lib/session-api";
import { readIdentityReference, readSessionAuth } from "@/lib/session-storage";

export default function AssessmentChatPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const search = useSearchParams();

  const token = params.token;
  const referenceImageB64 = useMemo(() => readIdentityReference(), []);

  const messages = useChatStore((s) => s.messages);
  const sessionId = useChatStore((s) => s.sessionId);
  const accessToken = useChatStore((s) => s.accessToken);
  const currentTool = useChatStore((s) => s.currentTool);
  const currentToolInfo = useChatStore((s) => s.currentToolInfo);
  const isComplete = useChatStore((s) => s.isComplete);

  const pushToolQuestion = useChatStore((s) => s.pushToolQuestion);
  const pushTransition = useChatStore((s) => s.pushTransition);
  const markAnswered = useChatStore((s) => s.markAnswered);
  const setSession = useChatStore((s) => s.setSession);
  const setCurrentTool = useChatStore((s) => s.setCurrentTool);
  const setIsComplete = useChatStore((s) => s.setIsComplete);
  const advanceExaminer = useChatStore((s) => s.advanceExaminer);

  const currentMessageId = useRef<string | null>(null);
  const started = useRef(false);
  const advancing = useRef(false);

  const completeHref = useMemo(() => {
    const sid = sessionId ?? search.get("session_id");
    return sid
      ? `/assessment/${token}/complete?session_id=${encodeURIComponent(sid)}`
      : `/assessment/${token}/complete`;
  }, [sessionId, search, token]);

  const firstQuestionForTool = useCallback(
    (tool: string, totalForTool: number, difficulty?: string, timeLimitSeconds?: number | null) => {
      const msgId = pushToolQuestion(
        tool as ToolType,
        null,
        0,
        totalForTool,
        difficulty,
        timeLimitSeconds,
      );
      currentMessageId.current = msgId;
    },
    [pushToolQuestion],
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const stored = readSessionAuth();
    const sid = search.get("session_id") ?? stored.sessionId;
    const tok = stored.token;
    if (!sid || !tok) return;

    setSession(sid, tok);

    submitResponse(sid, "", "start", tok)
      .then((res) => {
        const tool = res.current_tool as ToolType | null;
        setCurrentTool(tool, res.next_tool_info);
        setIsComplete(res.is_complete);

        if (tool && res.next_tool_info) {
          firstQuestionForTool(
            tool,
            res.next_tool_info.total_for_tool,
            res.next_tool_info.difficulty,
            res.next_tool_info.time_limit_seconds,
          );
        }
      })
      .catch(() => {});
  }, [search, setSession, setCurrentTool, setIsComplete, firstQuestionForTool]);

  useEffect(() => {
    if (!isComplete || !sessionId || !accessToken) return;
    router.push(completeHref);
  }, [isComplete, sessionId, accessToken, completeHref, router]);

  const handleAnswered = useCallback(
    async (step: NormalizedToolStep) => {
      if (currentMessageId.current) {
        markAnswered(currentMessageId.current);
      }

      pushTransition(step.transitionText);

      if (step.isToolComplete) {
        if (advancing.current) return;
        advancing.current = true;

        try {
          const result = await advanceExaminer();

          if (result.isComplete) {
            currentMessageId.current = null;
            return;
          }

          if (result.nextTool && result.nextToolInfo) {
            firstQuestionForTool(
              result.nextTool,
              result.nextToolInfo.total_for_tool,
              result.nextToolInfo.difficulty,
              result.nextToolInfo.time_limit_seconds,
            );
          }
        } catch {
          // error handled by store
        } finally {
          advancing.current = false;
        }
      } else if (step.nextPayload) {
        const msgId = pushToolQuestion(
          step.tool,
          step.nextPayload,
          0,
          currentToolInfo?.total_for_tool ?? 1,
        );
        currentMessageId.current = msgId;
      }
    },
    [
      markAnswered,
      pushTransition,
      pushToolQuestion,
      advanceExaminer,
      firstQuestionForTool,
      currentToolInfo,
    ],
  );

  interface ToolMsg {
    kind: "tool_question";
    tool: ToolType;
  }

  const renderTool = useCallback(
    (msg: ToolMsg) => {
      const Component = toolRegistry[msg.tool];
      if (!Component) return null;
      return (
        <Component
          message={msg as ToolQuestionMessage}
          onAnswered={handleAnswered}
        />
      );
    },
    [handleAnswered],
  );

  if (!sessionId || !accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface px-4">
        <p className="text-sm text-[#1F2430]/70">Preparing your assessment…</p>
      </main>
    );
  }

  const isBusy = advancing.current;

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
          paused={isBusy}
        />

        <div className="mx-auto mb-6 w-full max-w-2xl">
          <p className="text-sm font-medium capitalize text-[#1F2430]">
            {currentTool ?? ""} section
          </p>
        </div>

        <ChatWindow
          messages={messages}
          renderTool={renderTool}
        />
      </SessionProctoringShell>
    </main>
  );
}
