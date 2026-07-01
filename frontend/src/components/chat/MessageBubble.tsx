import type { ChatMessage } from "@/types/chat";

export interface MessageBubbleProps {
  message: ChatMessage;
  wide?: boolean;
}

export function MessageBubble({ message, wide }: MessageBubbleProps) {
  if (message.kind === "text") {
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

  const widthClass = wide ? "w-full max-w-4xl" : "w-full max-w-2xl";

  return (
    <div className="flex justify-start">
      <div className={`${widthClass}`}>
        {message.status === "generating" && (
          <div className="flex items-center gap-2 rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 shadow-sm">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[#004EFF]" />
            <span className="text-sm text-[#1F2430]/70">
              Preparing {message.tool} question…
            </span>
          </div>
        )}
        {message.status === "failed" && (
          <div className="rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 px-4 py-3">
            <p className="text-sm text-[#E5484D]">
              Failed to load {message.tool} question.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
