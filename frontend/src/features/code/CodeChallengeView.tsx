"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CodeEditor } from "@/features/code/CodeEditor";
import { IntegrityMonitor } from "@/features/proctoring";
import {
  generateCodeChallenge,
  listCodeLanguages,
  type AdaptiveContract,
  type ChallengeRead,
  type CodeLanguage,
  type DifficultyLevel,
  type SupportedLanguage,
} from "@/lib/api";

const DEFAULT_ASSESSMENT_ID = "coding-tool-demo";

function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}`;
}

export interface CodeChallengeViewProps {
  initialChallengeId?: number;
  initialSessionId?: string;
  assessmentId?: string;
  /** Enable browser + camera integrity monitoring for the session. */
  enableProctoring?: boolean;
  /** Consent was collected before the assessment (required for camera/mic). */
  proctoringConsentGiven?: boolean;
  /** Reference portrait from identity verification for VLM continuity checks. */
  referenceImageB64?: string;
  onSessionComplete?: (payload: {
    reason: "learner" | "adaptive";
    questionsAnswered: number;
    sessionId: string;
    assessmentId: string;
  }) => void;
}

export function CodeChallengeView({
  initialChallengeId,
  initialSessionId,
  assessmentId = DEFAULT_ASSESSMENT_ID,
  enableProctoring = false,
  proctoringConsentGiven = false,
  referenceImageB64,
  onSessionComplete,
}: CodeChallengeViewProps) {
  const [sessionId, setSessionId] = useState(initialSessionId ?? newSessionId);
  const [languages, setLanguages] = useState<CodeLanguage[]>([]);
  const [language, setLanguage] = useState<SupportedLanguage>("python");
  const [challenge, setChallenge] = useState<ChallengeRead | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("beginner");
  const [activeContract, setActiveContract] = useState<AdaptiveContract | null>(null);
  const [questionsAnswered, setQuestionsAnswered] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sessionStarted, setSessionStarted] = useState(false);
  const [generatingNext, setGeneratingNext] = useState(false);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [endReason, setEndReason] = useState<"learner" | "adaptive" | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to generate challenge",
        );
        if (!contract) setChallenge(null);
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

  const beginSession = useCallback(async () => {
    setSessionStarted(true);
    setLoading(true);
    setError(null);
    try {
      await loadGeneratedChallenge();
    } catch {
      setSessionStarted(false);
    } finally {
      setLoading(false);
    }
  }, [loadGeneratedChallenge]);

  const startNewSession = useCallback(() => {
    if (initialSessionId) {
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
      return;
    }
    setSessionId(newSessionId());
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
  }, [initialSessionId]);

  const handleEndSession = useCallback(() => {
    const answered = questionsAnswered;
    const message =
      answered > 0
        ? `End this session? You have submitted ${answered} answer(s). Progress is saved but no further questions will be generated.`
        : "End this session? No answers have been submitted yet.";
    if (!window.confirm(message)) return;
    setSessionEnded(true);
    setEndReason("learner");
    setChallenge(null);
    setGeneratingNext(false);
    onSessionComplete?.({
      reason: "learner",
      questionsAnswered,
      sessionId,
      assessmentId,
    });
  }, [assessmentId, onSessionComplete, questionsAnswered, sessionId]);

  const handleSubmitted = useCallback(
    async ({ contract }: { contract: AdaptiveContract }) => {
      setActiveContract(contract);
      setQuestionsAnswered(contract.question_index);
      if (contract.stop) {
        setSessionEnded(true);
        setEndReason("adaptive");
        setChallenge(null);
        onSessionComplete?.({
          reason: "adaptive",
          questionsAnswered: contract.question_index,
          sessionId,
          assessmentId,
        });
        return;
      }
      setGeneratingNext(true);
      setError(null);
      try {
        await loadGeneratedChallenge(contract);
      } catch {
        // Error state is set in loadGeneratedChallenge.
      } finally {
        setGeneratingNext(false);
      }
    },
    [assessmentId, loadGeneratedChallenge, onSessionComplete, sessionId],
  );

  const sessionLabel = useMemo(() => sessionId.slice(0, 8), [sessionId]);

  if (!sessionStarted && !sessionEnded && initialChallengeId == null) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold text-neutral">Adaptive coding</h1>
          <p className="text-sm text-neutral/70">
            Choose a language, then begin. The LLM will author your first
            challenge and grade submissions in that language.
          </p>
        </header>
        {languages.length > 0 && (
          <label className="flex max-w-xs flex-col gap-1 text-sm">
            <span className="font-medium text-neutral">Language</span>
            <select
              className="rounded-lg border border-border bg-white px-3 py-2"
              value={language}
              onChange={(e) => setLanguage(e.target.value as SupportedLanguage)}
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
          <p className="rounded-lg border border-error/30 bg-error/5 p-3 text-sm text-error">
            {error}
          </p>
        )}
        <button
          type="button"
          onClick={() => void beginSession()}
          disabled={loading}
          className="w-fit rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:opacity-50"
        >
          {loading ? "Starting session…" : "Begin session"}
        </button>
      </div>
    );
  }

  if (loading && !sessionEnded && !challenge) {
    return (
      <p className="text-sm text-neutral/70">
        LLM is authoring your first {language} challenge…
      </p>
    );
  }

  return (
    <IntegrityMonitor
      sessionId={sessionId}
      enabled={enableProctoring && sessionStarted && !sessionEnded}
      consentGiven={proctoringConsentGiven}
      referenceImageB64={referenceImageB64}
      showBadge={enableProctoring}
    >
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-neutral">Adaptive coding</h1>
          <p className="text-sm text-neutral/70">
            Run tests to practice in the sandbox, then submit when ready. Submit
            saves your response and prepares the next question silently.
          </p>
          <p className="text-xs text-neutral/50">
            Session {sessionLabel}… · assessment {assessmentId}
            {questionsAnswered > 0 && ` · ${questionsAnswered} submitted`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {challenge && (
            <span className="rounded-full bg-surface-muted px-3 py-1 text-xs font-medium capitalize text-neutral">
              {challenge.language}
            </span>
          )}
          {challenge && (
            <button
              type="button"
              onClick={handleEndSession}
              disabled={generatingNext}
              className="rounded-lg border border-error/30 bg-white px-3 py-2 text-sm font-medium text-error transition hover:bg-error/5 disabled:opacity-50"
            >
              End session
            </button>
          )}
        </div>
      </header>

      {activeContract && !sessionEnded && (
        <div className="rounded-lg border border-border bg-surface-muted p-3 text-sm text-neutral/80">
          Question {questionIndex + 1} ·{" "}
          <span className="font-medium capitalize">{difficulty}</span>
        </div>
      )}

      {generatingNext && (
        <p className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm text-primary">
          Answer recorded — LLM is authoring your next challenge…
        </p>
      )}

      {error && !sessionEnded && (
        <div className="space-y-2">
          <p className="rounded-lg border border-error/30 bg-error/5 p-3 text-sm text-error">
            {error}
          </p>
          <button
            type="button"
            onClick={() => void loadGeneratedChallenge(activeContract)}
            className="rounded-lg border border-border bg-white px-3 py-2 text-sm font-medium text-neutral hover:bg-surface-muted"
          >
            Retry generation
          </button>
        </div>
      )}

      {challenge && !sessionEnded && (
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
      )}

      {sessionEnded && (
        <div className="space-y-4 rounded-xl border border-border bg-surface-muted p-5">
          <h2 className="text-lg font-semibold text-neutral">Session ended</h2>
          <p className="text-sm text-neutral/80">
            {endReason === "learner"
              ? "You ended this coding session."
              : "The adaptive loop signalled completion."}
            {questionsAnswered > 0
              ? ` You submitted ${questionsAnswered} answer(s).`
              : " No answers were submitted."}
          </p>
          <button
            type="button"
            onClick={startNewSession}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60"
          >
            Start new session
          </button>
        </div>
      )}
      </div>
    </IntegrityMonitor>
  );
}
