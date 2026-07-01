"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { NormalizedToolStep, ToolType } from "@/types/chat";
import {
  type AdaptiveContract,
  type ChallengeRead,
  type DifficultyLevel,
  type SupportedLanguage,
  createAdaptiveCodeSubmission,
  generateCodeChallenge,
  listCodeLanguages,
} from "@/lib/api";

export interface CodeDriverState {
  status: "loading" | "ready" | "submitting" | "generating_next" | "complete" | "error";
  challenge: ChallengeRead | null;
  contract: AdaptiveContract | null;
  questionIndex: number;
  difficulty: DifficultyLevel;
  language: SupportedLanguage;
  languages: { id: SupportedLanguage; label: string; monaco_language: string }[];
  questionsAnswered: number;
  error: string | null;
  submit: (code: string) => Promise<NormalizedToolStep>;
  setLanguage: (lang: SupportedLanguage) => void;
  reset: () => void;
}

interface UseCodeDriverOptions {
  sessionId: string;
  assessmentId: string;
  maxQuestions?: number;
}

export function useCodeDriver({
  sessionId,
  assessmentId,
  maxQuestions,
}: UseCodeDriverOptions): CodeDriverState {
  const [languages, setLanguages] = useState<
    { id: SupportedLanguage; label: string; monaco_language: string }[]
  >([]);
  const [language, setLanguage] = useState<SupportedLanguage>("python");
  const [challenge, setChallenge] = useState<ChallengeRead | null>(null);
  const [contract, setContract] = useState<AdaptiveContract | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("beginner");
  const [questionsAnswered, setQuestionsAnswered] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [generatingNext, setGeneratingNext] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  const loadGeneratedChallenge = useCallback(
    async (existingContract?: AdaptiveContract | null) => {
      setError(null);
      try {
        const result = await generateCodeChallenge({
          session_id: sessionId,
          assessment_id: assessmentId,
          contract: existingContract ?? undefined,
          language,
        });
        setChallenge(result.challenge);
        setContract(result.contract);
        setQuestionIndex(result.contract.question_index);
        setDifficulty(result.contract.difficulty);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Failed to generate challenge";
        setError(msg);
        if (!existingContract) setChallenge(null);
        throw err;
      }
    },
    [assessmentId, language, sessionId],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await listCodeLanguages();
        if (!cancelled) setLanguages(items);
      } catch {
        if (!cancelled) {
          setLanguages([
            { id: "python", label: "Python", monaco_language: "python" },
            { id: "javascript", label: "JavaScript", monaco_language: "javascript" },
          ]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    setLoading(true);
    loadGeneratedChallenge()
      .catch(() => {})
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = useCallback(
    async (code: string): Promise<NormalizedToolStep> => {
      if (!challenge || !contract) {
        throw new Error("No active challenge to submit");
      }

      setSubmitting(true);
      setError(null);

      try {
        const result = await createAdaptiveCodeSubmission({
          challenge_id: challenge.id,
          session_id: sessionId,
          assessment_id: assessmentId,
          submitted_code: code,
          question_index: questionIndex,
          difficulty,
        });

        const newContract = result.contract;
        const answered = newContract.question_index;
        setQuestionsAnswered(answered);
        setContract(newContract);

        const reachedLimit =
          maxQuestions != null && maxQuestions > 0 && answered >= maxQuestions;

        if (newContract.stop || reachedLimit) {
          setChallenge(null);
          return {
            tool: "code" as ToolType,
            isToolComplete: true,
            nextPayload: null,
            transitionText: "Got it — next question…",
          };
        }

        setGeneratingNext(true);
        setSubmitting(false);

        const nextChallenge = await generateCodeChallenge({
          session_id: sessionId,
          assessment_id: assessmentId,
          contract: newContract,
          language,
        });

        setChallenge(nextChallenge.challenge);
        setContract(nextChallenge.contract);
        setQuestionIndex(nextChallenge.contract.question_index);
        setDifficulty(nextChallenge.contract.difficulty);
        setGeneratingNext(false);

        return {
          tool: "code" as ToolType,
          isToolComplete: false,
          nextPayload: {
            challenge: nextChallenge.challenge,
            contract: nextChallenge.contract,
            questionIndex: nextChallenge.contract.question_index,
            difficulty: nextChallenge.contract.difficulty,
          },
          transitionText: "Got it — next question…",
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Submit failed";
        setError(msg);
        setSubmitting(false);
        setGeneratingNext(false);
        throw err;
      }
    },
    [
      challenge,
      contract,
      sessionId,
      assessmentId,
      questionIndex,
      difficulty,
      maxQuestions,
      language,
    ],
  );

  const reset = useCallback(() => {
    setChallenge(null);
    setContract(null);
    setQuestionIndex(0);
    setDifficulty("beginner");
    setQuestionsAnswered(0);
    setLoading(true);
    setSubmitting(false);
    setGeneratingNext(false);
    setError(null);
    started.current = false;
  }, []);

  const status: CodeDriverState["status"] = error
    ? "error"
    : submitting
      ? "submitting"
      : generatingNext
        ? "generating_next"
        : loading
          ? "loading"
          : challenge
            ? "ready"
            : "loading";

  return {
    status,
    challenge,
    contract,
    questionIndex,
    difficulty,
    language,
    languages,
    questionsAnswered,
    error,
    submit,
    setLanguage,
    reset,
  };
}
