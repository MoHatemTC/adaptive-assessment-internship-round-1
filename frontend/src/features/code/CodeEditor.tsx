"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import { SandboxResultsPanel } from "@/features/code/SandboxResultsPanel";
import {
  createAdaptiveCodeSubmission,
  createCodeSubmission,
  type AdaptiveContract,
  type ChallengeRead,
  type DifficultyLevel,
  type SubmissionRead,
} from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center rounded-lg border border-border bg-surface-muted text-sm text-neutral">
      Loading editor…
    </div>
  ),
});

export interface CodeEditorProps {
  challenge: ChallengeRead;
  sessionId: string;
  assessmentId: string;
  questionIndex: number;
  difficulty: DifficultyLevel;
  disabled?: boolean;
  onSubmitted?: (result: {
    contract: AdaptiveContract;
  }) => void;
}

export function CodeEditor({
  challenge,
  sessionId,
  assessmentId,
  questionIndex,
  difficulty,
  disabled = false,
  onSubmitted,
}: CodeEditorProps) {
  const [code, setCode] = useState(challenge.starter_code);
  const [runningTests, setRunningTests] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<SubmissionRead | null>(null);
  const [submitRecorded, setSubmitRecorded] = useState(false);

  const busy = runningTests || submitting;

  const handleRunTests = useCallback(async () => {
    setRunningTests(true);
    setError(null);
    setTestResult(null);
    try {
      const submission = await createCodeSubmission({
        challenge_id: challenge.id,
        session_id: sessionId,
        submitted_code: code,
      });
      setTestResult(submission);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test run failed");
    } finally {
      setRunningTests(false);
    }
  }, [challenge.id, code, sessionId]);

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    setSubmitRecorded(false);
    try {
      const adaptive = await createAdaptiveCodeSubmission({
        challenge_id: challenge.id,
        session_id: sessionId,
        assessment_id: assessmentId,
        submitted_code: code,
        question_index: questionIndex,
        difficulty,
      });
      setSubmitRecorded(true);
      onSubmitted?.({ contract: adaptive.contract });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }, [
    assessmentId,
    challenge.id,
    code,
    difficulty,
    onSubmitted,
    questionIndex,
    sessionId,
  ]);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-neutral">{challenge.title}</h2>
        <p className="mt-1 text-sm text-neutral/80">{challenge.description}</p>
        <p className="mt-2 text-xs text-neutral/60">
          Question {questionIndex + 1} · {difficulty} · {challenge.language}
        </p>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <MonacoEditor
          height="320px"
          language={challenge.language}
          theme="vs-light"
          value={code}
          onChange={(value) => setCode(value ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleRunTests}
          disabled={busy || disabled || !code.trim()}
          className="rounded-lg border border-border bg-white px-4 py-2 text-sm font-semibold text-neutral transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
        >
          {runningTests ? "Running tests…" : "Run tests"}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy || disabled || !code.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Submit answer"}
        </button>
        {error && (
          <p className="text-sm text-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <p className="text-xs text-neutral/50">
        Run tests executes the E2B sandbox only (practice, no LLM grading). Submit
        answer records your response and prepares the next challenge silently.
      </p>

      {testResult && (
        <SandboxResultsPanel
          result={testResult}
          title="Practice run"
          subtitle="Sandbox only — not counted toward your adaptive session."
        />
      )}

      {submitRecorded && (
        <p className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm text-primary">
          Answer recorded. Your assessment details are saved privately while the
          next challenge is prepared.
        </p>
      )}
    </div>
  );
}
