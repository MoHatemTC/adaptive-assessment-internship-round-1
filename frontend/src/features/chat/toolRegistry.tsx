import type { ComponentType } from "react";

import type { SubmitResult, ToolQuestionMessage, ToolType } from "@/types/chat";
import { ChatMcqMessage } from "@/features/mcq/ChatMcqMessage";
import { ChatDiagramMessage } from "@/features/diagram/ChatDiagramMessage";
import { ChatVoiceMessage } from "@/features/voice/ChatVoiceMessage";
import { ChatCodeMessage } from "@/features/code/ChatCodeMessage";

export interface ToolRendererProps {
  message: ToolQuestionMessage;
  onAnswered: (result: SubmitResult) => void;
}

export const toolRegistry: Record<ToolType, ComponentType<ToolRendererProps>> = {
  mcq: ChatMcqMessage,
  diagram: ChatDiagramMessage,
  voice: ChatVoiceMessage,
  code: ChatCodeMessage,
};
