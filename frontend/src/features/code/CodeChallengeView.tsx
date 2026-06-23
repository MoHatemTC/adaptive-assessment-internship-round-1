"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CodeAssessmentHeader } from "@/features/code/CodeAssessmentHeader";
import { CodeEditor } from "@/features/code/CodeEditor";
import { CodeQuestionPanel } from "@/features/code/CodeQuestionPanel";
import type { CodeChallengeViewProps } from "@/features/code/types";
import {
  generateCodeChallenge,
  getChallenge,
  listCodeLanguages,
  type AdaptiveContract,
  type ChallengeRead,
  type CodeLanguage,
  type DifficultyLevel,
  type SupportedLanguage,
} from "@/lib/api";

const DEFAULT_ASSESSMENT_ID = "coding-tool-demo";
const DEFAULT_TOTAL_QUESTIONS = 10;
/** Per-question UI timer — separate from sandbox execution timeout on the challenge. */
const DEFAULT_QUESTION_TIME_SECONDS = 15 * 60;

function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}`;
}

export function CodeChallengeView({
  sessionId: sessionIdProp,
  assessmentId: assessmentIdProp,
  initialChallengeId,
  mode = "standalone",
  questionNumber: questionNumberProp,
  totalQuestions = DEFAULT_TOTAL_QUESTIONS,
  timeLimitSeconds,
  initialLanguage = "python",
  autoStart = false,
  onExit,
  onSessionComplete,
  onSubmitted: onSubmittedProp,
}: CodeChallengeViewProps) {
  const [sessionId, setSessionId] = useState(sessionIdProp ?? newSessionId);
  const assessmentId = assessmentIdProp ?? DEFAULT_ASSESSMENT_ID;
  const [languages, setLanguages] = useState<CodeLanguage[]>([]);
  const [language, setLanguage] = useState<SupportedLanguage>(initialLanguage);
  const [challenge, setChallenge] = useState<ChallengeRead | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("beginner");
  const [activeContract, setActiveContract] = useState<AdaptiveContract | null>(
    null,
  );
  const [questionsAnswered, setQuestionsAnswered] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sessionStarted, setSessionStarted] = useState(
    autoStart || initialChallengeId != null,
  );
  const [generatingNext, setGeneratingNext] = useState(false);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [endReason, setEndReason] = useState<"learner" | "adaptive" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(
    timeLimitSeconds ?? null,
  );

  useEffect(() => {
    if (sessionIdProp) setSessionId(sessionIdProp);
  }, [sessionIdProp]);

  useEffect(() => {
    if (timeLimitSeconds != null) setSecondsRemaining(timeLimitSeconds);
  }, [timeLimitSeconds]);

  useEffect(() => {
    if (!sessionStarted || sessionEnded || challenge == null) return;

    const timer = window.setInterval(() => {
      setSecondsRemaining((value) => {
        if (value == null || value <= 0) return 0;
        return value - 1;
      });
    }, 1000);

    return () => window.clearInterval(timer);
  }, [challenge?.id, sessionEnded, sessionStarted]);

  const loadFixedChallenge = useCallback(async (challengeId: number) => {
    setError(null);
    const loaded = await getChallenge(challengeId);
    setChallenge(loaded);
    setQuestionIndex(0);
    setDifficulty("beginner");
    setActiveContract(null);
  }, []);

  const loadGeneratedChallenge = useCallback(
    async (contract?: AdaptiveContract | null) => {
      setError(null);
      try {
        const result = await generateCodeChallenge({
          session_id: sessionId,
          assessment_id: assessmentId,
          contract: contract ?? undefined,
          language,
        });
        setChallenge(result.challenge);
        setActiveContract(result.contract);
        setQuestionIndex(result.contract.question_index);
        setDifficulty(result.contract.difficulty);
        setSecondsRemaining(timeLimitSeconds ?? DEFAULT_QUESTION_TIME_SECONDS);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to generate challenge",
        );
        if (!contract) setChallenge(null);
        throw err;
      }
    },
    [assessmentId, language, sessionId, timeLimitSeconds],
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
            {
              id: "javascript",
              label: "JavaScript",
              monaco_language: "javascript",
            },
          ]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const beginSession = useCallback(async () => {
    if (!sessionIdProp) {
      setSessionId(newSessionId());
    }
    setSessionStarted(true);
    setLoading(true);
    setError(null);
    setSecondsRemaining(timeLimitSeconds ?? DEFAULT_QUESTION_TIME_SECONDS);
    try {
      if (initialChallengeId != null) {
        await loadFixedChallenge(initialChallengeId);
      } else {
        await loadGeneratedChallenge();
      }
    } catch {
      setSessionStarted(false);
    } finally {
      setLoading(false);
    }
  }, [initialChallengeId, loadFixedChallenge, loadGeneratedChallenge, sessionIdProp, timeLimitSeconds]);

  const autoStartedRef = useRef(false);

  useEffect(() => {
    if (
      !autoStart ||
      autoStartedRef.current ||
      sessionStarted ||
      sessionEnded
    ) {
      return;
    }
    autoStartedRef.current = true;
    void beginSession();
  }, [autoStart, beginSession, sessionEnded, sessionStarted]);

  const finishSession = useCallback(
    (reason: "learner" | "adaptive") => {
      setSessionEnded(true);
      setEndReason(reason);
      setChallenge(null);
      setGeneratingNext(false);
      onSessionComplete?.({
        questionsAnswered,
        reason,
        sessionId,
        assessmentId,
      });
    },
    [assessmentId, onSessionComplete, questionsAnswered, sessionId],
  );

  const handleExit = useCallback(() => {
    if (onExit) {
      onExit();
      return;
    }
    if (mode === "standalone" && questionsAnswered > 0) {
      const message =
        "Exit this coding session? Submitted answers are already saved.";
      if (!window.confirm(message)) return;
    }
    finishSession("learner");
  }, [finishSession, mode, onExit, questionsAnswered]);

  const startNewSession = useCallback(() => {
    setSessionId(sessionIdProp ?? newSessionId());
    setChallenge(null);
    setQuestionIndex(0);
    setDifficulty("beginner");
    setActiveContract(null);
    setQuestionsAnswered(0);
    setSessionEnded(false);
    setSessionStarted(false);
    setEndReason(null);
    setError(null);
    setLoading(false);
    setSecondsRemaining(timeLimitSeconds ?? null);
  }, [sessionIdProp, timeLimitSeconds]);

  const handleSubmitted = useCallback(
    async ({ contract }: { contract: AdaptiveContract }) => {
      setActiveContract(contract);
      setQuestionsAnswered(contract.question_index);
      onSubmittedProp?.({ contract });

      if (contract.stop) {
        finishSession("adaptive");
        return;
      }

      setGeneratingNext(true);
      setError(null);
      try {
        await loadGeneratedChallenge(contract);
      } catch {
        // Error surfaced via `error` state.
      } finally {
        setGeneratingNext(false);
      }
    },
    [finishSession, loadGeneratedChallenge, onSubmittedProp],
  );

  const displayQuestionNumber = useMemo(() => {
    if (questionNumberProp != null) return questionNumberProp;
    return questionIndex + 1;
  }, [questionIndex, questionNumberProp]);

  if (!sessionStarted && !sessionEnded) {
    return (
      <div className="mx-auto flex min-h-[60vh] w-full max-w-lg flex-col justify-center gap-md p-gutter">
        <div className="rounded-xl border border-surface-container-highest bg-surface p-md shadow-card">
          <h1 className="text-headline-sm text-on-surface">Coding challenge</h1>
          <p className="mt-2 text-body-md text-on-surface-variant">
            {mode === "embedded"
              ? "Complete the challenge below. Run code to practice, then submit when ready."
              : "Standalone adaptive coding tool — ready to plug into the examiner chat."}
          </p>
          {languages.length > 0 && (
            <label className="mt-md flex max-w-xs flex-col gap-1 text-label-md">
              Language
              <select
                className="rounded-lg border border-border-base bg-surface px-3 py-2 text-body-md"
                value={language}
                onChange={(e) =>
                  setLanguage(e.target.value as SupportedLanguage)
                }
              >
                {languages.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {error && (
            <p className="mt-sm rounded-lg border border-error/30 bg-error/5 p-3 text-body-sm text-error">
              {error}
            </p>
          )}
          <button
            type="button"
            onClick={() => void beginSession()}
            disabled={loading}
            className="mt-md flex h-[43px] items-center justify-center rounded-lg bg-primary px-6 text-label-md text-on-primary transition hover:bg-primary-hover disabled:opacity-50"
          >
            {loading ? "Starting…" : "Begin challenge"}
          </button>
        </div>
      </div>
    );
  }

  if (loading && !sessionEnded && !challenge) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center p-gutter text-body-md text-on-surface-variant">
        Authoring your {language} challenge…
      </div>
    );
  }

  if (sessionEnded) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-lg flex-col justify-center gap-sm p-gutter">
        <div className="rounded-xl border border-surface-container-highest bg-surface p-md shadow-card">
          <h2 className="text-title-md text-on-surface">Session complete</h2>
          <p className="mt-2 text-body-md text-on-surface-variant">
            {endReason === "learner"
              ? "You exited the coding session."
              : "The adaptive loop completed this coding segment."}
            {questionsAnswered > 0
              ? ` You submitted ${questionsAnswered} solution(s).`
              : " No solutions were submitted."}
          </p>
          {mode === "standalone" && (
            <button
              type="button"
              onClick={startNewSession}
              className="mt-md flex h-[43px] items-center justify-center rounded-lg bg-primary px-6 text-label-md text-on-primary transition hover:bg-primary-hover"
            >
              Start new session
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <CodeAssessmentHeader
        questionNumber={displayQuestionNumber}
        totalQuestions={totalQuestions}
        secondsRemaining={secondsRemaining}
        onExit={handleExit}
      />

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-gutter p-gutter lg:flex-row">
        {challenge && (
          <>
            <CodeQuestionPanel challenge={challenge} difficulty={difficulty} />
            <CodeEditor
              key={`${sessionId}-${challenge.id}-${questionIndex}-${difficulty}`}
              challenge={challenge}
              sessionId={sessionId}
              assessmentId={assessmentId}
              questionIndex={questionIndex}
              difficulty={difficulty}
              onSubmitted={handleSubmitted}
              disabled={generatingNext}
            />
          </>
        )}

        {generatingNext && (
          <p className="fixed bottom-6 right-6 rounded-lg border border-primary/20 bg-surface px-4 py-2 text-body-sm text-primary shadow-card">
            Preparing your next challenge…
          </p>
        )}

        {error && !challenge && (
          <div className="w-full space-y-2">
            <p className="rounded-lg border border-error/30 bg-error/5 p-3 text-body-sm text-error">
              {error}
            </p>
            <button
              type="button"
              onClick={() => void loadGeneratedChallenge(activeContract)}
              className="rounded-lg border border-border-base bg-surface px-3 py-2 text-label-md text-on-surface hover:bg-surface-muted"
            >
              Retry
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
