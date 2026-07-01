"use client";

import { useEffect, useRef } from "react";

import type { ChatMessage } from "@/types/chat";
import { MessageBubble } from "@/components/chat/MessageBubble";

export interface ChatWindowProps {
  messages: ChatMessage[];
  renderTool?: (message: ChatMessage & { kind: "tool_question" }) => React.ReactNode;
}

export function ChatWindow({ messages, renderTool }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      {messages.map((msg) => (
        <div key={msg.id}>
          {msg.kind === "tool_question" ? (
            renderTool ? (
              renderTool(msg)
            ) : (
              <MessageBubble message={msg} />
            )
          ) : (
            <MessageBubble message={msg} />
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
