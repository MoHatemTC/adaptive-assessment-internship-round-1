import type { SubmitResult, ToolType, UserAnswerMessage } from "@/types/chat";

export function buildUserAnswerMessage(
  tool: ToolType,
  summary: string,
): UserAnswerMessage {
  return {
    id: `ans-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    kind: "user_answer",
    role: "user",
    createdAt: Date.now(),
    tool,
    summary,
  };
}

export function buildPreviewResult(
  tool: ToolType,
  summary: string,
): SubmitResult {
  return {
    answerMessage: buildUserAnswerMessage(tool, summary),
    step: {
      tool,
      isToolComplete: false,
      nextPayload: null,
      transitionText: "Got it — saving your answer…",
    },
    phase: "preview",
  };
}

export async function runSubmitWithPreview(
  preview: SubmitResult,
  execute: () => Promise<SubmitResult>,
  onAnswered: (result: SubmitResult) => void | Promise<void>,
): Promise<void> {
  await onAnswered({ ...preview, phase: "preview" });
  try {
    const finalResult = await execute();
    await onAnswered({ ...finalResult, phase: "final" });
  } catch (error) {
    console.error("Tool submit failed", error);
    throw error;
  }
}
