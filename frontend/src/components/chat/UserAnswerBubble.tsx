import type { UserAnswerMessage } from "@/types/chat";

const toolLabels: Record<string, string> = {
  mcq: "MCQ",
  diagram: "Diagram",
  voice: "Voice",
  code: "Code",
};

export interface UserAnswerBubbleProps {
  message: UserAnswerMessage;
}

export function UserAnswerBubble({ message }: UserAnswerBubbleProps) {
  const label = toolLabels[message.tool] ?? message.tool;

  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl bg-[#004EFF] px-4 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-white/70">
            {label}
          </span>
        </div>
        <p className="mt-0.5 text-sm leading-relaxed text-white">
          {message.summary}
        </p>
      </div>
    </div>
  );
}
