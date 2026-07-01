"use client";

import type { TextMessage } from "@/types/chat";

export function TextBubble({ message }: { message: TextMessage }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] rounded-2xl bg-white px-4 py-3 shadow-sm border border-[#D8DDF0]">
        <p className="text-sm leading-relaxed text-[#1F2430]">
          {message.text}
        </p>
      </div>
    </div>
  );
}
