"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { NormalizedToolStep, ToolType } from "@/types/chat";
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

export interface VoiceDriverState {
  phase: VoicePhase;
  questionText: string;
  difficulty: Difficulty;
  questionIndex: number;
  followUpDepth: FollowUpDepth;
  voiceSessionId: number | null;
  maxQuestions: number;
  error: string | null;
  submit: () => Promise<NormalizedToolStep>;
  handleRetry: () => void;
}

interface UseVoiceDriverOptions {
  sessionId: string;
  initialQuestion: string;
  initialDifficulty: Difficulty;
  timeLimitSeconds?: number;
  learnerProfile: Record<string, unknown>;
  adminConfig: Record<string, unknown>;
  maxQuestions?: number;
}

export function useVoiceDriver({
  sessionId,
  initialQuestion,
  initialDifficulty,
  timeLimitSeconds = 120,
  learnerProfile,
  adminConfig,
  maxQuestions: maxQ,
}: UseVoiceDriverOptions): VoiceDriverState {
  const [phase, setPhase] = useState<VoicePhase>("initializing");
  const [questionText, setQuestionText] = useState(initialQuestion);
  const [difficulty, setDifficulty] = useState<Difficulty>(initialDifficulty);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [voiceSessionId, setVoiceSessionId] = useState<number | null>(null);
  const [followUpDepth, setFollowUpDepth] = useState<FollowUpDepth>("simple");
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
    async (question: string, difficulty: Difficulty, qIndex: number) => {
      try {
        const resp = await startAdaptiveVoiceSession({
          session_id: sessionId,
          question_text: question,
          question_index: qIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: difficulty,
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
    void initSession(initialQuestion, initialDifficulty, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = useCallback(
    async (): Promise<NormalizedToolStep> => {
      if (voiceSessionId === null) {
        throw new Error("No active voice session");
      }

      setPhase("processing");

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
            tool: "voice" as ToolType,
            isToolComplete: true,
            nextPayload: null,
            transitionText: "Got it — next question…",
          };
        }

        const nextQuestion = contract.next_question_text;
        const nextDifficulty = contract.difficulty;
        const nextDepth = contract.follow_up_depth;
        const nextIndex = questionIndex + 1;

        setQuestionText(nextQuestion);
        setDifficulty(nextDifficulty);
        setFollowUpDepth(nextDepth);
        setQuestionIndex(nextIndex);
        setPhase("transitioning");

        const resp = await startAdaptiveVoiceSession({
          session_id: sessionId,
          question_text: nextQuestion,
          question_index: nextIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: nextDifficulty,
          learner_profile: learnerProfileRef.current,
          admin_config: adminConfigRef.current,
        } satisfies StartSessionPayload);
        setVoiceSessionId(resp.voice_session_id);

        // Small delay before re-entering recording phase
        await new Promise((resolve) => setTimeout(resolve, 600));
        setPhase("recording");

        return {
          tool: "voice" as ToolType,
          isToolComplete: false,
          nextPayload: {
            questionText: nextQuestion,
            difficulty: nextDifficulty,
            questionIndex: nextIndex,
            followUpDepth: nextDepth,
          },
          transitionText: "Got it — next question…",
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
    setQuestionIndex(0);
    setQuestionText(initialQuestion);
    setDifficulty(initialDifficulty);
    setFollowUpDepth("simple");
    void initSession(initialQuestion, initialDifficulty, 0);
  }, [initialQuestion, initialDifficulty, initSession]);

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
