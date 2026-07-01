"use client";

import { createContext, useContext } from "react";

import type { SubmitResult } from "@/types/chat";

export interface ChatContextValue {
  assessmentToken: string;
  onAnswered: (result: SubmitResult) => void | Promise<void>;
}

export const ChatContext = createContext<ChatContextValue | null>(null);

export function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext must be used within a ChatContext.Provider");
  return ctx;
}
