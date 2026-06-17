"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CodeEditor } from "@/features/code/CodeEditor";
import {
  generateCodeChallenge,
  type AdaptiveContract,
  type ChallengeRead,
  type DifficultyLevel,
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
}

export function CodeChallengeView({ initialChallengeId }: CodeChallengeViewProps) {
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const [sessionId, setSessionId] = useState(newSessionId);
  const [challenge, setChallenge] = useState<ChallengeRead | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [difficulty, setDifficulty] = useState<DifficultyLevel>("beginner");
  const [activeContract, setActiveContract] = useState<AdaptiveContract | null>(null);
  const [questionsAnswered, setQuestionsAnswered] = useState(0);
  const [loading, setLoading] = useState(true);
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
          assessment_id: DEFAULT_ASSESSMENT_ID,
          contract: contract ?? undefined,
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
    [sessionId],
  );

  const startNewSession = useCallback(() => {
    setSessionId(newSessionId());
    setSessionEpoch((n) => n + 1);
    setChallenge(null);
    setQuestionIndex(0);
    setDifficulty("beginner");
    setActiveContract(null);
    setQuestionsAnswered(0);
    setSessionEnded(false);
    setEndReason(null);
    setError(null);
    setLoading(true);
  }, []);

  useEffect(() => {
    if (sessionEnded) {
      setLoading(false);
      return;
    }
    if (initialChallengeId != null) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        await loadGeneratedChallenge();
      } finally {
        setLoading(false);
      }
    })();
  }, [
    initialChallengeId,
    loadGeneratedChallenge,
    sessionEnded,
    sessionEpoch,
  ]);

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
  }, [questionsAnswered]);

  const handleSubmitted = useCallback(
    async ({ contract }: { contract: AdaptiveContract }) => {
      setActiveContract(contract);
      setQuestionsAnswered(contract.question_index);
      if (contract.stop) {
        setSessionEnded(true);
        setEndReason("adaptive");
        setChallenge(null);
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
    [loadGeneratedChallenge],
  );

  const sessionLabel = useMemo(() => sessionId.slice(0, 8), [sessionId]);

  if (loading && !sessionEnded) {
    return (
      <p className="text-sm text-neutral/70">LLM is authoring your first challenge…</p>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-neutral">Adaptive coding</h1>
          <p className="text-sm text-neutral/70">
            Run tests to practice in the sandbox, then submit when ready. Submit
            runs LLM grading, memory extraction, and adaptation for the next
            question.
          </p>
          <p className="text-xs text-neutral/50">
            Session {sessionLabel}… · assessment {DEFAULT_ASSESSMENT_ID}
            {questionsAnswered > 0 && ` · ${questionsAnswered} submitted`}
          </p>
        </div>
        {!sessionEnded && challenge && (
          <button
            type="button"
            onClick={handleEndSession}
            disabled={generatingNext}
            className="rounded-lg border border-error/30 bg-white px-3 py-2 text-sm font-medium text-error transition hover:bg-error/5 disabled:opacity-50"
          >
            End session
          </button>
        )}
      </header>

      {activeContract && !sessionEnded && (
        <div className="rounded-lg border border-border bg-surface-muted p-3 text-sm text-neutral/80">
          Question {questionIndex + 1} ·{" "}
          <span className="font-medium capitalize">{difficulty}</span>
          {activeContract.focus_dimension && (
            <>
              {" "}
              · focus{" "}
              <span className="font-medium">
                {activeContract.focus_dimension.replace("_", " ")}
              </span>
            </>
          )}
          {activeContract.memory_summary && (
            <p className="mt-1 text-xs text-neutral/60">
              {activeContract.memory_summary}
            </p>
          )}
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
          assessmentId={DEFAULT_ASSESSMENT_ID}
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
          {activeContract?.memory_summary && (
            <p className="text-sm text-neutral/70">{activeContract.memory_summary}</p>
          )}
          {activeContract && (
            <ul className="flex flex-wrap gap-2 text-xs">
              {(
                [
                  ["thinking", activeContract.cumulative_scores.thinking],
                  ["work", activeContract.cumulative_scores.work],
                  ["digital_ai", activeContract.cumulative_scores.digital_ai],
                ] as const
              )
                .filter(([, value]) => value != null)
                .map(([name, value]) => (
                  <li
                    key={name}
                    className="rounded-full bg-white px-2.5 py-1 font-medium text-neutral shadow-sm"
                  >
                    {name.replace("_", " ")}: {value}/10
                  </li>
                ))}
            </ul>
          )}
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
  );
}
