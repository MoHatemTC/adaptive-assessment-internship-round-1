import { create } from "zustand";

import type { ChatMessage, ToolType } from "@/types/chat";
import { completeSession, submitResponse } from "@/lib/session-api";
import type { NextToolInfo } from "@/lib/session-api";

let nextId = 1;
function genId(): string {
  return `chat-${nextId++}-${Date.now()}`;
}

export interface ChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  accessToken: string | null;
  currentTool: ToolType | null;
  currentToolInfo: NextToolInfo | null;
  isComplete: boolean;

  appendMessage: (msg: ChatMessage) => void;
  pushToolQuestion: (
    tool: ToolType,
    payload: unknown,
    questionIndex: number,
    totalForTool: number,
    difficulty?: string,
    timeLimitSeconds?: number | null,
  ) => string;
  pushTransition: (text: string) => void;
  markAnswered: (messageId: string) => void;
  setSession: (sessionId: string, accessToken: string) => void;
  setCurrentTool: (tool: ToolType | null, info: NextToolInfo | null) => void;
  setIsComplete: (complete: boolean) => void;
  advanceExaminer: () => Promise<ExaminerAdvanceResult>;
  reset: () => void;
}

export interface ExaminerAdvanceResult {
  nextTool: ToolType | null;
  nextToolInfo: NextToolInfo | null;
  isComplete: boolean;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  sessionId: null,
  accessToken: null,
  currentTool: null,
  currentToolInfo: null,
  isComplete: false,

  appendMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  pushToolQuestion: (tool, payload, questionIndex, totalForTool, difficulty, timeLimitSeconds) => {
    const id = genId();
    const msg: ChatMessage = {
      id,
      kind: "tool_question",
      role: "assistant",
      createdAt: Date.now(),
      tool,
      questionIndex,
      totalForTool,
      difficulty,
      timeLimitSeconds,
      status: "ready",
      payload,
    };
    set((s) => ({
      messages: [...s.messages, msg],
      currentTool: tool,
    }));
    return id;
  },

  pushTransition: (text) => {
    const msg: ChatMessage = {
      id: genId(),
      kind: "text",
      role: "assistant",
      createdAt: Date.now(),
      text,
    };
    set((s) => ({ messages: [...s.messages, msg] }));
  },

  markAnswered: (messageId) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === messageId && m.kind === "tool_question"
          ? { ...m, status: "answered" as const }
          : m,
      ),
    })),

  setSession: (sessionId, accessToken) => set({ sessionId, accessToken }),

  setCurrentTool: (tool, info) => set({ currentTool: tool, currentToolInfo: info }),

  setIsComplete: (complete) => set({ isComplete: complete }),

  advanceExaminer: async () => {
    const { sessionId, accessToken, currentTool } = get();
    if (!sessionId || !accessToken || !currentTool) {
      throw new Error("Cannot advance: missing session or current tool");
    }

    const res = await submitResponse(sessionId, currentTool, "complete_tool", accessToken);

    const nextTool = res.current_tool as ToolType | null;
    const nextInfo = res.next_tool_info;

    set({
      currentTool: nextTool,
      currentToolInfo: nextInfo,
      isComplete: res.is_complete,
    });

    if (res.is_complete && sessionId && accessToken) {
      try {
        await completeSession(sessionId, accessToken);
      } catch (err) {
        console.warn("Failed to mark session complete", err);
      }
    }

    return { nextTool, nextToolInfo: nextInfo, isComplete: res.is_complete };
  },

  reset: () =>
    set({
      messages: [],
      sessionId: null,
      accessToken: null,
      currentTool: null,
      currentToolInfo: null,
      isComplete: false,
    }),
}));
