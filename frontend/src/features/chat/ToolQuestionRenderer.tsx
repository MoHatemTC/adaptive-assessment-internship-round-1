"use client";

import type { ToolQuestionMessage } from "@/types/chat";
import { toolRegistry } from "@/features/chat/toolRegistry";
import { useChatContext } from "@/features/chat/chatContext";

export interface ToolQuestionRendererProps {
  message: ToolQuestionMessage;
}

export function ToolQuestionRenderer({ message }: ToolQuestionRendererProps) {
  const { onAnswered } = useChatContext();
  const Component = toolRegistry[message.tool];
  if (!Component) return null;
  return <Component message={message} onAnswered={onAnswered} />;
}
