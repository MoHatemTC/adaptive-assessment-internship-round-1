import type { ToolQuestionMessage } from "@/types/chat";

const toolLabels: Record<string, string> = {
  mcq: "MCQ",
  diagram: "Diagram",
  voice: "Voice",
  code: "Code",
};

export interface AnsweredToolPlaceholderProps {
  message: ToolQuestionMessage;
}

export function AnsweredToolPlaceholder({ message }: AnsweredToolPlaceholderProps) {
  const label = toolLabels[message.tool] ?? message.tool;

  return (
    <div className="rounded-2xl border border-[#D8DDF0] bg-[#F4F6FA] px-4 py-3 text-sm text-[#1F2430]/70">
      {label} question {message.questionIndex + 1} of {message.totalForTool} — answered
    </div>
  );
}
