"use client";

import { useEffect, useRef } from "react";

import type { ChatMessage } from "@/types/chat";
import { messageKindRegistry } from "@/features/chat/messageKindRegistry";

export interface ChatWindowProps {
  messages: ChatMessage[];
}

export function ChatWindow({ messages }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      {messages.map((msg) => {
        const Renderer = messageKindRegistry[msg.kind] as React.ComponentType<{ message: ChatMessage }>;
        return (
          <div key={msg.id}>
            <Renderer message={msg} />
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
