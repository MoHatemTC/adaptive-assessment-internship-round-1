import type { ComponentType } from "react";

import type { TextMessage, ToolQuestionMessage, UserAnswerMessage } from "@/types/chat";
import { TextBubble } from "@/features/chat/textRenderer";
import { ToolQuestionRenderer } from "@/features/chat/ToolQuestionRenderer";
import { UserAnswerBubble } from "@/components/chat/UserAnswerBubble";

type MessageKindMap = {
  text: TextMessage;
  tool_question: ToolQuestionMessage;
  user_answer: UserAnswerMessage;
};

export const messageKindRegistry: {
  [K in keyof MessageKindMap]: ComponentType<{ message: MessageKindMap[K] }>;
} = {
  text: TextBubble,
  tool_question: ToolQuestionRenderer,
  user_answer: UserAnswerBubble,
};
