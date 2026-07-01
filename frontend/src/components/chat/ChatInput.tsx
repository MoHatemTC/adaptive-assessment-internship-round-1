"use client";

import { useCallback, useRef } from "react";

export interface ChatInputProps {
  visible?: boolean;
  onSend?: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  visible = false,
  onSend,
  disabled = false,
  placeholder = "Type your answer…",
}: ChatInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSend = useCallback(() => {
    const el = inputRef.current;
    if (!el || !el.value.trim() || disabled) return;
    onSend?.(el.value.trim());
    el.value = "";
  }, [onSend, disabled]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") handleSend();
    },
    [handleSend],
  );

  if (!visible) return null;

  return (
    <div className="mx-auto flex w-full max-w-2xl items-center gap-2 border-t border-[#D8DDF0] bg-white px-4 py-3">
      <input
        ref={inputRef}
        type="text"
        placeholder={placeholder}
        disabled={disabled}
        onKeyDown={handleKeyDown}
        className="flex-1 rounded-2xl border border-[#D8DDF0] bg-[#FBFBFD] px-4 py-2.5 text-sm text-[#1F2430] placeholder-[#A0A8B8] outline-none transition focus:border-[#004EFF] focus:ring-2 focus:ring-[#004EFF]/10 disabled:opacity-60"
      />
      <button
        type="button"
        onClick={handleSend}
        disabled={disabled}
        className="flex h-[38px] w-[38px] items-center justify-center rounded-full bg-[#004EFF] text-white transition hover:bg-[#3374FF] disabled:opacity-60"
        aria-label="Send"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M15 1L7 9"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M15 1L10 15L7 9L1 6L15 1Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}
