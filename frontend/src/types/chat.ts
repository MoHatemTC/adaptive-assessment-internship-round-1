export type ChatRole = "assistant" | "user" | "system";

export type ToolType = "mcq" | "voice" | "diagram" | "code";

interface BaseChatMessage {
  id: string;
  role: ChatRole;
  createdAt: number;
}

export interface TextMessage extends BaseChatMessage {
  kind: "text";
  text: string;
}

export interface ToolQuestionMessage extends BaseChatMessage {
  kind: "tool_question";
  tool: ToolType;
  questionIndex: number;
  totalForTool: number;
  difficulty?: string;
  timeLimitSeconds?: number | null;
  status: "generating" | "ready" | "answered" | "failed";
  payload: unknown;
}

export interface UserAnswerMessage extends BaseChatMessage {
  kind: "user_answer";
  tool: ToolType;
  summary: string;
}

export type ChatMessage = TextMessage | ToolQuestionMessage | UserAnswerMessage;

export interface NormalizedToolStep {
  tool: ToolType;
  isToolComplete: boolean;
  nextPayload: unknown | null;
  nextQuestionIndex?: number;
  transitionText: string;
}

export type SubmitPhase = "preview" | "final";

export interface SubmitResult {
  answerMessage: UserAnswerMessage;
  step: NormalizedToolStep;
  phase?: SubmitPhase;
}
