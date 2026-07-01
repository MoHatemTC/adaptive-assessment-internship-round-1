"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { SubmitResult, ToolType, UserAnswerMessage } from "@/types/chat";
import {
  type Difficulty,
  type FollowUpDepth,
  type StartSessionPayload,
  processVoiceSession,
  startAdaptiveVoiceSession,
} from "@/lib/voice-api";

export type VoicePhase =
  | "initializing"
  | "recording"
  | "processing"
  | "transitioning"
  | "complete"
  | "error";

export interface VoiceQuestionPayload {
  questionText: string;
  difficulty: Difficulty;
  questionIndex: number;
  followUpDepth?: FollowUpDepth;
}

export interface VoiceDriverState {
  phase: VoicePhase;
  questionText: string;
  difficulty: Difficulty;
  questionIndex: number;
  followUpDepth: FollowUpDepth;
  voiceSessionId: number | null;
  maxQuestions: number;
  error: string | null;
  submit: () => Promise<SubmitResult>;
  handleRetry: () => void;
}

interface UseVoiceDriverOptions {
  sessionId: string;
  initialQuestion: string;
  initialDifficulty: Difficulty;
  initialQuestionIndex?: number;
  timeLimitSeconds?: number;
  learnerProfile: Record<string, unknown>;
  adminConfig: Record<string, unknown>;
  maxQuestions?: number;
  bootstrapPayload?: VoiceQuestionPayload | null;
  skipBootstrap?: boolean;
}

export function useVoiceDriver({
  sessionId,
  initialQuestion,
  initialDifficulty,
  initialQuestionIndex = 0,
  timeLimitSeconds = 120,
  learnerProfile,
  adminConfig,
  maxQuestions: maxQ,
  bootstrapPayload = null,
  skipBootstrap = false,
}: UseVoiceDriverOptions): VoiceDriverState {
  const bootstrapQuestion = bootstrapPayload?.questionText ?? initialQuestion;
  const bootstrapDifficulty = bootstrapPayload?.difficulty ?? initialDifficulty;
  const bootstrapIndex = bootstrapPayload?.questionIndex ?? initialQuestionIndex;
  const bootstrapDepth = bootstrapPayload?.followUpDepth ?? "simple";

  const [phase, setPhase] = useState<VoicePhase>(skipBootstrap ? "complete" : "initializing");
  const [questionText, setQuestionText] = useState(bootstrapQuestion);
  const [difficulty, setDifficulty] = useState<Difficulty>(bootstrapDifficulty);
  const [questionIndex, setQuestionIndex] = useState(bootstrapIndex);
  const [voiceSessionId, setVoiceSessionId] = useState<number | null>(null);
  const [followUpDepth, setFollowUpDepth] = useState<FollowUpDepth>(bootstrapDepth);
  const [error, setError] = useState<string | null>(null);

  const maxQuestions =
    maxQ ??
    (typeof adminConfig.max_questions === "number"
      ? adminConfig.max_questions
      : typeof adminConfig.question_count === "number"
        ? adminConfig.question_count
        : 10);

  const learnerProfileRef = useRef(learnerProfile);
  learnerProfileRef.current = learnerProfile;
  const adminConfigRef = useRef(adminConfig);
  adminConfigRef.current = adminConfig;

  const initSession = useCallback(
    async (question: string, diff: Difficulty, qIndex: number) => {
      try {
        const resp = await startAdaptiveVoiceSession({
          session_id: sessionId,
          question_text: question,
          question_index: qIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: diff,
          learner_profile: learnerProfileRef.current,
          admin_config: adminConfigRef.current,
        } satisfies StartSessionPayload);
        setVoiceSessionId(resp.voice_session_id);
        setPhase("recording");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to start session.",
        );
        setPhase("error");
      }
    },
    [sessionId, timeLimitSeconds],
  );

  useEffect(() => {
    if (skipBootstrap) return;
    void initSession(bootstrapQuestion, bootstrapDifficulty, bootstrapIndex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = useCallback(
    async (): Promise<SubmitResult> => {
      if (voiceSessionId === null) {
        throw new Error("No active voice session");
      }

      setPhase("processing");

      const answerMessage: UserAnswerMessage = {
        id: `ans-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        kind: "user_answer",
        role: "user",
        createdAt: Date.now(),
        tool: "voice",
        summary: "Voice response submitted",
      };

      try {
        const result = await processVoiceSession(voiceSessionId, {
          session_id: sessionId,
          question_text: questionText,
          question_index: questionIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: difficulty,
          learner_profile: learnerProfileRef.current,
          admin_config: adminConfigRef.current,
          voice_session_id: voiceSessionId,
        });

        const contract = result.adaptive_contract;

        if (!contract || contract.stop || questionIndex >= maxQuestions - 1) {
          setPhase("complete");
          return {
            answerMessage,
            step: {
              tool: "voice" as ToolType,
              isToolComplete: true,
              nextPayload: null,
              transitionText: "Got it — next question…",
            },
          };
        }

        const nextQuestion = contract.next_question_text;
        const nextDifficulty = contract.difficulty;
        const nextDepth = contract.follow_up_depth;
        const nextIndex = questionIndex + 1;

        setPhase("complete");

        return {
          answerMessage,
          step: {
            tool: "voice" as ToolType,
            isToolComplete: false,
            nextPayload: {
              questionText: nextQuestion,
              difficulty: nextDifficulty,
              questionIndex: nextIndex,
              followUpDepth: nextDepth,
            } satisfies VoiceQuestionPayload,
            nextQuestionIndex: nextIndex,
            transitionText: "Got it — next question…",
          },
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Processing failed.";
        setError(msg);
        setPhase("error");
        throw err;
      }
    },
    [
      voiceSessionId,
      sessionId,
      questionText,
      questionIndex,
      difficulty,
      timeLimitSeconds,
      maxQuestions,
    ],
  );

  const handleRetry = useCallback(() => {
    setPhase("initializing");
    setError(null);
    setVoiceSessionId(null);
    setQuestionIndex(bootstrapIndex);
    setQuestionText(bootstrapQuestion);
    setDifficulty(bootstrapDifficulty);
    setFollowUpDepth(bootstrapDepth);
    void initSession(bootstrapQuestion, bootstrapDifficulty, bootstrapIndex);
  }, [
    bootstrapQuestion,
    bootstrapDifficulty,
    bootstrapIndex,
    bootstrapDepth,
    initSession,
  ]);

  return {
    phase,
    questionText,
    difficulty,
    questionIndex,
    followUpDepth,
    voiceSessionId,
    maxQuestions,
    error,
    submit,
    handleRetry,
  };
}
